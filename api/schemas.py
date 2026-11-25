"""Request and response models for Phase 1C. ErrorBody has no extra fields."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class CustomerRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str
    name: str
    phone: str = ""


class CustomerLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str


class EmployeeLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str


class CustomerProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    email: str
    name: str
    phone: str


class EmployeeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    email: str
    name: str


class CustomerAuthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["customer"]
    customer: CustomerProfile


class EmployeeAuthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["employee"]
    employee: EmployeeProfile


class AnonymousMe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal[""]


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    error: str
