from __future__ import annotations

import threading
from copy import deepcopy

from .config import Settings
from .depth_challenge import load_verification_config
from .models import CaptureSessionArtifacts, CaptureSessionStatus, StartCaptureSessionRequest
from .receipt_workflow import ReceiptWorkflow
from .oak4_engine import Oak4RuntimeConfig
from .preview import SessionPreviewRegistry
from .session_runtime import CaptureSessionManager, SessionArtifacts
from .storage import LocalStorage


class CaptureService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage = LocalStorage(settings.storage_root)
        self.receipt_workflow = ReceiptWorkflow(settings, self.storage)
        self._postprocess_lock = threading.Lock()
        verification_config = load_verification_config(settings.verification_config_path.resolve())
        runtime_config = Oak4RuntimeConfig(
            fps=settings.runtime_fps,
            rgb_size=(settings.runtime_rgb_width, settings.runtime_rgb_height),
            stereo_size=(settings.runtime_stereo_width, settings.runtime_stereo_height),
            sync_threshold_ms=settings.runtime_sync_threshold_ms,
        )
        self.preview_registry = SessionPreviewRegistry(
            runtime_config=runtime_config,
            verification_config=verification_config,
        )
        self.manager = CaptureSessionManager(
            storage=self.storage,
            verification_config=verification_config,
            public_base_url=settings.public_base_url,
            runtime_config=runtime_config,
            oak_device_id=settings.oak_device_id,
            observer_factory=self.preview_registry.observer_for_session,
        )

    def start_session(self, request: StartCaptureSessionRequest) -> CaptureSessionStatus:
        simulate = request.simulate if request.simulate is not None else self.settings.simulate
        session = self.manager.start_session(
            asset_id=request.asset_id,
            operator_id=request.operator_id,
            notes=request.notes,
            tags=request.tags,
            simulate=simulate,
        )
        return self._status_from_snapshot(session.snapshot())

    def get_session_status(self, session_id: str) -> CaptureSessionStatus:
        session = self.manager.get_session(session_id)
        self._ensure_session_postprocessed(session)
        return self._status_from_snapshot(session.snapshot())

    def stop_session(self, session_id: str) -> CaptureSessionStatus:
        session = self.manager.stop_session(session_id)
        self._ensure_session_postprocessed(session)
        return self._status_from_snapshot(session.snapshot())

    def get_session_rgb_preview_jpeg(
        self,
        session_id: str,
        *,
        width: int | None = None,
        height: int | None = None,
        quality: int = 90,
    ) -> bytes:
        self.manager.get_session(session_id)
        return self.preview_registry.latest_rgb_jpeg(
            session_id,
            width=width,
            height=height,
            quality=quality,
        )

    def get_session_depth_preview_jpeg(
        self,
        session_id: str,
        *,
        width: int | None = None,
        height: int | None = None,
        quality: int = 90,
    ) -> bytes:
        self.manager.get_session(session_id)
        return self.preview_registry.latest_depth_jpeg(
            session_id,
            width=width,
            height=height,
            quality=quality,
        )

    def _ensure_session_postprocessed(self, session: object) -> None:
        if not hasattr(session, "needs_postprocessing") or not session.needs_postprocessing():
            return

        with self._postprocess_lock:
            if not session.needs_postprocessing():
                return
            snapshot = session.snapshot()
            proof_summary = snapshot.get("proof_summary")
            artifacts_snapshot = snapshot.get("artifacts")
            if not isinstance(proof_summary, dict):
                session.apply_postprocess()
                return

            try:
                workflow_result = self.receipt_workflow.finalize(snapshot)
            except Exception as exc:
                workflow_result = self.receipt_workflow.finalize_error(str(exc))
            updated_summary = deepcopy(proof_summary)
            updated_summary["receipt_workflow"] = workflow_result.receipt_workflow
            proof_relative_path = (
                artifacts_snapshot.get("proof_relative_path")
                if isinstance(artifacts_snapshot, dict)
                else None
            )
            if isinstance(proof_relative_path, str) and proof_relative_path:
                proof_path = self.storage.resolve_asset_path(proof_relative_path)
                self.storage.write_json(proof_path, updated_summary)

            if isinstance(artifacts_snapshot, dict):
                updated_artifacts = SessionArtifacts(
                    session_directory=str(artifacts_snapshot["session_directory"]),
                    rgb_video_relative_path=artifacts_snapshot.get("rgb_video_relative_path"),
                    proof_relative_path=artifacts_snapshot.get("proof_relative_path"),
                    receipt_relative_path=workflow_result.receipt_relative_path,
                    rgb_video_uri=artifacts_snapshot.get("rgb_video_uri"),
                    proof_uri=artifacts_snapshot.get("proof_uri"),
                    receipt_uri=workflow_result.receipt_uri,
                )
            else:
                updated_artifacts = None
            session.apply_postprocess(
                proof_summary=updated_summary,
                artifacts=updated_artifacts,
            )

    def _status_from_snapshot(self, snapshot: dict[str, object]) -> CaptureSessionStatus:
        artifacts_data = snapshot.get("artifacts")
        artifacts = (
            CaptureSessionArtifacts.model_validate(artifacts_data)
            if isinstance(artifacts_data, dict)
            else None
        )
        return CaptureSessionStatus(
            session_id=str(snapshot["session_id"]),
            asset_id=str(snapshot["asset_id"]),
            operator_id=snapshot.get("operator_id"),
            notes=snapshot.get("notes"),
            tags=list(snapshot.get("tags", [])),
            simulate=bool(snapshot["simulate"]),
            state=str(snapshot["state"]),
            error=snapshot.get("error"),
            started_at=snapshot["started_at"],
            stopped_at=snapshot.get("stopped_at"),
            device_info=snapshot.get("device_info"),
            live_state=snapshot.get("live_state"),
            artifacts=artifacts,
            proof_summary=snapshot.get("proof_summary"),
        )
