"""Validated customer configuration. Credentials remain outside this file."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.domain import Rule


class TruckConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    device_id: str = Field(min_length=1, max_length=80)
    rule: Rule | None = None


class TenantConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    accent: str = Field(default="#17675e", pattern=r"^#[0-9a-fA-F]{6}$")
    demo_mode: Literal["live_simulation"] | None = None
    rule: Rule = Field(default_factory=Rule)
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
