from datetime import timezone
from uuid import uuid4

import httpx

from .config import Settings
from .depthai_client import DepthAIClient
from .models import (
    BackendSubmissionResult,
    CaptureRequest,
    CaptureResponse,
    ReceiptPayload,
    SignedReceiptEnvelope,
)
from .signing import sign_payload
from .storage import LocalStorage


class CaptureService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage = LocalStorage(settings.storage_root)
        self.depthai = DepthAIClient(
            simulate=settings.simulate,
            oak_device_id=settings.oak_device_id,
        )

    async def capture(self, request: CaptureRequest) -> CaptureResponse:
        capture_id = str(uuid4())
        receipt_id = f"{self.settings.receipt_namespace}-{uuid4()}"

        artifact = self.depthai.capture(capture_id, request)
        captured_day = artifact.captured_at.astimezone(timezone.utc).strftime("%Y%m%d")
        stored_asset = self.storage.save_asset(
            capture_id=capture_id,
            captured_day=captured_day,
            payload=artifact.content,
            extension=artifact.extension,
            media_type=artifact.media_type,
        )

        storage_uri = (
            f"{self.settings.public_base_url.rstrip('/')}/assets/{stored_asset.relative_path}"
        )
        metadata = {
            key: value
            for key, value in {
                "operator_id": request.operator_id,
                "notes": request.notes,
                "tags": request.tags,
                "capture_mode": artifact.metadata.get("mode"),
                "asset_size_bytes": stored_asset.size_bytes,
                "station_public_base_url": self.settings.public_base_url,
                "device": artifact.metadata,
            }.items()
            if value not in (None, [], {})
        }
        payload = ReceiptPayload(
            receipt_id=receipt_id,
            capture_id=capture_id,
            station_id=self.settings.station_id,
            asset_id=request.asset_id,
            captured_at=artifact.captured_at,
            asset_hash=stored_asset.sha256_hex,
            storage_uri=storage_uri,
            media_type=stored_asset.media_type,
            metadata=metadata,
        )
        receipt = SignedReceiptEnvelope(
            payload=payload,
            signature=sign_payload(payload, self.settings.station_signer_private_key),
        )
        self.storage.save_receipt(receipt)

        submission = None
        if self.settings.auto_submit_to_backend:
            submission = await self._submit_to_backend(receipt)

        return CaptureResponse(receipt=receipt, submission=submission)

    async def _submit_to_backend(
        self, receipt: SignedReceiptEnvelope
    ) -> BackendSubmissionResult:
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                response = await client.post(
                    f"{self.settings.backend_base_url.rstrip('/')}/api/v1/receipts",
                    json=receipt.model_dump(mode="json"),
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            return BackendSubmissionResult(
                accepted=False,
                receipt_id=receipt.payload.receipt_id,
                backend_url=self.settings.backend_base_url,
                message=str(exc),
            )

        return BackendSubmissionResult(
            accepted=True,
            receipt_id=receipt.payload.receipt_id,
            backend_url=self.settings.backend_base_url,
            message="Receipt accepted by backend.",
        )
