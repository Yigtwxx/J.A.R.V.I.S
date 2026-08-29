"""Avatar handling: download, fingerprint, and reverse-image lookup.

Image comparison here is byte- and gradient-level only. No face detection, no
face embeddings, no biometric matching — see ``hashing`` for the full statement.
"""

from app.discovery.media.hashing import (
    dhash64,
    hamming,
    image_dimensions,
    is_near_duplicate,
    sha256_bytes,
)
from app.discovery.media.reverse import ReverseHit, ReverseImageSearcher, is_generic_image
from app.discovery.media.store import AvatarStore, StoredAvatar, sniff_image

__all__ = [
    "AvatarStore",
    "ReverseHit",
    "ReverseImageSearcher",
    "StoredAvatar",
    "dhash64",
    "hamming",
    "image_dimensions",
    "is_generic_image",
    "is_near_duplicate",
    "sha256_bytes",
    "sniff_image",
]
