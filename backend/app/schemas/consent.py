from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.consent import ConsentType
from app.models.deletion_request import DeletionRequestStatus, DeletionTarget


class ConsentCreate(BaseModel):
    consent_type: ConsentType


class ConsentOut(BaseModel):
    id: UUID
    consent_type: ConsentType
    granted_at: datetime
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


class DeletionRequestOut(BaseModel):
    id: UUID
    target: DeletionTarget
    status: DeletionRequestStatus
    requested_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
