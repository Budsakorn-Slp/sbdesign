from datetime import datetime

from pydantic import BaseModel, Field


class ConsentIn(BaseModel):
    marketing: bool


class ConsentOut(BaseModel):
    kind: str
    granted: bool
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PrivacyOut(BaseModel):
    """สรุปสถานะความเป็นส่วนตัวของบัญชีตัวเอง"""

    consent_marketing: bool
    consent_marketing_at: datetime | None = None
    anonymized_at: datetime | None = None
    history: list[ConsentOut] = Field(default_factory=list)


class DeleteIn(BaseModel):
    note: str | None = None
    confirm: bool = False


class DataRequestOut(BaseModel):
    id: str
    user_id: str
    kind: str
    status: str
    note: str | None = None
    result: dict | None = None
    created_at: datetime
    done_at: datetime | None = None

    model_config = {"from_attributes": True}


class AuditOut(BaseModel):
    id: str
    actor_user_id: str | None = None
    role: str | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    payload: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
