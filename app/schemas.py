from typing import Literal
from urllib.parse import urlsplit
import ipaddress
from pydantic import BaseModel, Field, field_validator


def validate_url(value: str) -> str:
    value = value.strip()
    if len(value) > 2048:
        raise ValueError("URL terlalu panjang (maksimal 2048 karakter)")
    try:
        parsed = urlsplit(value)
        port = parsed.port  # validates malformed ports
    except ValueError:
        raise ValueError("URL atau port tidak valid")
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Gunakan URL HTTP atau HTTPS yang lengkap")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Kredensial di dalam URL tidak diperbolehkan")
    if parsed.fragment:
        raise ValueError("Fragmen URL (#) tidak diperbolehkan")
    if any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError("URL tidak boleh mengandung spasi")
    return value


class EndpointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    url: str
    method: Literal["GET", "HEAD"] = "GET"
    expected_status: int = Field(default=200, ge=100, le=599)
    interval_seconds: int = Field(default=60, ge=30, le=86400)
    timeout_seconds: int = Field(default=10, ge=1, le=30)
    failure_threshold: int = Field(default=2, ge=1, le=10)
    recovery_threshold: int = Field(default=1, ge=1, le=10)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Nama endpoint wajib diisi")
        return value

    @field_validator("url")
    @classmethod
    def check_url(cls, value: str) -> str:
        return validate_url(value)


class EndpointUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    url: str | None = None
    method: Literal["GET", "HEAD"] | None = None
    expected_status: int | None = Field(default=None, ge=100, le=599)
    interval_seconds: int | None = Field(default=None, ge=30, le=86400)
    timeout_seconds: int | None = Field(default=None, ge=1, le=30)
    failure_threshold: int | None = Field(default=None, ge=1, le=10)
    recovery_threshold: int | None = Field(default=None, ge=1, le=10)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Nama endpoint wajib diisi")
        return value

    @field_validator("url")
    @classmethod
    def check_url(cls, value: str | None) -> str | None:
        return validate_url(value) if value is not None else None


class EnabledUpdate(BaseModel):
    enabled: bool


class IncidentUpdate(BaseModel):
    notes: str = Field(max_length=5000)


class ConfigUpdate(BaseModel):
    sla_target: float = Field(ge=0, le=100, allow_inf_nan=False)


class WebhookUpdate(BaseModel):
    webhook_url: str | None = None

    @field_validator("webhook_url")
    @classmethod
    def check_url(cls, value: str | None) -> str | None:
        return validate_url(value) if value and value.strip() else None
