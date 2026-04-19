from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings
from .models import ReceiptPayload, SignedReceiptEnvelope
from .signing import payload_digest_hex, sign_payload
from .storage import LocalStorage


@dataclass(frozen=True, slots=True)
class ReceiptWorkflowResult:
    receipt_workflow: dict[str, Any]
    receipt_relative_path: str | None
    receipt_uri: str | None


class ReceiptWorkflow:
    def __init__(self, settings: Settings, storage: LocalStorage) -> None:
        self.settings = settings
        self.storage = storage

    def finalize_error(self, error_message: str) -> ReceiptWorkflowResult:
        return ReceiptWorkflowResult(
            receipt_workflow={
                "status": "failed",
                "reason": "Receipt post-processing failed unexpectedly.",
                "error": error_message,
            },
            receipt_relative_path=None,
            receipt_uri=None,
        )

    def finalize(self, snapshot: dict[str, Any]) -> ReceiptWorkflowResult:
        proof_summary = snapshot.get("proof_summary")
        artifacts = snapshot.get("artifacts")
        if not isinstance(proof_summary, dict) or not isinstance(artifacts, dict):
            return ReceiptWorkflowResult(
                receipt_workflow={
                    "status": "skipped_missing_session_data",
                    "reason": "Capture session finished without proof metadata or artifacts.",
                },
                receipt_relative_path=None,
                receipt_uri=None,
            )

        if proof_summary.get("overall_status") != "verified":
            return ReceiptWorkflowResult(
                receipt_workflow={
                    "status": "skipped_unverified",
                    "reason": "Depth realness checks did not finish in the verified state.",
                },
                receipt_relative_path=None,
                receipt_uri=None,
            )

        rgb_video_relative_path = artifacts.get("rgb_video_relative_path")
        if not isinstance(rgb_video_relative_path, str) or not rgb_video_relative_path:
            return ReceiptWorkflowResult(
                receipt_workflow={
                    "status": "skipped_missing_video",
                    "reason": "No recorded RGB video is available for hashing.",
                },
                receipt_relative_path=None,
                receipt_uri=None,
            )

        rgb_video_path = self.storage.resolve_asset_path(rgb_video_relative_path)
        if not rgb_video_path.exists():
            return ReceiptWorkflowResult(
                receipt_workflow={
                    "status": "skipped_missing_video",
                    "reason": f"Recorded video {rgb_video_relative_path} was not found on disk.",
                },
                receipt_relative_path=None,
                receipt_uri=None,
            )

        asset_hash = self.storage.sha256_file_hex(rgb_video_path)
        if not self.settings.station_signer_private_key:
            return ReceiptWorkflowResult(
                receipt_workflow={
                    "status": "signing_disabled",
                    "reason": "CAPTURE_STATION_SIGNER_PRIVATE_KEY is not configured.",
                    "asset_hash": asset_hash,
                },
                receipt_relative_path=None,
                receipt_uri=None,
            )

        session_directory = str(artifacts["session_directory"])
        session_dir = self.storage.resolve_asset_path(session_directory)
        receipt_path = session_dir / "receipt.json"
        receipt_relative_path = receipt_path.relative_to(self.storage.root).as_posix()
        receipt_uri = self.storage.build_public_uri(receipt_relative_path, self.settings.public_base_url)
        receipt_id = f"{self.settings.receipt_namespace}-{snapshot['session_id']}"
        storage_uri = (
            artifacts.get("rgb_video_uri")
            or self.storage.build_public_uri(rgb_video_relative_path, self.settings.public_base_url)
            or rgb_video_relative_path
        )
        captured_at = snapshot.get("stopped_at") or snapshot["started_at"]

        payload = ReceiptPayload(
            receipt_id=receipt_id,
            capture_id=str(snapshot["session_id"]),
            station_id=self.settings.station_id,
            asset_id=str(snapshot["asset_id"]),
            captured_at=captured_at,
            asset_hash=asset_hash,
            storage_uri=str(storage_uri),
            media_type="video/mp4",
            metadata={
                "operator_id": snapshot.get("operator_id"),
                "notes": snapshot.get("notes"),
                "tags": list(snapshot.get("tags", [])),
                "proof_relative_path": artifacts.get("proof_relative_path"),
                "proof_uri": artifacts.get("proof_uri"),
                "proof_summary": deepcopy(proof_summary),
            },
        )
        signature = sign_payload(payload, self.settings.station_signer_private_key)
        envelope = SignedReceiptEnvelope(payload=payload, signature=signature)
        self.storage.write_json(
            receipt_path,
            envelope.model_dump(mode="json"),
        )

        receipt_workflow: dict[str, Any] = {
            "status": "created_local",
            "reason": "Created a signed receipt for a verified capture session.",
            "receipt_id": receipt_id,
            "receipt_hash": payload_digest_hex(payload),
            "asset_hash": asset_hash,
            "signer_address": signature.signer_address,
            "submitted_to_backend": False,
            "anchored": False,
            "receipt_relative_path": receipt_relative_path,
            "receipt_uri": receipt_uri,
        }

        if self.settings.auto_submit_to_backend and self.settings.backend_base_url:
            try:
                backend_record = self._submit_to_backend(envelope)
            except httpx.HTTPError as exc:
                receipt_workflow.update(
                    {
                        "status": "submission_failed",
                        "reason": "Failed to submit the signed receipt to the backend.",
                        "submission_error": str(exc),
                    }
                )
            else:
                receipt_workflow.update(
                    {
                        "status": "anchored" if backend_record.get("anchored") else "submitted",
                        "reason": (
                            "Receipt was stored by the backend and anchored to Flare."
                            if backend_record.get("anchored")
                            else "Receipt was stored by the backend."
                        ),
                        "submitted_to_backend": True,
                        "anchored": bool(backend_record.get("anchored")),
                        "anchor_tx_hash": backend_record.get("anchor_tx_hash"),
                        "anchor_tx_url": backend_record.get("anchor_tx_url"),
                        "backend_receipt_hash": backend_record.get("receipt_hash"),
                    }
                )

        return ReceiptWorkflowResult(
            receipt_workflow=receipt_workflow,
            receipt_relative_path=receipt_relative_path,
            receipt_uri=receipt_uri,
        )

    def _submit_to_backend(self, envelope: SignedReceiptEnvelope) -> dict[str, Any]:
        assert self.settings.backend_base_url is not None
        base_url = self.settings.backend_base_url.rstrip("/")
        with httpx.Client(timeout=self.settings.request_timeout_seconds) as client:
            response = client.post(
                f"{base_url}/api/v1/receipts",
                json=envelope.model_dump(mode="json"),
            )
            response.raise_for_status()
            return response.json()
