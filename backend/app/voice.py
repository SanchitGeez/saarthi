from __future__ import annotations

import httpx
from fastapi import HTTPException, UploadFile

from app.config import settings
from app.schemas import MAX_SPEECH_CHARACTERS

ELEVEN_BASE = "https://api.elevenlabs.io/v1"
MAX_AUDIO_BYTES = 12 * 1024 * 1024


def _headers() -> dict[str, str]:
    if not settings.eleven_labs_api_key:
        raise HTTPException(status_code=503, detail="Voice is not configured yet.")
    return {"xi-api-key": settings.eleven_labs_api_key}


async def transcribe(upload: UploadFile) -> str:
    audio = await upload.read(MAX_AUDIO_BYTES + 1)
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="That recording is too large. Try a shorter note.")
    if not audio:
        raise HTTPException(status_code=400, detail="The recording was empty. Please try again.")
    headers = _headers()
    filename = upload.filename or "voice-note.m4a"
    mime_type = upload.content_type or "audio/mp4"
    try:
        async with httpx.AsyncClient(timeout=75) as client:
            response = await client.post(
                f"{ELEVEN_BASE}/speech-to-text",
                headers=headers,
                data={"model_id": settings.eleven_labs_stt_model, "tag_audio_events": "false"},
                files={"file": (filename, audio, mime_type)},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Voice transcription is unavailable right now.") from exc
    if response.is_error:
        raise HTTPException(status_code=502, detail="Voice transcription could not process that note.")
    text = response.json().get("text", "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="I couldn't make out the recording. Try once more or type it.")
    return text


async def speak(text: str) -> bytes:
    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="There is no reply text to read aloud.")
    if len(text) > MAX_SPEECH_CHARACTERS:
        raise HTTPException(status_code=422, detail="This reply is too long to play as one recording.")
    headers = _headers()
    try:
        async with httpx.AsyncClient(timeout=75) as client:
            response = await client.post(
                f"{ELEVEN_BASE}/text-to-speech/{settings.eleven_labs_voice_id}",
                headers={**headers, "Accept": "audio/mpeg", "Content-Type": "application/json"},
                params={"output_format": "mp3_44100_128"},
                json={"text": text, "model_id": settings.eleven_labs_tts_model},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Spoken replies are unavailable right now.") from exc
    if response.is_error:
        raise HTTPException(status_code=502, detail="I couldn't make an audio version of that reply.")
    return response.content
