from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, StringConstraints

MAX_SPEECH_CHARACTERS = 10_000


class CodeRequest(BaseModel):
    email: EmailStr


class CodeVerify(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class ConversationCreate(BaseModel):
    private: bool = False


class TurnRequest(BaseModel):
    text: str = Field(min_length=1, max_length=6000)
    client_id: UUID | None = None


class SpeechRequest(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_SPEECH_CHARACTERS)]


class PreferencesPatch(BaseModel):
    memory_enabled: bool | None = None
    language: str | None = Field(default=None, pattern=r"^(auto|en|hi|hinglish)$")


class MemoryPatch(BaseModel):
    action: str | None = Field(default=None, pattern=r"^(confirm|reject)$")
    content: str | None = Field(default=None, min_length=1, max_length=500)
