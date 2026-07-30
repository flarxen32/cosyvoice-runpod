# ============================================================
# CosyVoice 3 Serverless — Dockerfile para RunPod (x86_64, CUDA 12.1)
# ============================================================
# Baixa o modelo no BUILD (não no runtime) para minimizar cold start.
# Tamanho final esperado: ~8-9 GB.
# ============================================================

FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# ---------- Dependências de sistema ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3-pip python3.10-dev \
        git wget curl sox libsox-dev ffmpeg \
        && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3

# ---------- Clone CosyVoice (com submódulos) ----------
WORKDIR /workspace
RUN git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git /workspace/CosyVoice \
    && cd /workspace/CosyVoice \
    && git submodule update --init --recursive

# ---------- Instala dependências Python ----------
# Instalamos torch primeiro (PyTorch index) para garantir versão CUDA 12.1
RUN pip install --no-cache-dir torch==2.3.1 torchaudio==2.3.1 \
    --index-url https://download.pytorch.org/whl/cu121

# Dependências do CosyVoice (removemos deepspeed/tensorrt que pesam no build
# e não são necessários para inferência serverless)
RUN cd /workspace/CosyVoice && \
    grep -vE 'deepspeed|tensorrt|tensorboard|grpc' requirements.txt > /tmp/req_filtered.txt && \
    pip install --no-cache-dir -r /tmp/req_filtered.txt

# SDK RunPod Serverless
RUN pip install --no-cache-dir runpod==1.7.3

# ---------- Download do modelo no BUILD ----------
# Fun-CosyVoice3-0.5B-2512 (~2 GB). Usamos HuggingFace para servidores fora da China.
RUN pip install --no-cache-dir huggingface_hub && \
    python3 -c "from huggingface_hub import snapshot_download; \
                 snapshot_download('FunAudioLLM/Fun-CosyVoice3-0.5B-2512', \
                                   local_dir='/workspace/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B')"

# ---------- Copia handler e entry point ----------
COPY cosyvoice_handler.py rp_handler.py /workspace/

WORKDIR /workspace

# O RunPod executa: python3 /workspace/rp_handler.py
CMD ["python3", "/workspace/rp_handler.py"]
