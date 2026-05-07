# RTX 3060 Fine-Tuning Setup Guide

Complete setup for training QuoteForge on your RTX 3060. Works on Windows or Linux.

## What You Need

- **GPU:** RTX 3060 (12GB for Mistral-7B, 8GB for Phi-3-mini or Llama-3.2-3B)
- **RAM:** 16GB minimum (32GB recommended)
- **Disk:** 50GB free (model + training data + checkpoints)
- **OS:** Windows 11 or Ubuntu 22.04

## Step 1: Install CUDA Toolkit

### Windows
1. Download **CUDA 12.1** from: https://developer.nvidia.com/cuda-12-1-0-download-archive
2. Install with default options
3. Verify:
```powershell
nvcc --version
nvidia-smi
```

### Linux (Ubuntu)
```bash
wget https://developer.download.nvidia.com/compute/cuda/12.1.0/local_installers/cuda_12.1.0_530.30.02_linux.run
sudo sh cuda_12.1.0_530.30.02_linux.run
# Add to ~/.bashrc:
export PATH=/usr/local/cuda-12.1/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-12.1/lib64:$LD_LIBRARY_PATH
```

## Step 2: Install Python 3.10 + Create Environment

```bash
# Create venv
python -m venv quoteforge-ml
# Windows: quoteforge-ml\Scripts\activate
source quoteforge-ml/bin/activate

# Install PyTorch with CUDA 12.1
pip install torch==2.2.0 --index-url https://download.pytorch.org/whl/cu121

# Verify CUDA works
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}')"
```

Expected output:
```
CUDA: True
GPU: NVIDIA GeForce RTX 3060
```

## Step 3: Install ML Dependencies

```bash
pip install transformers==4.40.0 peft==0.10.0 bitsandbytes==0.43.0 \
    accelerate==0.29.0 datasets==2.19.0 trl==0.8.1 \
    sentencepiece protobuf scipy tensorboard
```

## Step 4: Copy Project Files

Copy these from this project to your Windows/Linux machine:
```
quoteforge_v3/backend/
├── training_data/              # The 1,200 samples
│   ├── hf_train.jsonl
│   ├── hf_val.jsonl
│   └── hf_test.jsonl
└── model_training/
    └── scripts/
        ├── train_qlora.py
        ├── merge_lora.py
        ├── convert_to_gguf.py
        └── test_model.py
```

## Step 5: Start Training

### For RTX 3060 12GB — Mistral-7B (best quality)
```bash
cd model_training/scripts
python train_qlora.py --model mistral-7b --epochs 3 --batch-size 2
```
Expected time: **3-5 hours**
Expected VRAM: ~10GB

### For RTX 3060 8GB — Phi-3-mini (faster, still good)
```bash
python train_qlora.py --model phi-3-mini --epochs 3 --batch-size 4
```
Expected time: **1-2 hours**
Expected VRAM: ~6GB

### For RTX 3060 8GB — Llama-3.2-3B (balanced)
```bash
python train_qlora.py --model llama-3.2-3b --epochs 3 --batch-size 2
```
Expected time: **2-3 hours**
Expected VRAM: ~7GB

## Step 6: Test Your Trained Model

```bash
python test_model.py --model-path ../checkpoints/quoteforge-mistral-7b-20260405_180000
```

You'll see the model generate proposal sections. Compare against the base model to see fine-tuning improvements.

## Step 7: Deploy to Ollama (for production serving)

### Merge LoRA into base model
```bash
python merge_lora.py --model-path ../checkpoints/quoteforge-mistral-7b-20260405_180000
```

### Install llama.cpp (for GGUF conversion)
```bash
git clone https://github.com/ggerganov/llama.cpp ~/llama.cpp
cd ~/llama.cpp
make
pip install -r requirements.txt
```

### Convert to GGUF
```bash
python convert_to_gguf.py --model-path ../checkpoints/quoteforge-mistral-7b-20260405_180000-merged
```

### Import into Ollama
```bash
ollama create quoteforge -f Modelfile
ollama run quoteforge
```

Now your fine-tuned model is callable via Ollama:
```bash
curl http://localhost:11434/api/chat -d '{
  "model": "quoteforge",
  "messages": [{"role":"user","content":"Generate a cover letter for Acme Corp, $75K deal"}]
}'
```

## Step 8: Connect QuoteForge Backend to Your Model

Edit `backend/.env`:
```
LLM_BACKEND=ollama
LLM_URL=http://localhost:11434
LLM_MODEL=quoteforge
QUOTEFORGE_USE_LLM=true
```

Restart backend — it now uses YOUR fine-tuned model.

## Production Scaling Path

Same model, same code, bigger hardware:

| Stage | Hardware | Setup | Throughput |
|-------|----------|-------|------------|
| Dev | RTX 3060 local | Ollama | 1-3 req/sec |
| Staging | RunPod RTX 4090 | vLLM | 10-20 req/sec |
| Production | RunPod A100 80GB | vLLM (tensor parallel) | 50-100 req/sec |
| Enterprise | Multi-A100 cluster | Kubernetes + vLLM | 1000+ req/sec |

See `DEPLOYMENT.md` for cloud deployment configs.

## Troubleshooting

**"CUDA out of memory"**
- Use smaller model (`phi-3-mini`)
- Reduce batch size: `--batch-size 1`
- Increase gradient accumulation in `train_qlora.py`

**"bitsandbytes not found"**
```bash
pip install bitsandbytes --upgrade --force-reinstall
```

**"Training very slow"**
- Verify GPU is being used: `nvidia-smi` should show ~90% utilization
- Check you're not running on CPU by accident

**"ConnectError on Ollama"**
- Make sure Ollama is running: `ollama serve`
- Check model is loaded: `ollama list`
