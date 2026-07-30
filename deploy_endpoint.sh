#!/usr/bin/env bash
# deploy_endpoint.sh — Cria template + endpoint serverless no RunPod
# Executar APÓS a imagem estar disponível no GHCR
set -euo pipefail

RP_KEY="${RUNPOD_API_KEY:?Defina RUNPOD_API_KEY no ambiente}"
IMAGE="ghcr.io/flarxen32/cosyvoice-runpod:latest"
GPUS="${1:-ADA_24}"  # ADA_24 = L4 / RTX 4090 (24GB Ada Lovelace), cheapest that runs CosyVoice

echo "=== 1. Criar template serverless ==="
TEMPLATE_RESP=$(curl -s -X POST "https://api.runpod.io/graphql?api_key=$RP_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"mutation { saveTemplate(input: { containerDiskInGb: 20, dockerArgs: \"python3 /workspace/rp_handler.py\", env: [], imageName: \"$IMAGE\", isServerless: true, name: \"CosyVoice 3\", volumeInGb: 0 }) { id name imageName isServerless } }\"
  }")
echo "$TEMPLATE_RESP"
TEMPLATE_ID=$(echo "$TEMPLATE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['saveTemplate']['id'])")
echo "Template ID: $TEMPLATE_ID"

echo ""
echo "=== 2. Criar endpoint serverless ==="
ENDPOINT_RESP=$(curl -s -X POST "https://api.runpod.io/graphql?api_key=$RP_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"mutation { saveEndpoint(input: { gpuIds: \"$GPUS\", name: \"CosyVoice 3 TTS\", templateId: \"$TEMPLATE_ID\", workersMin: 0, workersMax: 1, idleTimeout: 5, flashBootType: FLASHBOOT, scalerType: \"QUEUE_DELAY\", scalerValue: 4 }) { id name gpuIds workersMin workersMax flashBootType } }\"
  }")
echo "$ENDPOINT_RESP"
ENDPOINT_ID=$(echo "$ENDPOINT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['saveEndpoint']['id'])")
echo "Endpoint ID: $ENDPOINT_ID"

echo ""
echo "=== 3. Salvar info ==="
python3 -c "
import json
info = {'endpoint_id': '$ENDPOINT_ID', 'template_id': '$TEMPLATE_ID', 'image': '$IMAGE', 'gpu': '$GPUS'}
with open('/opt/data/.dagger/dan/runpod/endpoint_info.json', 'w') as f:
    json.dump(info, f, indent=2)
print('Saved to endpoint_info.json')
"
echo ""
echo "DONE: Endpoint $ENDPOINT_ID criado com template $TEMPLATE_ID"
