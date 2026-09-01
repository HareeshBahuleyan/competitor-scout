from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from competitor_scout.models.intelligence import ApprovalStatus, CompetitorStatus, SourceCategory
from competitor_scout.schemas.runs import RunRead


class CompetitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    primary_domain: str = Field(min_length=3, max_length=2048)
    description: str = Field(default="", max_length=2000)
    daily_run_time_local: time | None = None


class CompetitorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    daily_run_time_local: time | None = None
    status: CompetitorStatus | None = None

    @field_validator("name", "description", "daily_run_time_local")
    @classmethod
    def mutable_fields_must_not_be_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("competitor fields must not be null")
        return value

    @field_validator("status")
    @classmethod
    def status_must_be_user_selectable(
        cls, value: CompetitorStatus | None
    ) -> CompetitorStatus | None:
        if value in {CompetitorStatus.DELETED, CompetitorStatus.DISCOVERING}:
            raise ValueError("status cannot be selected directly")
        return value


class CompetitorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    primary_domain: str
    description: str
    status: CompetitorStatus
    daily_run_time_local: time
    created_at: datetime
    updated_at: datetime


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: HttpUrl
    source_category: SourceCategory
    title: str
    discovery_reason: str
    approval_status: ApprovalStatus
    created_at: datetime
    updated_at: datetime


class SourceApprovalUpdate(BaseModel):
    approval_status: ApprovalStatus

    @field_validator("approval_status")
    @classmethod
    def approval_must_be_a_decision(cls, value: ApprovalStatus) -> ApprovalStatus:
        if value is ApprovalStatus.SUGGESTED:
            raise ValueError("approval_status must be approved or rejected")
        return value


class SourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)


class StartMonitoringRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ids: list[UUID] = Field(min_length=1, max_length=100)
    run_initial_scan: bool = True


class StartMonitoringResponse(BaseModel):
    competitor: CompetitorRead
    run: RunRead | None
