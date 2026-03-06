from pydantic import BaseModel
from typing import List, Optional


class FacePairResult(BaseModel):
    """Result of comparing two face images"""
    image_a_label: str
    image_b_label: str
    verified: bool
    confidence: float  # 0-100 percentage
    distance: float    # Raw distance metric


class FaceMatchReport(BaseModel):
    """Full face matching report across all collected profile images"""
    overall_confidence: float       # Weighted average 0-100
    total_comparisons: int
    successful_comparisons: int
    pairs: List[FacePairResult]
    face_detected_count: int        # How many images had detectable faces
    total_images: int               # How many images were collected
