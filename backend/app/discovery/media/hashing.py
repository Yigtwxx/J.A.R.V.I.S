"""Image fingerprinting for avatar comparison.

**This is file/image comparison, NOT face recognition.** Everything here works on
image *bytes* and on coarse pixel gradients: ``sha256_bytes`` answers "is this the
identical file?" and ``dhash64`` answers "does this look like the same picture
after a resize or a re-encode?". No face is ever detected, no face vector is ever
extracted, and no biometric template is ever produced or stored. Biometric
identification is deliberately out of scope for this pipeline — the discovery
layer corroborates identities from public text and links, and an avatar is only
ever a *file-level* corroborator ("the same picture is used on both accounts").

Design notes:

* ``dhash64`` is a 64-bit difference hash: the image is reduced to 9x8 greyscale
  and each pixel is compared with its right-hand neighbour. It is invariant to
  scaling, mild compression and small brightness shifts, and it is *not* an
  identity claim on its own — a stock photo also matches itself everywhere.
* Every function returns gracefully on unreadable input (``""`` / ``64`` /
  ``False`` / ``None``) and never raises: a corrupt avatar must not abort a search.
"""

from __future__ import annotations

import hashlib
from io import BytesIO

from PIL import Image

# 9x8 greyscale -> 8 horizontal comparisons per row across 8 rows = 64 bits.
_DHASH_SIZE = (9, 8)
_HASH_BITS = 64
_HEX_LENGTH = _HASH_BITS // 4
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of the raw bytes. Empty input yields the digest of b""."""
    if not isinstance(data, bytes | bytearray | memoryview):
        return ""
    return hashlib.sha256(bytes(data)).hexdigest()


def dhash64(data: bytes) -> str:
    """64-bit difference hash as 16 hex chars, or ``""`` when unreadable.

    The bit order is fixed: rows top to bottom, columns left to right, most
    significant bit first, so two hashes are always comparable.
    """
    if not data:
        return ""
    try:
        with Image.open(BytesIO(bytes(data))) as image:
            greyscale = image.convert("L").resize(_DHASH_SIZE, Image.Resampling.LANCZOS)
            pixels = list(greyscale.getdata())
    except Exception:
        # Truncated download, an HTML error page, an unsupported codec, a
        # decompression bomb — all of them mean "no hash", never a crash.
        return ""
    width, height = _DHASH_SIZE
    if len(pixels) < width * height:
        return ""

    bits = 0
    for row in range(height):
        offset = row * width
        for column in range(width - 1):
            bits <<= 1
            if pixels[offset + column + 1] > pixels[offset + column]:
                bits |= 1
    return f"{bits:0{_HEX_LENGTH}x}"


def hamming(a: str, b: str) -> int:
    """Bit distance between two hex dhash strings. ``64`` on malformed input.

    Returning the maximum distance (rather than raising or returning 0) makes a
    malformed hash behave as "nothing like it", which is the safe direction: a
    broken hash can never manufacture a match.
    """
    left = _as_int(a)
    right = _as_int(b)
    if left is None or right is None:
        return _HASH_BITS
    return (left ^ right).bit_count()


def is_near_duplicate(a: str, b: str, *, threshold: int = 6) -> bool:
    """True when two dhashes are within ``threshold`` bits of each other.

    6/64 bits is the usual working point: it survives a resize and a JPEG
    re-encode while still separating two genuinely different photographs.
    """
    return hamming(a, b) <= max(0, threshold)


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    """``(width, height)`` of the image, or None when the bytes are not an image."""
    if not data:
        return None
    try:
        with Image.open(BytesIO(bytes(data))) as image:
            width, height = image.size
    except Exception:
        return None
    if not width or not height:
        return None
    return int(width), int(height)


def _as_int(value: str) -> int | None:
    """Parse a 16-char hex dhash. None for anything else."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) != _HEX_LENGTH or not all(character in _HEX_DIGITS for character in text):
        return None
    try:
        return int(text, 16)
    except ValueError:
        return None
