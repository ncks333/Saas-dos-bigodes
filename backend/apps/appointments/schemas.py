from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from core.utils.phones import normalize_brazilian_whatsapp


class AvailabilityQuery(BaseModel):
    day: date
    service_id: int = Field(gt=0)


class PublicBookingInput(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    whatsapp: str
    service_id: int = Field(gt=0)
    starts_at: datetime
    captcha_token: str = Field(min_length=1, max_length=2048)
    privacy_notice_accepted: Literal[True]

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("whatsapp")
    @classmethod
    def clean_whatsapp(cls, value: str) -> str:
        return normalize_brazilian_whatsapp(value)

    @field_validator("starts_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("O horário deve conter fuso horário")
        return value
