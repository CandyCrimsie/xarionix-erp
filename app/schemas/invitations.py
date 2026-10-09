from datetime import datetime
from enum import StrEnum

from pydantic import (
    BaseModel,
    Field,
)

from schemas.user import (
    UserCreate,
    UserResponse,
)


class InvitationListScope(StrEnum):
    MINE = "mine"
    ALL = "all"


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


class CompanyInvitationCreate(BaseModel):
    expires_in_hours: int | None = Field(
        default=None,
        ge=1,
    )


class CompanyInvitationResponse(BaseModel):
    id: int
    company_id: int

    token_prefix: str

    expires_at: datetime

    accepted_at: datetime | None
    revoked_at: datetime | None

    created_at: datetime
    updated_at: datetime

    status: InvitationStatus
    created_by_username: str


class CompanyInvitationCreatedResponse(
    CompanyInvitationResponse
):
    token: str


class InvitationPublicCompanyResponse(
    BaseModel
):
    name: str
    short_name: str | None


class InvitationPublicResponse(BaseModel):
    company: InvitationPublicCompanyResponse
    expires_at: datetime
    status: InvitationStatus


class InvitationPolicyResponse(BaseModel):
    default_expire_hours: int
    max_expire_hours: int


class InvitationTokenRequest(BaseModel):
    token: str = Field(
        min_length=1,
        max_length=512,
    )


class InvitationAcceptNewUserRequest(
    UserCreate
):
    token: str = Field(
        min_length=1,
        max_length=512,
    )


class InvitationAcceptanceResponse(BaseModel):
    user: UserResponse
    company_id: int
