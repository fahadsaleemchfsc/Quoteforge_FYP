# QuoteForge Model — Production Deployment Guide

How to scale from RTX 3060 (dev) → cloud GPU (production).

## Architecture

```
┌────────────────────────────────────────────────────────┐
│  QuoteForge Backend (FastAPI)                          │
│  └── Pricing Engine, Document Engine, CRM Connector    │
└─────────────────────┬──────────────────────────────────┘
                      │ HTTP
                      ↓
┌─────────────────────────────────────────────────────────┐
│  LLM Inference Server (vLLM or Ollama)                  │
│  ├── Stage 1: Local RTX 3060 (dev)                      │
│  ├── Stage 2: RunPod RTX 4090 (staging, $0.40/hr)       │
│  ├── Stage 3: RunPod A100 80GB (prod, $1.89/hr)         │
│  └── Stage 4: Multi-A100 K8s cluster (enterprise)       │
└─────────────────────────────────────────────────────────┘
```

---

## Stage 1: Local Dev (RTX 3060)

Already covered in `SETUP_RTX3060.md`. Use Ollama with your fine-tuned model.

---

## Stage 2: RunPod Deployment ($0.40-2/hr)

### Why RunPod
- Pay only when training/serving
- RTX 4090 or A100 available
- One-click templates
- Community pricing 50% cheaper than on-demand

### Deploy to RunPod

1. **Create RunPod account** → https://runpod.io

2. **Upload your fine-tuned model** to RunPod network volume:
```bash
# From your local machine
scp -r ./checkpoints/quoteforge-mistral-7b-20260405_180000-merged runpod@your-pod:/workspace/models/
```

3. **Create a pod** with vLLM template:
   - GPU: RTX 4090 (24GB) — $0.40/hr community
   - OR A100 40GB — $0.89/hr community
   - Image: `vllm/vllm-openai:latest`
   - Volume mount: `/workspace/models`
   - Expose port: 8000

4. **Start vLLM server** (via RunPod web terminal):
```bash
python -m vllm.entrypoints.openai.api_server \
    --model /workspace/models/quoteforge-mistral-7b-20260405_180000-merged \
    --host 0.0.0.0 \
    --port 8000 \
    --served-model-name quoteforge \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.90
```

5. **Get public URL** from RunPod dashboard (they give you an HTTPS endpoint)

6. **Update QuoteForge backend `.env`:**
```
LLM_BACKEND=vllm
LLM_URL=https://your-runpod-url.runpod.net/v1
LLM_MODEL=quoteforge
```

Your QuoteForge backend now calls the RunPod GPU for inference. **Generation time drops from 60s → 2-3s.**

---

## Stage 3: Docker Container (portable deployment)

### Dockerfile for Model Serving

```dockerfile
FROM vllm/vllm-openai:latest

# Copy the fine-tuned model
COPY ./checkpoints/quoteforge-merged /app/model

# Run vLLM server
CMD ["--model", "/app/model", \
     "--served-model-name", "quoteforge", \
     "--host", "0.0.0.0", \
     "--port", "8000"]
```

### Build and push
```bash
docker build -t quoteforge/model:v1 .
docker push quoteforge/model:v1
```

### Run anywhere
```bash
# Local with GPU
docker run --gpus all -p 8001:8000 quoteforge/model:v1

# AWS g5.xlarge (A10G GPU)
# Deploy to ECS or EKS with this image
```

---

## Stage 4: Enterprise Scale (Kubernetes)

### Example: Deploy on GKE or EKS with GPU node pool

```yaml
# quoteforge-model-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: quoteforge-model
spec:
  replicas: 2  # Scale to N GPUs
  selector:
    matchLabels:
      app: quoteforge-model
  template:
    metadata:
      labels:
        app: quoteforge-model
    spec:
      containers:
      - name: vllm
        image: quoteforge/model:v1
        resources:
          limits:
            nvidia.com/gpu: 1
        ports:
        - containerPort: 8000
---
apiVersion: v1
kind: Service
metadata:
  name: quoteforge-model-svc
spec:
  type: LoadBalancer
  selector:
    app: quoteforge-model
  ports:
  - port: 8000
```

Deploy:
```bash
kubectl apply -f quoteforge-model-deployment.yaml
kubectl scale deployment quoteforge-model --replicas=5  # 5 GPU replicas
```

---

## Cost Comparison

| Setup | Hardware | Cost | Throughput |
|-------|----------|------|------------|
| Local Dev | RTX 3060 | $0/mo (own hardware) | 1-3 req/sec |
| RunPod Community | RTX 4090 | $290/mo (24/7) | 10-20 req/sec |
| RunPod Community | A100 40GB | $640/mo (24/7) | 30-50 req/sec |
| AWS g5.xlarge | A10G 24GB | $730/mo | 10-20 req/sec |
| AWS p4d.24xlarge | 8× A100 | $23,000/mo | 500+ req/sec |

**Rule of thumb:** Each A100 can serve ~100 QuoteForge customers concurrently.

---

## Performance Benchmarks

| Hardware | Model | First Token | Full Response |
|----------|-------|-------------|---------------|
| RTX 3060 (12GB) | Mistral-7B Q4 | 2.1s | 15s |
| RTX 4090 (24GB) | Mistral-7B FP16 | 0.4s | 2.8s |
| A100 40GB | Mistral-7B FP16 | 0.2s | 1.5s |
| A100 80GB | Mistral-7B FP16 | 0.15s | 1.2s |

---

## Monitoring

Add these metrics to your production deployment:

```python
# In the inference client, log:
# - p50/p95/p99 latency
# - Request count by section type
# - Token count per request
# - Error rate
# - GPU utilization
```

Use Grafana + Prometheus for dashboards. RunPod exposes GPU metrics natively.
