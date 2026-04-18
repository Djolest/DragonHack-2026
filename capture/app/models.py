from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CaptureRequest(BaseModel):
    asset_id: str = Field(..., description="Business identifier for the asset or batch being captured.")
    operator_id: str | None = Field(default=None, description="Operator badge, email, or username.")
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    simulate: bool | None = Field(
        default=None,
        description="Optional per-request override for CAPTURE_SIMULATE.",
    )


class ReceiptPayload(BaseModel):
    schema_version: str = "1.0"
    receipt_id: str
    capture_id: str
    station_id: str
    asset_id: str
    captured_at: datetime
    asset_hash: str
    storage_uri: str
    media_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReceiptSignature(BaseModel):
    scheme: Literal["eip191"] = "eip191"
    signer_address: str
    signature: str


class SignedReceiptEnvelope(BaseModel):
    payload: ReceiptPayload
    signature: ReceiptSignature


class BackendSubmissionResult(BaseModel):
    accepted: bool
    receipt_id: str
    backend_url: str
    anchor_required: bool = True
    message: str | None = None


class CaptureResponse(BaseModel):
    receipt: SignedReceiptEnvelope
    submission: BackendSubmissionResult | None = None
