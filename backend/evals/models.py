"""Small, explicit file formats for experiments and reviews."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Profile(Record):
    name: str
    gender: str = "Prefer not to say"
    age: int = Field(default=26, ge=1, le=120)


class Knowledge(Record):
    id: UUID
    type: Literal["factual", "behavioural", "contextual"]
    content: str = Field(min_length=1, max_length=2000)
    status: Literal["active"] = "active"


class Scenario(Record):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    split: Literal["development", "holdout"]
    language: str
    profile: Profile
    knowledge: list[Knowledge] = Field(default_factory=list)
    latest_summary: str | None = None
    situation: str = Field(min_length=1)
    persona: str = Field(min_length=1)
    expected_behavior: list[str] = Field(min_length=1)
    max_user_turns: int = Field(default=8, ge=1, le=20)
    first_user_message: str | None = Field(default=None, min_length=1, max_length=4000)

    @field_validator("id")
    @classmethod
    def not_a_manifest_name(cls, value):
        if value in {"run", "reviews"}:
            raise ValueError("Scenario ID conflicts with a run artifact")
        return value

    def payload(self, turns, *, opening=False):
        return {
            "profile": self.profile.model_dump(),
            "knowledge": [item.model_dump(mode="json") for item in self.knowledge],
            "latest_summary": self.latest_summary,
            "opening": opening,
            "transcript": [{"role": t.role, "content": t.content} for t in turns],
        }


class Assessment(Record):
    verdict: Literal["good", "acceptable", "bad"]
    evidence: str = Field(min_length=1)
    desired_change: str = Field(min_length=1)
    flags: list[Literal["invented_scripture", "wrong_citation", "harmful_agreement", "other"]] = (
        Field(default_factory=list)
    )
