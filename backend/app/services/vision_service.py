"""Vision Service — image analysis using Ollama multimodal models (LLaVA / Llama 3.2-Vision)."""

from __future__ import annotations

import base64
from typing import Any

import httpx
import ollama

from app.config import get_settings
from app.utils.logger import logger

settings = get_settings()


class VisionService:
    """Analyze images using a multimodal LLM via Ollama."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.vision_model
        self.client = ollama.AsyncClient()

    async def _download_image(self, image_url: str) -> bytes:
        """Download an image and return raw bytes."""
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            return resp.content

    async def analyze_image(self, image_url: str, prompt: str = "Describe this image in detail.") -> str:
        """General-purpose image analysis.

        Args:
            image_url: URL of the image to analyze
            prompt: The question/instruction for the vision model

        Returns:
            The model's text response describing the image
        """
        try:
            image_bytes = await self._download_image(image_url)
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")

            response = await self.client.chat(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }],
                options={"temperature": 0.3},
            )
            return response.get("message", {}).get("content", "No response generated.")

        except Exception as exc:
            logger.log_error(f"Vision analysis failed: {exc}")
            return f"Vision analysis error: {exc}"

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

        try:
            raw = await self.analyze_image(image_url, prompt)

            result: dict[str, Any] = {
                "description": "",
                "location_clues": "",
                "text_detected": "",
                "people_count": "",
                "objects": "",
                "mood": "",
                "osint_notes": "",
                "raw_analysis": raw,
            }

            # Parse structured response
            current_key = ""
            key_map = {
                "DESCRIPTION": "description",
                "LOCATION CLUES": "location_clues",
                "TEXT DETECTED": "text_detected",
                "PEOPLE": "people_count",
                "OBJECTS": "objects",
                "MOOD/CONTEXT": "mood",
                "OSINT NOTES": "osint_notes",
            }

            for line in raw.split("\n"):
                line = line.strip()
                matched = False
                for prefix, key in key_map.items():
                    if line.upper().startswith(prefix):
                        current_key = key
                        value = line.split(":", 1)[1].strip() if ":" in line else ""
                        result[current_key] = value
                        matched = True
                        break
                if not matched and current_key:
                    result[current_key] += " " + line

            # Clean up whitespace
            for k in result:
                if isinstance(result[k], str):
                    result[k] = result[k].strip()

            return result

        except Exception as exc:
            logger.log_error(f"Social photo analysis failed: {exc}")
            return {"error": str(exc), "raw_analysis": ""}

    async def read_screenshot(self, image_url: str) -> str:
        """OCR-like extraction from screenshots — read all visible text."""
        prompt = """Read and extract ALL visible text from this screenshot/image.
Return the text exactly as it appears, maintaining the layout structure.
If there are UI elements, labels, or buttons, include those too.
Focus on accuracy — do not guess or infer text that isn't clearly visible."""

        return await self.analyze_image(image_url, prompt)

    async def compare_faces_visual(self, image_url_a: str, image_url_b: str) -> str:
        """Visual comparison of two face images (supplement to DeepFace)."""
        prompt = """Compare the two people in these images.
Describe:
1. Physical similarities and differences
2. Estimated age, gender, ethnicity
3. Your confidence level that these are the same person (LOW/MEDIUM/HIGH)
4. Notable distinguishing features"""

        try:
            img_a = await self._download_image(image_url_a)
            img_b = await self._download_image(image_url_b)

            response = await self.client.chat(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": prompt,
                    "images": [
                        base64.b64encode(img_a).decode("utf-8"),
                        base64.b64encode(img_b).decode("utf-8"),
                    ],
                }],
                options={"temperature": 0.2},
            )
            return response.get("message", {}).get("content", "No comparison generated.")

        except Exception as exc:
            logger.log_error(f"Visual face comparison failed: {exc}")
            return f"Face comparison error: {exc}"


vision_service = VisionService()
