"""Assumed video capability for interaction design, explicitly a prototype fixture.

No network media is fetched and no speech/OCR is performed here. This adapter
stands in for the future video-import worker while product flows are reviewed.
Its output is marked `prototype` and must not be used as verified source evidence.
"""
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


class VideoRequest(BaseModel):
    source_url: str = Field(default="", max_length=2000)
    file_name: str = Field(default="", max_length=260)


router = APIRouter(prefix="/api/video")


@router.post("/analyze")
def analyze(req: VideoRequest):
    if not req.source_url.strip() and not req.file_name.strip():
        raise HTTPException(400, "Вставьте ссылку или выберите видео")
    if req.source_url:
        try:
            parsed = urlsplit(req.source_url)
            valid = parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(400, "Проверьте ссылку на видео")
    return {"id": uuid4().hex, "title": "Небольшая доля технологий", "mode": "prototype",
            "source_url": req.source_url, "file_name": req.file_name,
            "text": "Идея материала: дополнить дивидендный портфель небольшой долей российских IT-компаний. Рассматривать её на длинном горизонте, без заёмных денег и с сохранением ограничений основного портфеля."}
