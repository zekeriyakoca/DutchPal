"""Serves exam audio, video and pictures from MEDIA_DIR (default ./media) at /media/{path}.

Content exercises store media paths relative to this root (e.g. `staatsexamen-b1/2024-luisteren/Track 3 opgave 1.mp3`,
see docs/06-content-extraction.md). The files are never committed or baked into an image; in production they
live on the `dutchpal-media` volume (docs/01-production-deployment.md). FileResponse answers Range requests,
so audio and video players can seek.
"""

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".opus": "audio/ogg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def media_root() -> Path:
    return Path(os.getenv("MEDIA_DIR", "media")).resolve()


def resolve_media(path: str) -> Optional[Path]:
    """The file for `path` inside the media root, or None (outside the root, missing, or not a media type)."""
    root = media_root()
    try:
        target = (root / path).resolve()
    except (OSError, ValueError):  # e.g. an embedded null byte
        return None
    if root not in target.parents or not target.is_file() or target.suffix.lower() not in MEDIA_TYPES:
        return None
    return target


@router.get("/media/{path:path}", tags=["Media"])
def get_media(path: str):
    """
    One media file (audio, video or picture) used by content exercises. Supports Range requests.
    """
    target = resolve_media(path)
    if target is None:
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(
        target,
        media_type=MEDIA_TYPES[target.suffix.lower()],
        headers={"Cache-Control": "public, max-age=86400"},
    )
