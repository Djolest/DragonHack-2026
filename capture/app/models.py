from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class StartCaptureSessionRequest(BaseModel):
    asset_id: str = Field(..., description="Business identifier for the asset or batch being captured.")
    operator_id: str | None = Field(default=None, description="Operator badge, email, or username.")
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    simulate: bool | None = Field(
        default=None,
        description="Optional per-request override for CAPTURE_SIMULATE.",
    )


class CaptureSessionArtifacts(BaseModel):
    session_directory: str
    rgb_video_relative_path: str | None = None
    proof_relative_path: str | None = None
    receipt_relative_path: str | None = None
    rgb_video_uri: str | None = None
    proof_uri: str | None = None
    receipt_uri: str | None = None


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


class CaptureSessionStatus(BaseModel):
    session_id: str
    asset_id: str
    operator_id: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    simulate: bool
    state: str
    error: str | None = None
    started_at: datetime
    stopped_at: datetime | None = None
    device_info: dict[str, Any] | None = None
    live_state: dict[str, Any] | None = None
    artifacts: CaptureSessionArtifacts | None = None
    proof_summary: dict[str, Any] | None = None


class StopCaptureSessionResponse(BaseModel):
    session: CaptureSessionStatus
