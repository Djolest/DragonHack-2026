import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct

from ..config import Settings
from ..models import AnchorResult, ReceiptRecord, SignedReceiptEnvelope, VerificationResult
from ..repository import ReceiptRepository


def canonical_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def payload_message(receipt: SignedReceiptEnvelope) -> str:
    return canonical_json(receipt.payload.model_dump(mode="json"))


def payload_digest_hex(receipt: SignedReceiptEnvelope) -> str:
    return hashlib.sha256(payload_message(receipt).encode("utf-8")).hexdigest()


def recover_signer(receipt: SignedReceiptEnvelope) -> str:
    return Account.recover_message(
        encode_defunct(text=payload_message(receipt)),
        signature=receipt.signature.signature,
    )


class ReceiptService:
    def __init__(self, settings: Settings, repository: ReceiptRepository) -> None:
        self.settings = settings
        self.repository = repository

    def ingest(self, receipt: SignedReceiptEnvelope) -> ReceiptRecord:
        signer_address = recover_signer(receipt)
        if signer_address.lower() != receipt.signature.signer_address.lower():
            raise ValueError("Recovered signer does not match the signer recorded in the receipt.")

        if self.settings.allowed_signers and signer_address.lower() not in self.settings.allowed_signers:
            raise ValueError("Signer is not in BACKEND_CAPTURE_SIGNER_ALLOWLIST.")

        now = datetime.now(timezone.utc)
        existing = self.repository.get(receipt.payload.receipt_id)
        record = ReceiptRecord(
            receipt_id=receipt.payload.receipt_id,
            receipt=receipt,
            receipt_hash=payload_digest_hex(receipt),
            signature_valid=True,
            signer_address=signer_address,
            anchored=existing.anchored if existing else False,
            anchor_tx_hash=existing.anchor_tx_hash if existing else None,
            anchor_tx_url=existing.anchor_tx_url if existing else None,
            anchor_chain_id=existing.anchor_chain_id if existing else None,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            stored_at=existing.stored_at if existing else "",
        )
        return self.repository.save(record)

    def get_or_raise(self, receipt_id: str) -> ReceiptRecord:
        record = self.repository.get(receipt_id)
        if record is None:
            raise FileNotFoundError(f"Receipt {receipt_id} was not found.")
        return record

    def mark_anchored(self, receipt_id: str, anchor_result: AnchorResult) -> ReceiptRecord:
        record = self.get_or_raise(receipt_id)
        updated = record.model_copy(
            update={
                "anchored": anchor_result.anchored,
                "anchor_tx_hash": anchor_result.tx_hash,
                "anchor_tx_url": anchor_result.tx_url,
                "anchor_chain_id": anchor_result.chain_id,
            }
        )
        return self.repository.save(updated)

    def build_verification(self, receipt_id: str) -> VerificationResult:
        record = self.get_or_raise(receipt_id)
        return VerificationResult(
            receipt_id=record.receipt_id,
            signature_valid=record.signature_valid,
            anchored=record.anchored,
            signer_address=record.signer_address,
            receipt_hash=record.receipt_hash,
            anchor_tx_hash=record.anchor_tx_hash,
            anchor_tx_url=record.anchor_tx_url,
        )
