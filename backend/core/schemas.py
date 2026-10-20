import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Kind = Literal["factual", "behavioural", "contextual"]
Status = Literal["active", "inactive"]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Phone(Schema):
    phone: str

    @field_validator("phone")
    @classmethod
    def normalize(cls, value):
        value = re.sub(r"[ ()-]", "", value.strip())
        if value.startswith("+91"):
            value = value[3:]
        if not re.fullmatch(r"[6-9][0-9]{9}", value):
            raise ValueError("Enter a 10-digit Indian mobile number, optionally prefixed with +91.")
        return "+91" + value


class Verify(Phone):
    otp: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class Profile(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    gender: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    age: Annotated[int, Field(strict=True, ge=1, le=120)]


class UserOut(Schema):
    id: UUID
    phone: str
    name: str | None
    gender: str | None
    age: int | None
    onboarded_at: datetime | None


class CreateConversation(Schema):
    id: UUID


class Send(CreateConversation):
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class KnowledgeCreate(Schema):
    type: Literal["factual", "behavioural", "contextual", "summary"]
    content: Text
    status: Status = "active"


class KnowledgePatch(Schema):
    type: Literal["factual", "behavioural", "contextual", "summary"] | None = None
    content: Text | None = None
    status: Status | None = None

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set or any(
            getattr(self, key) is None for key in self.model_fields_set
        ):
            raise ValueError("Supply at least one non-null field.")
        return self


class ConversationOut(Schema):
    id: UUID
    title: str
    status: str
    knowledge_status: str
    generation_status: str
    generation_message_id: UUID | None
    claim_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None


class MessageOut(Schema):
    delivery_status: Literal["complete", "interrupted"] = "complete"
    id: UUID
    role: str
    content: str
    created_at: datetime
    reply_to_id: UUID | None


class KnowledgeOut(Schema):
    id: UUID
    type: str
    status: str
    content: str
    source_conversation_id: UUID | None
    created_at: datetime
    updated_at: datetime
