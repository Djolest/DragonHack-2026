from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


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


class ReceiptRecord(BaseModel):
    receipt_id: str
    receipt: SignedReceiptEnvelope
    receipt_hash: str
    signature_valid: bool
    signer_address: str
    anchored: bool = False
    anchor_tx_hash: str | None = None
    anchor_tx_url: str | None = None
    anchor_chain_id: int | None = None
    created_at: datetime
    updated_at: datetime
    stored_at: str


class AnchorResult(BaseModel):
    receipt_id: str
    anchored: bool
    tx_hash: str
    tx_url: str
    chain_id: int


class VerificationResult(BaseModel):
    receipt_id: str
    signature_valid: bool
    anchored: bool
    signer_address: str
    receipt_hash: str
    anchor_tx_hash: str | None = None
    anchor_tx_url: str | None = None


class TransactionProofResult(BaseModel):
    tx_hash: str
    proof_type: Literal["anchor_contract", "legacy_signed_payload"]
    decoded: bool
    proof_valid: bool
    chain_id: int | None = None
    block_number: int | None = None
    from_address: str | None = None
    to_address: str | None = None
    explorer_url: str | None = None
    receipt_id: str | None = None
    receipt_id_hash: str | None = None
    receipt_hash: str | None = None
    asset_hash: str | None = None
    storage_uri: str | None = None
    signer_address: str | None = None
    submitter_address: str | None = None
    signature: str | None = None
    public_key: str | None = None
    signature_valid: bool | None = None
    public_key_matches: bool | None = None
    record_found: bool = False
    record_consistent: bool | None = None
    provided_asset_hash: str | None = None
    asset_hash_matches: bool | None = None
