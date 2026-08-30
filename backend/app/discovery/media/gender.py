"""Estimating, from a profile picture, whether it shows a man or a woman.

**Scope, precisely.** This describes *an image*. It does not identify anyone, it
never compares two faces, and it produces no template that could be used to
recognise a person elsewhere. That distinction is why this module reaches for the
local vision model and not for
``app.services.face_matching_service`` — biometric identification stays out of
the discovery package, and ``tests/discovery/test_service_integration.py`` keeps
it that way.

**Why a vision model rather than a gender classifier.** A profile picture is very
often not a portrait: a logo, a cartoon, a cat, a landscape, a car, a group
photo. A classifier answers "male" for all of them with high confidence, because
answering is all it can do. A vision model can say *there is no face here*, and
that answer is worth more than the classification, because it is what stops the
right person being thrown away over a picture of their dog.

**Why the guards are so tight.** A reading only ever removes a candidate, and a
wrong removal is the one failure this pipeline is built to avoid. So a reading is
actionable only when the model saw exactly one face and said so confidently;
every other outcome — no face, several faces, an unsure answer, an unreachable
daemon — changes nothing at all.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Final

from app.discovery.types import Gender
from app.services.llm_json import generate_json

MIN_CONFIDENCE: Final[float] = 0.75
"""Default floor. Below it a reading is recorded but never acted on."""

_PROMPT: Final[str] = (
    "You are looking at one profile picture from a social media account.\n"
    "Answer only about what is visibly in the image. Do not guess.\n\n"
    "Rules:\n"
    "- has_face: true only if at least one real human face is visible. A logo, an "
    "illustration, a cartoon or anime character, an animal, an object, a landscape, "
    "text, or a blank/default avatar all mean false.\n"
    "- face_count: how many distinct real human faces are visible. 0 if none.\n"
    '- gender: "male" or "female" only if exactly one human face is visible AND the '
    'presentation is clearly one or the other. Otherwise answer "unclear".\n'
    "- confidence: 0.0 to 1.0, how sure you are of the gender answer specifically. "
    "Use a low value whenever the face is small, blurred, turned away, heavily "
    'filtered, obscured, or ambiguous. Answer "unclear" with confidence 0.0 rather '
    "than guessing."
)

_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "has_face": {"type": "boolean"},
        "face_count": {"type": "integer", "minimum": 0},
        "gender": {"type": "string", "enum": ["male", "female", "unclear"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["has_face", "face_count", "gender", "confidence"],
}

_GENDER_WORDS: Final[dict[str, Gender]] = {"male": Gender.MALE, "female": Gender.FEMALE}


def describe_gender(gender: Gender) -> str:
    """The phrase a score reason uses for a gender read off a picture.

    A thin alias for ``Gender.description``, which lives on the enum so the
    scorer can render an exclusion without importing this module — doing so
    pulls in the LLM client below it and closes an import cycle.
    """
    return gender.description


@dataclass(frozen=True, slots=True)
class AvatarGenderReading:
    """What the model made of one picture. Every field is what it claimed, not a verdict."""

    has_face: bool
    face_count: int
    gender: Gender
    confidence: float

    def is_actionable(self, *, min_confidence: float = MIN_CONFIDENCE) -> bool:
        """Whether this reading is solid enough to remove a candidate over.

        All four conditions, deliberately. Two faces mean we cannot tell which one
        the account belongs to; no face means the picture says nothing about a
        person at all; and an unsure answer is not an answer.
        """
        return self.has_face and self.face_count == 1 and self.gender.is_stated and self.confidence >= min_confidence

    def contradicts(self, stated: Gender, *, min_confidence: float = MIN_CONFIDENCE) -> bool:
        """Whether this picture argues against the gender the user gave."""
        return self.is_actionable(min_confidence=min_confidence) and stated.contradicts(self.gender)

    def describe(self) -> str:
        """How the reading reads in a score reason: "a man" / "a woman"."""
        return describe_gender(self.gender)


def _coerce(payload: dict[str, Any]) -> AvatarGenderReading | None:
    """Turn the model's JSON into a reading, or None when it is not usable.

    Constrained decoding makes malformed output rare rather than impossible, and
    a reading that is quietly wrong here would remove the wrong account.
    """
    try:
        face_count = int(payload.get("face_count") or 0)
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return None

    word = str(payload.get("gender") or "").strip().lower()
    gender = _GENDER_WORDS.get(word, Gender.UNKNOWN)
    has_face = bool(payload.get("has_face"))

    # A model that says "no face" and then names a gender has contradicted
    # itself; believing the more convenient half is how a bad exclusion happens.
    if not has_face or face_count <= 0:
        return AvatarGenderReading(has_face=False, face_count=max(0, face_count), gender=Gender.UNKNOWN, confidence=0.0)

    return AvatarGenderReading(
        has_face=True,
        face_count=face_count,
        gender=gender,
        confidence=min(1.0, max(0.0, confidence)),
    )


async def read_avatar_gender(
    data: bytes,
    *,
    model: str | None = None,
    timeout_s: float | None = None,
    keep_alive: str | None = None,
) -> AvatarGenderReading | None:
    """Ask the vision model about one avatar. ``None`` when it could not answer.

    ``None`` and "unclear" are different and both are honest: the first means the
    model never spoke, the second means it looked and could not tell. Neither one
    ever removes a candidate, so the caller may treat them alike — but the
    journal records which happened.
    """
    if not data:
        return None

    payload = await generate_json(
        _PROMPT,
        _SCHEMA,
        model=model,
        timeout_s=timeout_s,
        temperature=0.0,
        images=[base64.b64encode(data).decode("ascii")],
        keep_alive=keep_alive,
        max_output_tokens=256,
    )
    if not payload:
        return None
    return _coerce(payload)
