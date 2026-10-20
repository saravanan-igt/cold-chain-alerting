"""Validated customer configuration. Credentials remain outside this file."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.domain import Rule


class TruckConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    device_id: str = Field(min_length=1, max_length=80)
    rule: Rule | None = None


NotificationEvent = Literal["incident.opened", "incident.recovered", "incident.acknowledged", "incident.escalated"]


class ChannelConfig(BaseModel):
    """A delivery target. Secrets are referenced by environment variable name, never stored."""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")
    type: Literal["log", "webhook"]
    url: str | None = Field(default=None, pattern=r"^https?://", max_length=2000)
    secret_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,79}$")
    format: Literal["coldline", "slack"] = "coldline"
    events: list[NotificationEvent] = Field(default_factory=lambda: ["incident.opened", "incident.recovered"], max_length=4)

    @model_validator(mode="after")
    def target_required(self):
        if self.type == "webhook" and not self.url:
            raise ValueError("Webhook channels require a url")
        if self.type == "log" and (self.url or self.secret_env):
            raise ValueError("Log channels do not take a url or secret")
        return self


class EscalationLevel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_minutes: float = Field(gt=0, le=1440, allow_inf_nan=False)
    channels: list[str] = Field(min_length=1, max_length=10)


class NotificationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channels: list[ChannelConfig] = Field(default_factory=list, max_length=10)
    escalation: list[EscalationLevel] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def references(self):
        ids = [channel.id for channel in self.channels]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate notification channel id")
        delays = [level.after_minutes for level in self.escalation]
        if delays != sorted(set(delays)):
            raise ValueError("Escalation levels must have strictly increasing after_minutes")
        for level in self.escalation:
            unknown = set(level.channels) - set(ids)
            if unknown:
                raise ValueError(f"Escalation references unknown channel(s): {sorted(unknown)}")
        return self


class TenantConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    accent: str = Field(default="#17675e", pattern=r"^#[0-9a-fA-F]{6}$")
    demo_mode: Literal["live_simulation"] | None = None
    rule: Rule = Field(default_factory=Rule)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    trucks: list[TruckConfig] = Field(max_length=1000)

    @model_validator(mode="after")
    def unique_streams(self):
        for name in ("id", "device_id"):
            values = [getattr(truck, name) for truck in self.trucks]
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate truck {name}")
        return self


class Customers(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenants: list[TenantConfig] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_tenants(self):
        if len({tenant.id for tenant in self.tenants}) != len(self.tenants):
            raise ValueError("Duplicate tenant ID")
        return self


class Credential(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant: str
    role: Literal["operator", "device"]
    truck_id: str | None = None
    device_id: str | None = None

    @model_validator(mode="after")
    def device_binding(self):
        if self.role == "device" and (not self.truck_id or not self.device_id):
            raise ValueError("Device credentials require truck_id and device_id")
        return self
