"""Text-to-speech for any Dutch text the user picks, with Azure Speech (REST, no SDK).

Every result is cached as `<MEDIA_DIR>/tts/<sha256 of voice + text>.mp3`, so the same text is
synthesized once and later requests cost nothing. Needs AZURE_SPEECH_KEY and AZURE_SPEECH_REGION
(docs/01-production-deployment.md#text-to-speech); the UI falls back to the browser's voice on any error.
"""

import hashlib
import os
from xml.sax.saxutils import escape

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from routes.media import media_root
from services.users import User
from utils.auth import current_user

router = APIRouter()

VOICE = "nl-NL-FennaNeural"
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
MAX_TEXT = 500  # characters; keeps one request well inside the free tier


@router.get("/tts", tags=["Speech"])
async def text_to_speech(text: str, user: User = Depends(current_user)):
    """
    The spoken Dutch `text` as MP3 (at most 500 characters; longer text is cut). Signed-in users only.
    """
    text = " ".join(text.split())[:MAX_TEXT]
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty")

    path = media_root() / "tts" / f"{hashlib.sha256(f'{VOICE}|{text}'.encode()).hexdigest()}.mp3"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(await synthesize(text))
        tmp.replace(path)  # never serve a half-written file

    return FileResponse(
        path,
        media_type="audio/mpeg",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


async def synthesize(text: str) -> bytes:
    key, region = os.getenv("AZURE_SPEECH_KEY"), os.getenv("AZURE_SPEECH_REGION")
    if not key or not region:
        raise HTTPException(status_code=503, detail="Text-to-speech is not configured on this server")

    ssml = (
        '<speak version="1.0" xml:lang="nl-NL">'
        f'<voice name="{VOICE}">{escape(text)}</voice>'
        "</speak>"
    )
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
                content=ssml.encode(),
                headers={
                    "Ocp-Apim-Subscription-Key": key,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
                    "User-Agent": "dutchpal",
                },
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="The speech service cannot be reached")

    if response.status_code == 429:
        raise HTTPException(status_code=503, detail="The speech service quota is used up for now")
    if response.status_code != 200:
        print(f"Azure TTS failed: {response.status_code} {response.text[:200]}")
        raise HTTPException(status_code=503, detail="The speech service is temporarily unavailable")
    return response.content
