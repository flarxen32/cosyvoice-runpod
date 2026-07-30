"""
Handler CosyVoice 3 para RunPod Serverless.

Input JSON (dentro de job["input"]):
    {
        "text": "Texto para sintetizar (obrigatório)",
        "reference_audio": "<base64 wav>" (opcional),
        "reference_text": "Transcrição do áudio de referência" (opcional),
        "mode": "zero_shot" | "cross_lingual" | "instruct2" (default: zero_shot),
        "instruct_text": "Instrução para mode=instruct2" (opcional),
        "speed": 1.0 (opcional),
        "stream": false (opcional)
    }

Output:
    {"audio": "<base64 wav 24000Hz mono>"}

Se reference_audio não for fornecido, usa o zero_shot_prompt.wav
embutido no repo CosyVoice como voz padrão.
"""
import os
import sys
import base64
import io
import logging
import tempfile

# Garante que CosyVoice e Matcha-TTS estão no path
COSYVOICE_ROOT = "/workspace/CosyVoice"
for p in [COSYVOICE_ROOT, os.path.join(COSYVOICE_ROOT, "third_party", "Matcha-TTS")]:
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Caminho do modelo baixado durante o build
MODEL_DIR = os.environ.get("COSYVOICE_MODEL_DIR", os.path.join(COSYVOICE_ROOT, "pretrained_models", "Fun-CosyVoice3-0.5B"))

# Áudio de referência padrão (embutido no repo)
DEFAULT_PROMPT_WAV = os.path.join(COSYVOICE_ROOT, "asset", "zero_shot_prompt.wav")

# Prefixo obrigatório para CosyVoice 3
CV3_PROMPT_PREFIX = "You are a helpful assistant.<|endofprompt|>"

# Carrega o modelo uma única vez no startup do worker (não por job)
_model = None


def get_model():
    """Lazy-load do modelo CosyVoice 3. Persiste entre chamadas."""
    global _model
    if _model is not None:
        return _model
    logger.info("Carregando CosyVoice 3 de %s ...", MODEL_DIR)
    from cosyvoice.cli.cosyvoice import AutoModel
    _model = AutoModel(model_dir=MODEL_DIR)
    logger.info("Modelo carregado. sample_rate=%s", _model.sample_rate)
    return _model


def _decode_reference_audio(b64_data):
    """Decodifica base64 WAV e salva em arquivo temporário 16kHz mono."""
    raw = base64.b64decode(b64_data)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.write(raw)
    tmp.close()
    return tmp.name


def _tts_speech_to_wav_bytes(tts_speech_tensor, sample_rate):
    """Converte tensor PyTorch [1, N] em bytes WAV (int16, mono).

    Usa tempfile (método testado em example.py oficial) em vez de BytesIO
    para máxima compatibilidade com torchaudio.
    """
    import torchaudio

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    torchaudio.save(tmp.name, tts_speech_tensor.cpu(), sample_rate)
    with open(tmp.name, "rb") as f:
        wav_bytes = f.read()
    os.unlink(tmp.name)
    return wav_bytes


def generate_audio(text, reference_audio=None, reference_text=None,
                   mode="zero_shot", instruct_text=None, speed=1.0, stream=False):
    """
    Gera áudio usando CosyVoice 3. Retorna bytes WAV.

    modos:
      - zero_shot: precisa de reference_audio + reference_text (ou usa default)
      - cross_lingual: precisa de reference_audio (ou usa default)
      - instruct2: precisa de reference_audio + instruct_text
    """
    model = get_model()

    # Resolve áudio de referência
    if reference_audio:
        prompt_wav = _decode_reference_audio(reference_audio)
        _cleanup_after = prompt_wav
    else:
        prompt_wav = DEFAULT_PROMPT_WAV
        _cleanup_after = None
        logger.info("Sem reference_audio — usando prompt padrão: %s", prompt_wav)

    try:
        # Concatena todos os chunks do generator em um único tensor
        import torch
        chunks = []

        if mode == "zero_shot":
            # CV3 exige prefixo no prompt_text
            ptext = reference_text or "希望你以后能够做的比我还好呦。"
            if CV3_PROMPT_PREFIX not in ptext:
                ptext = CV3_PROMPT_PREFIX + ptext
            logger.info("zero_shot | text=%d chars | prompt_text=%d chars", len(text), len(ptext))
            gen = model.inference_zero_shot(
                text, ptext, prompt_wav, stream=stream, speed=speed
            )

        elif mode == "cross_lingual":
            # CV3 exige prefixo no próprio texto
            if CV3_PROMPT_PREFIX not in text:
                text = CV3_PROMPT_PREFIX + text
            logger.info("cross_lingual | text=%d chars", len(text))
            gen = model.inference_cross_lingual(text, prompt_wav, stream=stream, speed=speed)

        elif mode == "instruct2":
            # CV3 exige prefixo no instruct_text
            if not instruct_text:
                raise ValueError("mode=instruct2 requer instruct_text")
            if CV3_PROMPT_PREFIX not in instruct_text:
                instruct_text = CV3_PROMPT_PREFIX + instruct_text
            logger.info("instruct2 | text=%d chars | instruct=%d chars", len(text), len(instruct_text))
            gen = model.inference_instruct2(text, instruct_text, prompt_wav, stream=stream, speed=speed)

        else:
            raise ValueError(f"modo desconhecido: {mode}")

        for chunk in gen:
            chunks.append(chunk["tts_speech"].cpu())

        if not chunks:
            raise RuntimeError("modelo não gerou nenhum chunk de áudio")

        # Concatena ao longo do eixo temporal (dim=1 para shape [1, N])
        full = torch.cat(chunks, dim=1)
        wav_bytes = _tts_speech_to_wav_bytes(full, model.sample_rate)
        return wav_bytes, model.sample_rate

    finally:
        if _cleanup_after and os.path.exists(_cleanup_after):
            os.unlink(_cleanup_after)


def handler(job):
    """
    Entry point do RunPod Serverless.
    job["input"] contém os parâmetros. Retorna dict serializável.
    """
    job_input = job.get("input", {})
    text = job_input.get("text")
    if not text:
        return {"error": "campo 'text' é obrigatório"}

    try:
        wav_bytes, sr = generate_audio(
            text=text,
            reference_audio=job_input.get("reference_audio"),
            reference_text=job_input.get("reference_text"),
            mode=job_input.get("mode", "zero_shot"),
            instruct_text=job_input.get("instruct_text"),
            speed=float(job_input.get("speed", 1.0)),
            stream=bool(job_input.get("stream", False)),
        )
        audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
        return {
            "audio": audio_b64,
            "format": "wav",
            "sample_rate": sr,
            "size_bytes": len(wav_bytes),
        }
    except Exception as e:
        logger.exception("Erro no handler")
        return {"error": str(e), "type": type(e).__name__}
