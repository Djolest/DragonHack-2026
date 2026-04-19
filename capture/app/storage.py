from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SessionStoragePaths:
    session_dir: Path
    session_relative_path: str
    rgb_video_path: Path
    rgb_video_relative_path: str
    proof_path: Path
    proof_relative_path: str
    receipt_path: Path
    receipt_relative_path: str


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.captures_dir = self.root / "captures"
        self.captures_dir.mkdir(parents=True, exist_ok=True)

    def prepare_session(self, session_id: str, started_at: datetime) -> SessionStoragePaths:
        captured_day = started_at.astimezone().strftime("%Y%m%d")
        session_dir = self.captures_dir / captured_day / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        rgb_video_path = session_dir / "rgb.mp4"
        proof_path = session_dir / "proof.json"
        receipt_path = session_dir / "receipt.json"
        return SessionStoragePaths(
            session_dir=session_dir,
            session_relative_path=session_dir.relative_to(self.root).as_posix(),
            rgb_video_path=rgb_video_path,
            rgb_video_relative_path=rgb_video_path.relative_to(self.root).as_posix(),
            proof_path=proof_path,
            proof_relative_path=proof_path.relative_to(self.root).as_posix(),
            receipt_path=receipt_path,
            receipt_relative_path=receipt_path.relative_to(self.root).as_posix(),
        )

    def write_proof(self, paths: SessionStoragePaths, proof_summary: dict[str, object]) -> Path:
        return self.write_json(paths.proof_path, proof_summary)

    def write_receipt(self, paths: SessionStoragePaths, receipt_envelope: dict[str, Any]) -> Path:
        return self.write_json(paths.receipt_path, receipt_envelope)

    def write_json(self, path: Path, payload: dict[str, Any]) -> Path:
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    def sha256_file_hex(self, path: Path, *, chunk_size: int = 1024 * 1024) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_handle:
            while chunk := file_handle.read(chunk_size):
                digest.update(chunk)
        return digest.hexdigest()

    def build_public_uri(self, relative_path: str | None, public_base_url: str) -> str | None:
        if relative_path is None:
            return None
        return f"{public_base_url.rstrip('/')}/assets/{relative_path}"

    def resolve_asset_path(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        root = self.root.resolve()
        if root not in candidate.parents and candidate != root:
            raise ValueError("Requested asset path escapes storage root.")
        return candidate
