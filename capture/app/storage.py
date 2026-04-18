import hashlib
from dataclasses import dataclass
from pathlib import Path

from .models import SignedReceiptEnvelope
from .signing import canonical_json


@dataclass(slots=True)
class StoredAsset:
    relative_path: str
    sha256_hex: str
    media_type: str
    size_bytes: int


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.captures_dir = self.root / "captures"
        self.receipts_dir = self.root / "receipts"
        self.captures_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)

    def save_asset(
        self,
        capture_id: str,
        captured_day: str,
        payload: bytes,
        extension: str,
        media_type: str,
    ) -> StoredAsset:
        bucket = self.captures_dir / captured_day
        bucket.mkdir(parents=True, exist_ok=True)
        file_path = bucket / f"{capture_id}{extension}"
        file_path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        return StoredAsset(
            relative_path=file_path.relative_to(self.root).as_posix(),
            sha256_hex=digest,
            media_type=media_type,
            size_bytes=len(payload),
        )

    def save_receipt(self, receipt: SignedReceiptEnvelope) -> Path:
        captured_day = receipt.payload.captured_at.strftime("%Y%m%d")
        bucket = self.receipts_dir / captured_day
        bucket.mkdir(parents=True, exist_ok=True)
        file_path = bucket / f"{receipt.payload.receipt_id}.json"
        file_path.write_text(
            canonical_json(receipt.model_dump(mode="json")),
            encoding="utf-8",
        )
        return file_path

    def resolve_asset_path(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        root = self.root.resolve()
        if root not in candidate.parents and candidate != root:
            raise ValueError("Requested asset path escapes storage root.")
        return candidate
