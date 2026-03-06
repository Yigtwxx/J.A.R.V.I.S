import os
import tempfile
import logging
from typing import Optional
from io import BytesIO

import requests
from PIL import Image

from app.utils.logger import logger

# Suppress noisy tensorflow/deepface logs
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
logging.getLogger("tensorflow").setLevel(logging.ERROR)


class FaceMatchingService:
    """
    Downloads profile images from different platforms and compares faces
    using DeepFace to produce identity confidence scores.
    """

    DOWNLOAD_TIMEOUT = 10  # seconds per image
    MODEL_NAME = "Facenet512"
    DETECTOR_BACKEND = "opencv"  # fast & reliable
    DISTANCE_METRIC = "cosine"
    # Facenet512 cosine threshold (from DeepFace defaults)
    THRESHOLD = 0.30

    def download_image(self, url: str) -> Optional[str]:
        """
        Download an image from URL and save to a temp file.
        Returns the temp file path, or None on failure.
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(url, headers=headers, timeout=self.DOWNLOAD_TIMEOUT, stream=True)
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")
            if "image" not in content_type and not url.endswith((".jpg", ".jpeg", ".png", ".webp")):
                return None

            # Read into PIL to validate and convert
            img_data = BytesIO(response.content)
            img = Image.open(img_data)

            # Skip very small images (likely placeholders/icons)
            if img.width < 50 or img.height < 50:
                return None

            # Convert to RGB if necessary (e.g. RGBA, P mode)
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Save to temp file
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            img.save(tmp, format="JPEG", quality=95)
            tmp.close()
            return tmp.name

        except Exception as e:
            logger.log_warning(f"Face match: Failed to download image from {url[:60]}...: {e}")
            return None

    def compare_faces(self, img_path_a: str, img_path_b: str, label_a: str, label_b: str) -> Optional[dict]:
        """
        Compare two face images using DeepFace.
        Returns a result dict or None if comparison fails.
        """
        try:
            from deepface import DeepFace

            result = DeepFace.verify(
                img1_path=img_path_a,
                img2_path=img_path_b,
                model_name=self.MODEL_NAME,
                detector_backend=self.DETECTOR_BACKEND,
                distance_metric=self.DISTANCE_METRIC,
                enforce_detection=False,  # Don't crash if no face found
            )

            distance = result.get("distance", 1.0)
            threshold = result.get("threshold", self.THRESHOLD)
            verified = result.get("verified", False)

            # Convert distance to a 0–100 confidence score
            # For cosine: distance 0 = identical, threshold ≈ 0.30
            # Confidence = max(0, (1 - distance/threshold)) * 100, capped at 100
            if threshold > 0:
                raw_confidence = max(0.0, (1.0 - distance / threshold)) * 100
            else:
                raw_confidence = 100.0 if distance == 0 else 0.0

            confidence = min(100.0, round(raw_confidence, 1))

            return {
                "image_a_label": label_a,
                "image_b_label": label_b,
                "verified": verified,
                "confidence": confidence,
                "distance": round(distance, 4),
            }

        except Exception as e:
            logger.log_warning(f"Face match: Comparison failed ({label_a} vs {label_b}): {e}")
            return None

    def analyze_all_images(self, labeled_images: list[tuple[str, str]]) -> Optional[dict]:
        """
        Download all images, perform pairwise face comparison, return a report.

        Args:
            labeled_images: list of (label, url) tuples, e.g. [("GitHub", "https://..."), ...]

        Returns:
            FaceMatchReport dict or None if insufficient images.
        """
        if len(labeled_images) < 2:
            return None

        logger.log_action(f"Face matching: Processing {len(labeled_images)} profile images...")

        # Download all images
        downloaded = []  # list of (label, file_path)
        for label, url in labeled_images:
            path = self.download_image(url)
            if path:
                downloaded.append((label, path))
                logger.log_success(f"Face match: Downloaded {label} image")
            else:
                logger.log_warning(f"Face match: Skipped {label} (download failed or invalid image)")

        if len(downloaded) < 2:
            # Cleanup
            for _, path in downloaded:
                self._cleanup_file(path)
            logger.log_warning("Face match: Insufficient valid images for comparison")
            return None

        # Pairwise comparisons
        pairs = []
        for i in range(len(downloaded)):
            for j in range(i + 1, len(downloaded)):
                label_a, path_a = downloaded[i]
                label_b, path_b = downloaded[j]
                result = self.compare_faces(path_a, path_b, label_a, label_b)
                if result:
                    pairs.append(result)

        # Cleanup temp files
        for _, path in downloaded:
            self._cleanup_file(path)

        if not pairs:
            logger.log_warning("Face match: No successful comparisons")
            return {
                "overall_confidence": 0.0,
                "total_comparisons": len(downloaded) * (len(downloaded) - 1) // 2,
                "successful_comparisons": 0,
                "pairs": [],
                "face_detected_count": len(downloaded),
                "total_images": len(labeled_images),
            }

        # Calculate overall confidence (average of all successful pairs)
        avg_confidence = round(sum(p["confidence"] for p in pairs) / len(pairs), 1)

        report = {
            "overall_confidence": avg_confidence,
            "total_comparisons": len(downloaded) * (len(downloaded) - 1) // 2,
            "successful_comparisons": len(pairs),
            "pairs": pairs,
            "face_detected_count": len(downloaded),
            "total_images": len(labeled_images),
        }

        logger.log_success(
            f"Face matching complete: {len(pairs)} comparison(s), "
            f"overall confidence: {avg_confidence}%"
        )

        return report

    def _cleanup_file(self, path: str):
        """Safely remove a temp file."""
        try:
            if path and os.path.exists(path):
                os.unlink(path)
        except Exception:
            pass
