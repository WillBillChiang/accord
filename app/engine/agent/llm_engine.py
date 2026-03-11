"""
LLM inference engine using llama.cpp with GPU acceleration.

Wraps llama-cpp-python for running quantized language models inside
the GCP Confidential VM. With GPU support (NVIDIA L4/H100), inference
runs on CUDA with full GPU offloading for significantly faster
response times compared to CPU-only inference.
"""
import json
import logging
from typing import Optional

from config import MODEL_PATH

logger = logging.getLogger(__name__)

# Type stub for when llama_cpp is not installed (testing)
try:
    from llama_cpp import Llama
except ImportError:
    Llama = None  # type: ignore
    logger.warning("llama_cpp not available — LLM inference disabled")


class LLMEngine:
    """
    Wrapper around llama.cpp for negotiation agent inference.

    Runs quantized models inside the Confidential VM with GPU
    acceleration via CUDA. Uses structured JSON output for reliable
    proposal generation.
    """

    def __init__(
        self,
        model_path: str = MODEL_PATH,
        n_ctx: int = 8192,
        n_gpu_layers: int = -1,  # -1 = offload all layers to GPU
        temperature: float = 0.3,
    ) -> None:
        self.model_path = model_path
        self.temperature = temperature
        self._model: Optional[object] = None

        if Llama is not None:
            try:
                self._model = Llama(
                    model_path=model_path,
                    n_ctx=n_ctx,
                    n_gpu_layers=n_gpu_layers,
                    verbose=False,
                )
                logger.info(
                    f"LLM loaded: {model_path}, ctx={n_ctx}, "
                    f"gpu_layers={n_gpu_layers}"
                )
            except Exception as e:
                logger.error(f"Failed to load LLM model: {e}")
                self._model = None
        else:
            logger.warning("Running without LLM — using fallback strategy")

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1024,
    ) -> Optional[dict]:
        """
        Generate a JSON response from the LLM.

        Returns parsed dict or None if generation/parsing fails.
        """
        if self._model is None:
            logger.warning("No LLM model available, returning None")
            return None

        try:
            response = self._model.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = response["choices"][0]["message"]["content"]
            return json.loads(content)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"LLM output parsing failed: {e}")
            return None
        except Exception as e:
            logger.error(f"LLM inference error: {e}")
            return None

    @property
    def is_available(self) -> bool:
        """Check if LLM model is loaded and ready."""
        return self._model is not None
