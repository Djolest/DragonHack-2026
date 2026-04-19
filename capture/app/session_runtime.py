from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import cv2

from .depth_challenge import LiveSessionState, RealnessVerifier, VerificationConfig
from .oak4_engine import (
    DeviceSummary,
    FrameSource,
    Oak4FrameSource,
    Oak4RuntimeConfig,
    SimulatedFrameSource,
    SyncedFrame,
)
from .storage import LocalStorage, SessionStoragePaths


FrameObserver = Callable[[SyncedFrame, LiveSessionState, DeviceSummary], bool | None]
FrameSourceFactory = Callable[[bool, str], FrameSource]


@dataclass(frozen=True, slots=True)
class SessionArtifacts:
    session_directory: str
    rgb_video_relative_path: str | None
    proof_relative_path: str | None
    receipt_relative_path: str | None
    rgb_video_uri: str | None
    proof_uri: str | None
    receipt_uri: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_directory": self.session_directory,
            "rgb_video_relative_path": self.rgb_video_relative_path,
            "proof_relative_path": self.proof_relative_path,
            "receipt_relative_path": self.receipt_relative_path,
            "rgb_video_uri": self.rgb_video_uri,
            "proof_uri": self.proof_uri,
            "receipt_uri": self.receipt_uri,
        }


class CaptureSessionRuntime:
    def __init__(
        self,
        *,
        session_id: str,
        asset_id: str,
        operator_id: str | None,
        notes: str | None,
        tags: list[str],
        simulate: bool,
        storage: LocalStorage,
        verification_config: VerificationConfig,
        public_base_url: str,
        frame_source_factory: FrameSourceFactory,
        observer: FrameObserver | None = None,
        runtime_fps: float = 20.0,
    ) -> None:
        self.session_id = session_id
        self.asset_id = asset_id
        self.operator_id = operator_id
        self.notes = notes
        self.tags = list(tags)
        self.simulate = simulate
        self.storage = storage
        self.verification_config = verification_config
        self.public_base_url = public_base_url
        self.frame_source_factory = frame_source_factory
        self.observer = observer
        self.runtime_fps = runtime_fps

        self.started_at = datetime.now(timezone.utc)
        self.stopped_at: datetime | None = None
        self.state = "created"
        self.error: str | None = None
        self.live_state: LiveSessionState | None = None
        self.device_summary: DeviceSummary | None = None
        self.proof_summary: dict[str, Any] | None = None
        self.artifacts: SessionArtifacts | None = None

        self._storage_paths = self.storage.prepare_session(self.session_id, self.started_at)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._started_event = threading.Event()
        self._verifier = RealnessVerifier(config=verification_config, seed=session_id)
        self._postprocessed = False

    def start(self, *, wait_timeout_seconds: float = 10.0) -> None:
        with self._lock:
            if self._thread is not None:
                raise RuntimeError("Session is already running.")
            self.state = "starting"
            self._thread = threading.Thread(
                target=self._run,
                name=f"capture-session-{self.session_id}",
                daemon=True,
            )
            self._thread.start()

        self._started_event.wait(timeout=wait_timeout_seconds)
        with self._lock:
            if self.error is not None and self.state == "failed":
                raise RuntimeError(self.error)

    def stop(self, *, wait_timeout_seconds: float = 20.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=wait_timeout_seconds)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "session_id": self.session_id,
                "asset_id": self.asset_id,
                "operator_id": self.operator_id,
                "notes": self.notes,
                "tags": self.tags,
                "simulate": self.simulate,
                "state": self.state,
                "error": self.error,
                "started_at": self.started_at,
                "stopped_at": self.stopped_at,
                "device_info": self.device_summary.to_dict() if self.device_summary else None,
                "live_state": self.live_state.to_dict() if self.live_state else None,
                "artifacts": self.artifacts.to_dict() if self.artifacts else None,
                "proof_summary": self.proof_summary,
            }

    def is_active(self) -> bool:
        with self._lock:
            return self.state in {"starting", "recording", "paused", "stopping"}

    def needs_postprocessing(self) -> bool:
        with self._lock:
            return self.state == "stopped" and not self._postprocessed

    def apply_postprocess(
        self,
        *,
        proof_summary: dict[str, Any] | None = None,
        artifacts: SessionArtifacts | None = None,
    ) -> None:
        with self._lock:
            if proof_summary is not None:
                self.proof_summary = proof_summary
            if artifacts is not None:
                self.artifacts = artifacts
            self._postprocessed = True

    def _run(self) -> None:
        frame_source = self.frame_source_factory(self.simulate, self.session_id)
        video_writer: cv2.VideoWriter | None = None
        nominal_frame_interval_seconds = 1.0 / max(1.0, self.runtime_fps)
        previous_frame_timestamp_seconds: float | None = None
        try:
            device_summary = frame_source.open()
            with self._lock:
                self.device_summary = device_summary
                self.state = "recording"
            self._started_event.set()

            while not self._stop_event.is_set():
                frame = frame_source.next_frame()
                if frame is None:
                    break

                if previous_frame_timestamp_seconds is None:
                    frame_interval_seconds = nominal_frame_interval_seconds
                else:
                    frame_interval_seconds = max(
                        0.0,
                        frame.timestamp_seconds - previous_frame_timestamp_seconds,
                    )
                    if frame_interval_seconds == 0.0:
                        frame_interval_seconds = nominal_frame_interval_seconds
                previous_frame_timestamp_seconds = frame.timestamp_seconds

                decision = self._verifier.update(
                    timestamp_seconds=frame.timestamp_seconds,
                    depth_frame=frame.depth_frame,
                    rgb_frame_shape=frame.rgb_frame.shape,
                    recording_frame_interval_seconds=frame_interval_seconds,
                )
                live_state = decision.live_state
                if decision.should_record_frame:
                    if video_writer is None:
                        video_writer = self._open_video_writer(
                            rgb_frame=frame.rgb_frame,
                            output_path=self._storage_paths.rgb_video_path,
                        )
                    video_writer.write(frame.rgb_frame)
                with self._lock:
                    self.live_state = live_state
                    self.state = live_state.recording_state

                if self.observer is not None:
                    should_continue = self.observer(frame, live_state, device_summary)
                    if should_continue is False:
                        self._stop_event.set()
                        break

            with self._lock:
                self.state = "stopping"
        except Exception as exc:  # pragma: no cover - covered indirectly via API/service tests
            with self._lock:
                self.error = str(exc)
                self.state = "failed"
            self._started_event.set()
            return
        finally:
            if video_writer is not None:
                video_writer.release()
            frame_source.close()

        proof_summary = self._verifier.build_summary(
            device_info=self.device_summary.to_dict() if self.device_summary else {"name": "unknown"},
        )
        self.storage.write_proof(self._storage_paths, proof_summary)
        rgb_video_relative_path = None
        rgb_video_uri = None
        if self._storage_paths.rgb_video_path.exists():
            rgb_video_relative_path = self._storage_paths.rgb_video_relative_path
            rgb_video_uri = self.storage.build_public_uri(
                self._storage_paths.rgb_video_relative_path,
                self.public_base_url,
            )
        artifacts = SessionArtifacts(
            session_directory=self._storage_paths.session_relative_path,
            rgb_video_relative_path=rgb_video_relative_path,
            proof_relative_path=self._storage_paths.proof_relative_path,
            receipt_relative_path=None,
            rgb_video_uri=rgb_video_uri,
            proof_uri=self.storage.build_public_uri(
                self._storage_paths.proof_relative_path,
                self.public_base_url,
            ),
            receipt_uri=None,
        )
        with self._lock:
            self.proof_summary = proof_summary
            self.artifacts = artifacts
            self.stopped_at = datetime.now(timezone.utc)
            self.state = "stopped"
            self._started_event.set()

    def _open_video_writer(self, *, rgb_frame: Any, output_path: Path) -> cv2.VideoWriter:
        frame_height, frame_width = rgb_frame.shape[:2]
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            self.runtime_fps,
            (frame_width, frame_height),
        )
        if not writer.isOpened():
            raise RuntimeError(f"Failed to open video writer for {output_path}.")
        return writer


class CaptureSessionManager:
    def __init__(
        self,
        *,
        storage: LocalStorage,
        verification_config: VerificationConfig,
        public_base_url: str,
        runtime_config: Oak4RuntimeConfig,
        oak_device_id: str | None,
        frame_source_factory: FrameSourceFactory | None = None,
        observer_factory: Callable[[], FrameObserver | None] | None = None,
    ) -> None:
        self.storage = storage
        self.verification_config = verification_config
        self.public_base_url = public_base_url
        self.runtime_config = runtime_config
        self.oak_device_id = oak_device_id
        self.frame_source_factory = frame_source_factory or self._default_frame_source_factory
        self.observer_factory = observer_factory
        self._sessions: dict[str, CaptureSessionRuntime] = {}
        self._lock = threading.Lock()

    def start_session(
        self,
        *,
        asset_id: str,
        operator_id: str | None,
        notes: str | None,
        tags: list[str],
        simulate: bool,
    ) -> CaptureSessionRuntime:
        with self._lock:
            if any(session.is_active() for session in self._sessions.values()):
                raise RuntimeError("Only one capture session can run at a time on this station.")

            session_id = str(uuid4())
            observer = self.observer_factory() if self.observer_factory is not None else None
            session = CaptureSessionRuntime(
                session_id=session_id,
                asset_id=asset_id,
                operator_id=operator_id,
                notes=notes,
                tags=tags,
                simulate=simulate,
                storage=self.storage,
                verification_config=self.verification_config,
                public_base_url=self.public_base_url,
                frame_source_factory=self.frame_source_factory,
                observer=observer,
                runtime_fps=self.runtime_config.fps,
            )
            self._sessions[session_id] = session

        session.start()
        return session

    def get_session(self, session_id: str) -> CaptureSessionRuntime:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(session_id)
            return self._sessions[session_id]

    def stop_session(self, session_id: str) -> CaptureSessionRuntime:
        session = self.get_session(session_id)
        session.stop()
        return session

    def _default_frame_source_factory(self, simulate: bool, _: str) -> FrameSource:
        if simulate:
            return SimulatedFrameSource(runtime_config=self.runtime_config)
        return Oak4FrameSource(
            runtime_config=self.runtime_config,
            oak_device_id=self.oak_device_id,
        )
