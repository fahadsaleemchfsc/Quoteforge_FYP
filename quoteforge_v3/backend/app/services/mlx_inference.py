"""
MLX Inference Service — Apple Silicon native AI generation.
Uses your fine-tuned Llama model trained on QuoteForge data.
"""
import os
import logging
from pathlib import Path
from typing import Optional

# Ensure .env is loaded before reading env vars
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_BASE_MODEL = "mlx-community/Llama-3.2-1B-Instruct-4bit"
DEFAULT_ADAPTER = BASE_DIR / "model_training" / "mlx_output" / "quoteforge-v2"

# Cache loaded model (avoids reloading every request)
_model = None
_tokenizer = None


def _load_model():
    """Load the fine-tuned MLX model (cached)."""
    global _model, _tokenizer

    if _model is not None:
        return _model, _tokenizer

    try:
        from mlx_lm import load
    except ImportError:
        logger.warning("mlx_lm not installed — MLX inference unavailable")
        return None, None

    adapter_path = os.getenv("MLX_ADAPTER_PATH", str(DEFAULT_ADAPTER))
    base_model = os.getenv("MLX_BASE_MODEL", DEFAULT_BASE_MODEL)

    if not Path(adapter_path).exists():
        logger.info(f"No fine-tuned adapter at {adapter_path} — using base model")
        adapter_path = None

    try:
        logger.info(f"Loading MLX model: {base_model}")
        if adapter_path:
            logger.info(f"  With adapter: {adapter_path}")
            _model, _tokenizer = load(base_model, adapter_path=adapter_path)
        else:
            _model, _tokenizer = load(base_model)
        logger.info("MLX model loaded successfully")
        return _model, _tokenizer
    except Exception as e:
        logger.error(f"Failed to load MLX model: {e}")
        return None, None


async def generate_mlx(prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
    """Generate text using fine-tuned MLX model."""
    try:
        from mlx_lm import generate
    except ImportError:
        return ""

    model, tokenizer = _load_model()
    if model is None:
        return ""

    # Format with chat template
    messages = [
        {"role": "system", "content": "You are QuoteForge, a professional B2B proposal writer."},
        {"role": "user", "content": prompt},
    ]
    try:
        formatted = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception:
        formatted = prompt

    try:
        # MLX generate is synchronous; run it
        text = generate(
            model,
            tokenizer,
            prompt=formatted,
            max_tokens=max_tokens,
            verbose=False,
        )
        return text.strip()
    except Exception as e:
        logger.error(f"MLX generation failed: {e}")
        return ""


def check_mlx_available() -> dict:
    """Check MLX availability and adapter status."""
    status = {
        "backend": "mlx",
        "available": False,
        "base_model": os.getenv("MLX_BASE_MODEL", DEFAULT_BASE_MODEL),
    }

    try:
        import mlx_lm
        status["mlx_installed"] = True
    except ImportError:
        status["mlx_installed"] = False
        return status

    adapter_path = Path(os.getenv("MLX_ADAPTER_PATH", str(DEFAULT_ADAPTER)))
    status["adapter_path"] = str(adapter_path)
    status["adapter_exists"] = adapter_path.exists()

    if adapter_path.exists():
        safetensors = list(adapter_path.glob("*.safetensors"))
        status["adapter_files"] = len(safetensors)

    status["available"] = status["mlx_installed"]
    return status
