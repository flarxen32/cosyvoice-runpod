"""
Entry point RunPod Serverless para CosyVoice 3.

O RunPod procura por rp_handler.py e executa start().
A função handler() em cosyvoice_handler.py faz o trabalho pesado.
"""
import runpod
from cosyvoice_handler import handler

# Configura o worker serverless.
# ConcurrencyModifier controla quantos jobs simultâneos por worker GPU.
# Para TTS em L4 (24GB), 1 por vez evita OOM no cold start.
runpod.serverless.start(
    {"handler": handler, "concurrency_modifier": lambda x: 1}
)
