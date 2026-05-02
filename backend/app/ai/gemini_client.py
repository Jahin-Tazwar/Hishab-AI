"""
HishabAI Backend — Vertex AI (Gemini) Client

Wrapper for Google Vertex AI Gemini 2.5 Flash.
Used for document extraction, notice drafting, and classification.
"""

import json
import structlog
from typing import Any, Optional

from google import genai
from google.genai import types

from app.config import settings

logger = structlog.get_logger()

# Module-level client (initialized lazily)
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Get or create the Vertex AI Gemini client."""
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        )
    return _client


async def generate_text(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> str:
    """
    Generate text using Gemini 2.5 Flash.

    Args:
        system_prompt: System-level instructions (role, rules, format)
        user_prompt: The actual user query/data to process
        temperature: Creativity control (0.0–1.0). Use 0.2 for legal/financial tasks.
        max_tokens: Maximum output tokens

    Returns:
        Generated text string

    Raises:
        RuntimeError on API failures after retries
    """
    client = _get_client()

    try:
        response = client.models.generate_content(
            model=settings.VERTEX_AI_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )

        result = response.text or ""

        # Log token usage for billing tracking
        if response.usage_metadata:
            logger.info(
                "vertex_ai_usage",
                model=settings.VERTEX_AI_MODEL,
                input_tokens=response.usage_metadata.prompt_token_count,
                output_tokens=response.usage_metadata.candidates_token_count,
                total_tokens=response.usage_metadata.total_token_count,
            )

        return result

    except Exception as e:
        logger.error("vertex_ai_error", error=str(e), model=settings.VERTEX_AI_MODEL)
        raise RuntimeError(f"Gemini API call failed: {e}") from e


async def extract_structured(
    prompt: str,
    output_schema: dict[str, Any],
    system_prompt: str = "",
    fallback: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Ask Gemini to return structured JSON matching the given schema.

    Args:
        prompt: The extraction prompt with data
        output_schema: Expected JSON structure description
        system_prompt: Additional system instructions
        fallback: Default value if extraction fails

    Returns:
        Parsed dict matching the schema, or fallback on failure
    """
    schema_instruction = (
        f"Respond with ONLY valid JSON matching this schema. "
        f"No explanation, no markdown code blocks.\n\n"
        f"Schema: {json.dumps(output_schema, indent=2)}"
    )

    full_system = f"{system_prompt}\n\n{schema_instruction}" if system_prompt else schema_instruction

    try:
        text = await generate_text(
            system_prompt=full_system,
            user_prompt=prompt,
            temperature=0.1,  # Very low for structured extraction
        )

        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        return json.loads(text)

    except (json.JSONDecodeError, RuntimeError) as e:
        logger.warning(
            "structured_extraction_failed",
            error=str(e),
            fallback_used=fallback is not None,
        )
        if fallback is not None:
            return fallback
        raise
