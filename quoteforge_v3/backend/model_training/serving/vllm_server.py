"""
QuoteForge vLLM Inference Server
==================================
Production inference server using vLLM (2-3x faster than Ollama).

vLLM advantages:
  - PagedAttention for efficient memory usage
  - Continuous batching for high throughput
  - OpenAI-compatible API
  - Tensor parallelism for multi-GPU scaling

Requirements:
  pip install vllm

Usage:
  # Serve a fine-tuned model
  python vllm_server.py --model ./checkpoints/quoteforge-mistral-7b-20260405/

  # Serve base model (no fine-tuning)
  python vllm_server.py --model mistralai/Mistral-7B-Instruct-v0.3

  # Multi-GPU tensor parallelism
  python vllm_server.py --model ./checkpoints/... --tensor-parallel-size 2
"""
import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def serve(
    model_path: str,
    host: str = "0.0.0.0",
    port: int = 8001,
    tensor_parallel_size: int = 1,
    max_model_len: int = 4096,
    gpu_memory_utilization: float = 0.90,
):
    """Start vLLM OpenAI-compatible server."""
    try:
        from vllm.entrypoints.openai.api_server import run_server
        from vllm.entrypoints.openai.cli_args import make_arg_parser
    except ImportError:
        logger.error("vLLM not installed. Install with: pip install vllm")
        logger.error("Note: vLLM requires CUDA. Not supported on Mac.")
        sys.exit(1)

    # Build vLLM args
    args_list = [
        "--model", model_path,
        "--host", host,
        "--port", str(port),
        "--tensor-parallel-size", str(tensor_parallel_size),
        "--max-model-len", str(max_model_len),
        "--gpu-memory-utilization", str(gpu_memory_utilization),
        "--served-model-name", "quoteforge",
        "--dtype", "float16",
    ]

    parser = make_arg_parser()
    args = parser.parse_args(args_list)

    logger.info(f"Starting vLLM server on {host}:{port}")
    logger.info(f"Model: {model_path}")
    logger.info(f"Tensor parallel: {tensor_parallel_size}")
    logger.info(f"Max sequence length: {max_model_len}")

    run_server(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QuoteForge vLLM Server")
    parser.add_argument("--model", required=True, help="Path to model or HF ID")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--tensor-parallel-size", type=int, default=1, help="Number of GPUs")
    parser.add_argument("--max-model-len", type=int, default=4096)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.90)
    args = parser.parse_args()

    serve(
        model_path=args.model,
        host=args.host,
        port=args.port,
        tensor_parallel_size=args.tensor_parallel_size,
        max_model_len=args.max_model_len,
        gpu_memory_utilization=args.gpu_memory_utilization,
    )
