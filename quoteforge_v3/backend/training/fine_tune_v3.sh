#!/usr/bin/env bash
#
# MLX fine-tune script for QuoteForge-V3 Negotiation.
#
# Prereqs:
#   Apple Silicon Mac with mlx_lm installed in the project venv:
#     ./venv/bin/pip install "mlx-lm>=0.20"
#
# Inputs:
#   models/quoteforge-v3/data/train.jsonl  (produced by prepare_negotiation_dataset.py)
#   models/quoteforge-v3/data/valid.jsonl
#
# Output:
#   models/quoteforge-v3/adapters/            (the fine-tuned LoRA adapter)
#
# After training:
#   NEGOTIATION_MODEL_BACKEND=mlx NEGOTIATION_MODEL_PATH=models/quoteforge-v3 \
#     ./venv/bin/python training/evaluate_v3.py
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/models/quoteforge-v3"
DATA="${OUT}/data"
ADAPTERS="${OUT}/adapters"

if [[ ! -f "${DATA}/train.jsonl" ]]; then
    echo "train.jsonl missing — run prepare_negotiation_dataset.py first"
    exit 1
fi

mkdir -p "${ADAPTERS}"

# Base model: same as V2 so we stay on the budget we've already proven. Swap
# to a larger base if V3 quality is still insufficient after full training.
BASE_MODEL="mlx-community/Llama-3.2-1B-Instruct-4bit"

# Training args tuned for CPQ structured output. Short runs — ~14 min on M3.
# --iters 500 lands roughly at V2's training budget.
"${ROOT}/venv/bin/python" -m mlx_lm.lora \
    --train \
    --model "${BASE_MODEL}" \
    --data "${DATA}" \
    --iters 500 \
    --batch-size 4 \
    --lora-layers 8 \
    --learning-rate 1e-5 \
    --adapter-path "${ADAPTERS}" \
    --save-every 100

echo
echo "Adapter saved to ${ADAPTERS}"
echo "Evaluate with:"
echo "  NEGOTIATION_MODEL_BACKEND=mlx NEGOTIATION_MODEL_PATH=${OUT} \\"
echo "    ${ROOT}/venv/bin/python ${ROOT}/training/evaluate_v3.py"
