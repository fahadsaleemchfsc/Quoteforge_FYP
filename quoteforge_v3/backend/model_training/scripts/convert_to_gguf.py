"""
Convert merged HuggingFace model to GGUF format for Ollama.

GGUF advantages:
  - 4x smaller file size via quantization
  - 2-3x faster inference on CPU
  - Native Ollama support
  - Works on any hardware

Requirements:
  git clone https://github.com/ggerganov/llama.cpp
  cd llama.cpp
  make
  pip install -r requirements.txt
"""
import argparse
import subprocess
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def convert(model_path: str, quantization: str = "Q4_K_M", llama_cpp_dir: str = None):
    """Convert a HuggingFace model to GGUF with quantization."""
    model_path = Path(model_path).resolve()

    # Find llama.cpp
    if not llama_cpp_dir:
        # Look for it in common locations
        candidates = [
            Path.home() / "llama.cpp",
            Path("/opt/llama.cpp"),
            model_path.parent.parent / "llama.cpp",
        ]
        for c in candidates:
            if c.exists() and (c / "convert-hf-to-gguf.py").exists():
                llama_cpp_dir = c
                break

    if not llama_cpp_dir:
        logger.error("llama.cpp not found. Install it first:")
        logger.error("  git clone https://github.com/ggerganov/llama.cpp ~/llama.cpp")
        logger.error("  cd ~/llama.cpp && make")
        logger.error("  pip install -r ~/llama.cpp/requirements.txt")
        return

    llama_cpp_dir = Path(llama_cpp_dir)
    convert_script = llama_cpp_dir / "convert-hf-to-gguf.py"
    quantize_bin = llama_cpp_dir / "build" / "bin" / "llama-quantize"
    if not quantize_bin.exists():
        quantize_bin = llama_cpp_dir / "llama-quantize"
    if not quantize_bin.exists():
        quantize_bin = llama_cpp_dir / "quantize"

    # Step 1: Convert to F16 GGUF
    f16_output = model_path.with_suffix(".f16.gguf")
    logger.info(f"Step 1: Converting to F16 GGUF...")
    logger.info(f"  Input: {model_path}")
    logger.info(f"  Output: {f16_output}")

    subprocess.run([
        "python", str(convert_script),
        str(model_path),
        "--outfile", str(f16_output),
        "--outtype", "f16",
    ], check=True)

    # Step 2: Quantize
    quantized_output = model_path.with_suffix(f".{quantization}.gguf")
    logger.info(f"Step 2: Quantizing to {quantization}...")
    logger.info(f"  Output: {quantized_output}")

    subprocess.run([
        str(quantize_bin),
        str(f16_output),
        str(quantized_output),
        quantization,
    ], check=True)

    # Clean up F16 file (it's huge)
    f16_output.unlink()

    logger.info(f"✅ GGUF model saved: {quantized_output}")
    logger.info(f"")
    logger.info(f"To use with Ollama, create a Modelfile:")

    modelfile_content = f"""FROM {quantized_output}
TEMPLATE \"\"\"{{{{ if .System }}}}<|system|>
{{{{ .System }}}}<|end|>
{{{{ end }}}}{{{{ if .Prompt }}}}<|user|>
{{{{ .Prompt }}}}<|end|>
<|assistant|>
{{{{ end }}}}{{{{ .Response }}}}<|end|>\"\"\"
PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER num_ctx 4096
SYSTEM \"\"\"You are QuoteForge, a professional B2B proposal writer.\"\"\"
"""
    modelfile_path = model_path.parent / "Modelfile"
    modelfile_path.write_text(modelfile_content)

    logger.info(f"  Modelfile saved: {modelfile_path}")
    logger.info(f"")
    logger.info(f"Then import into Ollama:")
    logger.info(f"  ollama create quoteforge -f {modelfile_path}")
    logger.info(f"  ollama run quoteforge")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True, help="Path to merged HF model")
    parser.add_argument("--quantization", default="Q4_K_M",
                        choices=["Q4_0", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"],
                        help="Quantization level (Q4_K_M is good balance)")
    parser.add_argument("--llama-cpp-dir", default=None, help="Path to llama.cpp")
    args = parser.parse_args()
    convert(args.model_path, args.quantization, args.llama_cpp_dir)
