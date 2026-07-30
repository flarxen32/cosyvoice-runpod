# cosyvoice-runpod

Endpoint serverless **CosyVoice 3** (Fun-CosyVoice3-0.5B) no RunPod para TTS com clonagem de voz zero-shot. Foco: pt-BR.

## Como funciona

1. RunPod importa este repo via GitHub e constrói a imagem Docker x86 (custo de build = zero).
2. O modelo Fun-CosyVoice3-0.5B é baixado durante o BUILD da imagem (cold start menor).
3. Worker escala para zero (`minWorkers=0`) quando ocioso.

## Arquivos

| Arquivo | Função |
|---------|--------|
| `rp_handler.py` | Entry point RunPod — registra o handler |
| `cosyvoice_handler.py` | Lógica de inferência CosyVoice 3 |
| `Dockerfile` | Imagem CUDA 12.1 + CosyVoice + modelo pré-baixado |
| `requirements.txt` | Deps extras (runpod SDK) |

## API

### Request

POST para `https://api.runpod.io/v2/<ENDPOINT_ID>/run`

```json
{
  "input": {
    "text": "Olá, este é um teste de voz em português brasileiro.",
    "reference_audio": "<base64 wav 16kHz>",
    "reference_text": "Transcrição do áudio de referência",
    "mode": "zero_shot",
    "speed": 1.0,
    "stream": false
  }
}
```

**Campos:**

- `text` *(obrigatório)*: texto para sintetizar
- `reference_audio` *(opcional)*: WAV base64 (16kHz mono). Se ausente, usa prompt padrão do repo
- `reference_text` *(opcional)*: transcrição do áudio de referência (necessário para zero_shot)
- `mode`: `zero_shot` (default) | `cross_lingual` | `instruct2`
- `instruct_text`: instrução em linguagem natural (apenas mode=instruct2)
- `speed`: 1.0 (default), 0.5–2.0
- `stream`: false (default)

### Response

```json
{
  "output": {
    "audio": "<base64 WAV 24kHz mono>",
    "format": "wav",
    "sample_rate": 24000,
    "size_bytes": 12345
  }
}
```

## Decodificar o áudio

```bash
# Supondo que a resposta está em resp.json
python3 -c "import json,base64; d=json.load(open('resp.json')); open('out.wav','wb').write(base64.b64decode(d['output']['audio']))"
```

## Notas sobre CosyVoice 3

- CV3 **exige** o prefixo `You are a helpful assistant.<|endofprompt|>` em `reference_text` (zero_shot) ou no próprio `text` (cross_lingual) ou em `instruct_text` (instruct2). O handler adiciona automaticamente.
- CV3 não tem modo "voz default sem referência" — o handler usa `asset/zero_shot_prompt.wav` (embutido no repo CosyVoice) como fallback quando `reference_audio` não é fornecido.
- Idiomas suportados: zh, en, ja, ko, de, es, fr, it, ru + dialetos chineses. Português não é oficialmente listado, mas o modelo multilíngue consegue sintetizar pt-BR com qualidade razoável em zero_shot/cross_lingual.

## Custo

- GPU: NVIDIA L4 ($0.69/h no RunPod)
- Inferência de ~5s de áudio: <1s de GPU (~$0.0002)
- Cold start (loading do modelo): ~30–60s de GPU (~$0.01)
- `minWorkers=0`: custo zero quando ocioso
