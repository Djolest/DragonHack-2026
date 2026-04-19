import json
from datetime import datetime, timezone
from pathlib import Path

from .models import ReceiptRecord


class ReceiptRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.records_dir = self.root / "records"
        self.records_dir.mkdir(parents=True, exist_ok=True)

    def count(self) -> int:
        return len(list(self.records_dir.glob("*.json")))

    def get(self, receipt_id: str) -> ReceiptRecord | None:
        path = self.records_dir / f"{receipt_id}.json"
        if not path.exists():
            return None
        return ReceiptRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, record: ReceiptRecord) -> ReceiptRecord:
        path = self.records_dir / f"{record.receipt_id}.json"
        stored_record = record.model_copy(
            update={
                "stored_at": path.relative_to(self.root).as_posix(),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        path.write_text(
            json.dumps(
                stored_record.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return stored_record

    def find_by_anchor_tx_hash(self, tx_hash: str) -> ReceiptRecord | None:
        normalized = tx_hash.lower()
        for path in self.records_dir.glob("*.json"):
            record = ReceiptRecord.model_validate_json(path.read_text(encoding="utf-8"))
            if record.anchor_tx_hash and record.anchor_tx_hash.lower() == normalized:
                return record
        return None
