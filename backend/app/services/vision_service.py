"""Vision Service — image analysis using Ollama multimodal models (Qwen2.5-VL).

The default model moved off ``llama3.2-vision`` on 2026-08-29. Ollama 0.32.13
dropped the ``mllama`` architecture, so that model is still listed by
``ollama list`` but cannot load at all::

    HTTP 500 {"error":"llama-server process has terminated: exit status 1:
              error loading model: unknown model architecture: 'mllama'"}

Nothing reported it, because every method here caught the failure and returned
it as a *string* — so four endpoints answered with prose that read like an
observation and was really an outage. That is the reason for the two exception
types below: a caller must be able to tell "I looked and here is what I saw"
from "I could not look at all".
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from typing import Any

import httpx

from app.config import get_settings
from app.services.ollama_client import build_ollama_client

settings = get_settings()

_DEFAULT_PROMPT = "Describe this image in detail."


class VisionUnavailableError(RuntimeError):
    """The vision model could not answer — not loaded, not reachable, or silent.

    Never conflate this with a description. A model that will not load is an
    outage, and an outage reported as prose is indistinguishable from a finding.
    """


class VisionImageError(RuntimeError):
    """The image could not be retrieved. The model is not implicated."""


class VisionService:
    """Analyze images using a multimodal LLM via Ollama."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.vision_model
        self.client = build_ollama_client()

    # -- transport -----------------------------------------------------------

    async def _download_image(self, image_url: str) -> bytes:
        """Download an image and return raw bytes."""
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
                return resp.content
        except httpx.HTTPError as exc:
            raise VisionImageError(f"Could not retrieve the image: {exc}") from exc

    async def _ask(
        self,
        prompt: str,
        images: Sequence[bytes],
        *,
        temperature: float = 0.3,
        keep_alive: str | None = None,
    ) -> str:
        """Put one prompt and one or more images to the vision model.

        Every failure path raises. The bytes are base64-encoded here rather than
        by each caller so a caller only ever holds real image data.

        ``keep_alive`` is forwarded to Ollama. A caller that knows it is asking
        once should send ``"0"``: this model is 6.2 GB and Ollama's default is to
        hold it for five more minutes, which on an 8 GB card is five minutes of
        everything else — the browser's own compositor included — fighting for
        what is left of the card.
        """
        encoded = [base64.b64encode(data).decode("utf-8") for data in images]
        extra: dict[str, Any] = {"keep_alive": keep_alive} if keep_alive is not None else {}
        try:
            response = await self.client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt, "images": encoded}],
                options={"temperature": temperature},
                **extra,
            )
        except Exception as exc:
            # Includes the daemon refusing to load the model, which is the exact
            # case that used to be returned as a description.
            raise VisionUnavailableError(f"Vision model {self.model!r} could not answer: {exc}") from exc

        content = (response.get("message", {}) or {}).get("content", "") or ""
        content = content.strip()
        if not content:
            raise VisionUnavailableError(f"Vision model {self.model!r} returned an empty reply.")
        return content

    # -- general analysis ----------------------------------------------------

    async def analyze_image_bytes(
        self,
        data: bytes,
        prompt: str = _DEFAULT_PROMPT,
        *,
        keep_alive: str | None = None,
    ) -> str:
        """Analyze image bytes already in hand.

        The primitive the URL-taking methods are built on. A browser screenshot
        never has a URL, so routing it through ``analyze_image`` would mean
        writing it to disk and serving it back to ourselves.

        ``keep_alive`` forwards to Ollama — see :meth:`_ask`.
        """
        if not data:
            raise VisionImageError("No image data supplied.")
        return await self._ask(prompt, [data], keep_alive=keep_alive)

    async def analyze_image(self, image_url: str, prompt: str = _DEFAULT_PROMPT) -> str:
        """General-purpose image analysis.

        Args:
            image_url: URL of the image to analyze
            prompt: The question/instruction for the vision model

        Returns:
            The model's text response describing the image

        Raises:
            VisionImageError: the image could not be fetched
            VisionUnavailableError: the model could not answer
        """
        return await self.analyze_image_bytes(await self._download_image(image_url), prompt)

    # -- OSINT-focused analysis ----------------------------------------------

    async def analyze_social_photo(self, image_url: str) -> dict[str, Any]:
        """OSINT-focused image analysis — extract intelligence from social media photos.

        Returns:
            dict with keys: description, location_clues, text_detected, people_count,
                           objects, mood, osint_notes
        """
        prompt = """You are an OSINT (Open Source Intelligence) analyst examining a social media photo.
Analyze this image and provide intelligence in the following structured format:

DESCRIPTION: (What is shown in the image)
LOCATION CLUES: (Any geographical indicators — landmarks, signs, language on signs, vegetation, architecture style, climate indicators)
TEXT DETECTED: (Any visible text, signs, labels, watermarks, usernames)
PEOPLE: (Number of people, estimated age range, notable appearance details)
OBJECTS: (Notable objects, vehicles, equipment, brands visible)
MOOD/CONTEXT: (Social context — event type, activity, time of day estimate)
OSINT NOTES: (Any intelligence-relevant observations — security cameras, uniforms, restricted areas, metadata indicators)

Be precise and factual. Only report what you can actually see."""

        raw = await self.analyze_image(image_url, prompt)
        return _parse_structured(raw)

    async def read_screenshot(self, image_url: str) -> str:
        """OCR-like extraction from screenshots — read all visible text."""
        return await self.analyze_image(image_url, _SCREENSHOT_PROMPT)

    async def read_screenshot_bytes(self, data: bytes) -> str:
        """OCR-like extraction from a screenshot already in memory.

        What the browse tier calls when DOM extraction came back empty.
        """
        return await self.analyze_image_bytes(data, _SCREENSHOT_PROMPT)

    async def compare_faces_visual(self, image_url_a: str, image_url_b: str) -> str:
        """Visual comparison of two face images (supplement to DeepFace)."""
        prompt = """Compare the two people in these images.
Describe:
1. Physical similarities and differences
2. Estimated age, gender, ethnicity
3. Your confidence level that these are the same person (LOW/MEDIUM/HIGH)
4. Notable distinguishing features"""

        img_a = await self._download_image(image_url_a)
        img_b = await self._download_image(image_url_b)
        return await self._ask(prompt, [img_a, img_b], temperature=0.2)


_SCREENSHOT_PROMPT = """Read and extract ALL visible text from this screenshot/image.
Return the text exactly as it appears, maintaining the layout structure.
If there are UI elements, labels, or buttons, include those too.
Focus on accuracy — do not guess or infer text that isn't clearly visible."""


_SOCIAL_KEYS: dict[str, str] = {
    "DESCRIPTION": "description",
    "LOCATION CLUES": "location_clues",
    "TEXT DETECTED": "text_detected",
    "PEOPLE": "people_count",
    "OBJECTS": "objects",
    "MOOD/CONTEXT": "mood",
    "OSINT NOTES": "osint_notes",
}


def _parse_structured(raw: str) -> dict[str, Any]:
    """Split the labelled reply into fields, keeping the raw text alongside.

    The raw text is retained because the parse is prefix-based: a model that
    renames a heading would otherwise drop a whole section without trace.
    """
    result: dict[str, Any] = {key: "" for key in _SOCIAL_KEYS.values()}
    result["raw_analysis"] = raw

    current_key = ""
    for line in raw.split("\n"):
        line = line.strip()
        matched = False
        for prefix, key in _SOCIAL_KEYS.items():
            if line.upper().startswith(prefix):
                current_key = key
                result[current_key] = line.split(":", 1)[1].strip() if ":" in line else ""
                matched = True
                break
        if not matched and current_key:
            result[current_key] = f"{result[current_key]} {line}".strip()

    for key, value in result.items():
        if isinstance(value, str):
            result[key] = value.strip()
    return result


vision_service = VisionService()

__all__ = [
    "VisionImageError",
    "VisionService",
    "VisionUnavailableError",
    "vision_service",
]
