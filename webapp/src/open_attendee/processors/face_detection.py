"""저장된 사진에서 사용자가 검토할 얼굴 후보를 만든다."""

from __future__ import annotations

from importlib.resources import as_file, files

import cv2
import numpy as np
from PIL import Image
from pydantic import BaseModel, Field, model_validator

MAX_DETECTION_SIDE = 960
MAX_REGIONS = 100


class PhotoRegion(BaseModel):
    """저장된 사진의 가로·세로 크기를 기준으로 정규화한 직사각형."""

    left: float = Field(ge=0, lt=1)
    top: float = Field(ge=0, lt=1)
    right: float = Field(gt=0, le=1)
    bottom: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> PhotoRegion:
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("영역의 너비와 높이는 0보다 커야 해요.")
        return self


def suggest_faces(photo: Image.Image) -> list[PhotoRegion]:
    """확대한 얼굴 후보를 이미지 경계에 맞추고 좌표를 0~1로 반환한다."""
    image = photo.convert("RGB")
    image.thumbnail((MAX_DETECTION_SIDE, MAX_DETECTION_SIDE), Image.Resampling.LANCZOS)
    width, height = image.size
    if min(width, height) < 16:
        return []

    model = files(__package__).joinpath("models", "yunet.onnx")
    with as_file(model) as path:
        detector = cv2.FaceDetectorYN.create(str(path), "", image.size, 0.7)
        _, faces = detector.detect(cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR))

    suggestions: list[PhotoRegion] = []
    if faces is None:
        return suggestions
    for x, y, w, h in faces[:MAX_REGIONS, :4].astype(float):
        left = max(0, (x - 0.15 * w) / width)
        top = max(0, (y - 0.15 * h) / height)
        right = min(1, (x + 1.15 * w) / width)
        bottom = min(1, (y + 1.15 * h) / height)
        if left < right and top < bottom:
            suggestions.append(PhotoRegion(left=left, top=top, right=right, bottom=bottom))
    return suggestions
