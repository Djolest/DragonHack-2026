from __future__ import annotations

import shutil
import time
from pathlib import Path
from uuid import uuid4

import numpy as np
from fastapi.testclient import TestClient

from app.config import Settings
from app.depth_challenge import VerificationConfig
from app.main import create_app
from app.oak4_engine import DeviceSummary, FrameSource, Oak4RuntimeConfig, SyncedFrame
from app.service import CaptureService
from app.session_runtime import CaptureSessionManager


FRAME_HEIGHT = 120
FRAME_WIDTH = 160
TEST_PRIVATE_KEY = "0x" + ("11" * 32)


def build_config(**overrides: object) -> VerificationConfig:
    values = {
        "scene_min_depth_mm": 180,
        "scene_max_depth_mm": 2200,
        "scene_min_valid_depth_ratio": 0.2,
        "flat_scene_min_valid_depth_ratio": 0.55,
        "reliable_depth_floor_mm": 220,
        "too_close_pixel_ratio": 0.08,
        "max_too_close_frame_ratio": 0.3,
        "min_analyzable_frames": 5,
        "scene_sampling_stride": 1,
        "plane_fit_min_points": 200,
        "max_plane_fit_points": 3000,
        "max_planar_plane_fit_rms_mm": 18.0,
        "max_planar_frame_ratio": 0.75,
        "min_depth_spread_mm": 120.0,
        "depth_spread_low_percentile": 5.0,
        "depth_spread_high_percentile": 95.0,
        "challenge_roi_width_fraction": 0.22,
        "challenge_roi_height_fraction": 0.24,
        "challenge_center_safe_width_fraction": 0.5,
        "challenge_center_safe_height_fraction": 0.5,
        "challenge_min_valid_depth_ratio": 0.35,
        "challenge_min_valid_frames_for_pass": 3,
        "challenge_min_forward_motion_mm": 90.0,
        "challenge_min_progress_frames_for_pass": 2,
        "challenge_min_progress_step_mm": 8.0,
        "challenge_min_motion_duration_seconds": 1.0,
        "challenge_timeout_seconds": 10.0,
        "challenge_schedule_min_seconds": 5.0,
        "challenge_schedule_max_seconds": 5.0,
        "workflow_confirmation_frames": 2,
        "recording_pause_confirmation_frames": 2,
        "post_challenge_resume_delay_seconds": 1.5,
    }
    values.update(overrides)
    return VerificationConfig(**values)


def non_planar_depth(object_depth_mm: float | None = None) -> np.ndarray:
    ys, xs = np.indices((FRAME_HEIGHT, FRAME_WIDTH))
    depth = (
        820.0
        + (110.0 * np.sin(xs / 8.0))
        + (70.0 * np.cos(ys / 7.0))
        + (0.6 * xs)
        + (0.3 * ys)
    )
    if object_depth_mm is not None:
        depth[24:96, 32:128] = object_depth_mm
    return depth.astype(np.uint16)


def planar_depth() -> np.ndarray:
    ys, xs = np.indices((FRAME_HEIGHT, FRAME_WIDTH))
    depth = 700.0 + (1.4 * xs) + (0.7 * ys)
    return depth.astype(np.uint16)


def low_spread_depth() -> np.ndarray:
    ys, xs = np.indices((FRAME_HEIGHT, FRAME_WIDTH))
    checker = ((xs // 6) + (ys // 6)) % 2
    depth = 780.0 + np.where(checker == 0, -24.0, 24.0)
    return depth.astype(np.uint16)


def too_close_depth() -> np.ndarray:
    return np.full((FRAME_HEIGHT, FRAME_WIDTH), 120, dtype=np.uint16)


def build_frames(depth_frames: list[np.ndarray]) -> list[SyncedFrame]:
    rgb_frame = np.full((FRAME_HEIGHT, FRAME_WIDTH, 3), 120, dtype=np.uint8)
    return [
        SyncedFrame(
            rgb_frame=rgb_frame.copy(),
            depth_frame=depth_frame,
            timestamp_seconds=float(index),
        )
        for index, depth_frame in enumerate(depth_frames)
    ]


class ScriptedFrameSource(FrameSource):
    def __init__(self, frames: list[SyncedFrame]) -> None:
        self.frames = frames
        self.index = 0

    def open(self) -> DeviceSummary:
        return DeviceSummary(
            name="sim-test",
            device_id="simulate",
            state="SIMULATED",
            platform="RVC4",
            product_name="OAK4-SIM",
            board_name="SIM",
            board_revision="SIM",
            connected_sockets=("CAM_A", "CAM_B", "CAM_C"),
            camera_sensors={"CAM_A": "SIM", "CAM_B": "SIM", "CAM_C": "SIM"},
            usb_speed="SIMULATED",
        )

    def next_frame(self) -> SyncedFrame | None:
        if self.index >= len(self.frames):
            return None
        frame = self.frames[self.index]
        self.index += 1
        return frame

    def close(self) -> None:
        return None


def make_client(
    tmp_path: Path,
    *,
    frames: list[SyncedFrame],
    verification_config: VerificationConfig | None = None,
) -> TestClient:
    settings = Settings(
        storage_root=tmp_path,
        public_base_url="http://testserver",
        backend_base_url=None,
        station_id="test-station",
        station_signer_private_key=TEST_PRIVATE_KEY,
        simulate=True,
        auto_submit_to_backend=False,
        runtime_fps=20.0,
        runtime_rgb_width=FRAME_WIDTH,
        runtime_rgb_height=FRAME_HEIGHT,
        runtime_stereo_width=FRAME_WIDTH,
        runtime_stereo_height=FRAME_HEIGHT,
    )
    service = CaptureService(settings)
    service.manager = CaptureSessionManager(
        storage=service.storage,
        verification_config=verification_config or build_config(),
        public_base_url=settings.public_base_url,
        runtime_config=Oak4RuntimeConfig(
            fps=20.0,
            rgb_size=(FRAME_WIDTH, FRAME_HEIGHT),
            stereo_size=(FRAME_WIDTH, FRAME_HEIGHT),
            sync_threshold_ms=50,
        ),
        oak_device_id=None,
        frame_source_factory=lambda _simulate, _session_id: ScriptedFrameSource(frames),
    )
    return TestClient(create_app(settings=settings, service=service))


def make_workspace_temp_path() -> Path:
    base_dir = Path.cwd() / ".test-artifacts"
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / str(uuid4())
    path.mkdir(parents=True, exist_ok=True)
    return path


def wait_for_terminal_state(client: TestClient, session_id: str) -> dict[str, object]:
    deadline = time.time() + 2.0
    while time.time() < deadline:
        response = client.get(f"/api/v1/capture/sessions/{session_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["state"] == "stopped":
            return payload
        time.sleep(0.01)
    raise AssertionError("Session did not reach a terminal state in time.")


def assert_artifacts_exist(tmp_path: Path, session_payload: dict[str, object]) -> None:
    artifacts = session_payload["artifacts"]
    assert artifacts is not None
    rgb_path = tmp_path / artifacts["rgb_video_relative_path"]
    proof_path = tmp_path / artifacts["proof_relative_path"]
    assert rgb_path.exists()
    assert rgb_path.stat().st_size > 0
    assert proof_path.exists()
    assert proof_path.stat().st_size > 0


def assert_no_rgb_artifact(session_payload: dict[str, object]) -> None:
    artifacts = session_payload["artifacts"]
    assert artifacts is not None
    assert artifacts["rgb_video_relative_path"] is None
    assert artifacts["rgb_video_uri"] is None


def test_session_api_returns_verified_proof_and_artifacts() -> None:
    tmp_path = make_workspace_temp_path()
    try:
        client = make_client(
            tmp_path,
            verification_config=build_config(
                challenge_schedule_min_seconds=50.0,
                challenge_schedule_max_seconds=50.0,
            ),
            frames=build_frames(
                [
                    non_planar_depth(980.0),
                    non_planar_depth(930.0),
                    non_planar_depth(860.0),
                    non_planar_depth(760.0),
                    non_planar_depth(680.0),
                    non_planar_depth(620.0),
                    non_planar_depth(620.0),
                    non_planar_depth(620.0),
                    non_planar_depth(620.0),
                    non_planar_depth(620.0),
                    non_planar_depth(620.0),
                    non_planar_depth(620.0),
                    non_planar_depth(620.0),
                    non_planar_depth(620.0),
                    non_planar_depth(620.0),
                    non_planar_depth(620.0),
                ]
            ),
        )

        start_response = client.post("/api/v1/capture/sessions", json={"asset_id": "asset-1"})
        assert start_response.status_code == 200
        session_id = start_response.json()["session_id"]

        terminal_payload = wait_for_terminal_state(client, session_id)
        stop_response = client.post(f"/api/v1/capture/sessions/{session_id}/stop")
        assert stop_response.status_code == 200
        session_payload = stop_response.json()["session"]

        assert terminal_payload["proof_summary"]["overall_status"] == "verified"
        assert session_payload["proof_summary"]["overall_status"] == "verified"
        assert session_payload["proof_summary"]["recorded_frames"] > 0
        assert (
            session_payload["proof_summary"]["recorded_frames"]
            < session_payload["proof_summary"]["frames_processed"]
        )
        receipt_workflow = session_payload["proof_summary"]["receipt_workflow"]
        assert receipt_workflow["status"] == "created_local"
        assert receipt_workflow["asset_hash"]
        assert session_payload["artifacts"]["receipt_relative_path"] is not None
        assert_artifacts_exist(tmp_path, session_payload)
        receipt_path = tmp_path / session_payload["artifacts"]["receipt_relative_path"]
        assert receipt_path.exists()
        assert receipt_path.stat().st_size > 0
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_session_api_pauses_when_scene_is_planar() -> None:
    tmp_path = make_workspace_temp_path()
    try:
        client = make_client(tmp_path, frames=build_frames([planar_depth() for _ in range(6)]))
        start_response = client.post("/api/v1/capture/sessions", json={"asset_id": "asset-plane"})
        session_id = start_response.json()["session_id"]

        terminal_payload = wait_for_terminal_state(client, session_id)
        assert terminal_payload["proof_summary"]["overall_status"] == "inconclusive"
        assert terminal_payload["live_state"]["recording_state"] == "paused"
        assert (
            terminal_payload["live_state"]["recording_pause_reason"]
            == "Recording paused because the scene looks too planar."
        )
        assert terminal_payload["proof_summary"]["recorded_frames"] == 0
        assert_no_rgb_artifact(terminal_payload)
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_session_api_pauses_when_depth_variance_is_low() -> None:
    tmp_path = make_workspace_temp_path()
    try:
        client = make_client(
            tmp_path,
            frames=build_frames([low_spread_depth() for _ in range(6)]),
            verification_config=build_config(min_depth_spread_mm=80.0),
        )
        start_response = client.post(
            "/api/v1/capture/sessions",
            json={"asset_id": "asset-variance"},
        )
        session_id = start_response.json()["session_id"]

        terminal_payload = wait_for_terminal_state(client, session_id)
        assert terminal_payload["proof_summary"]["overall_status"] == "inconclusive"
        assert terminal_payload["live_state"]["recording_state"] == "paused"
        assert (
            terminal_payload["live_state"]["recording_pause_reason"]
            == "Recording paused until the scene shows more depth variation."
        )
        assert terminal_payload["proof_summary"]["recorded_frames"] == 0
        assert_no_rgb_artifact(terminal_payload)
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_session_api_pauses_when_scene_is_too_close() -> None:
    tmp_path = make_workspace_temp_path()
    try:
        client = make_client(tmp_path, frames=build_frames([too_close_depth() for _ in range(6)]))
        start_response = client.post("/api/v1/capture/sessions", json={"asset_id": "asset-close"})
        session_id = start_response.json()["session_id"]

        terminal_payload = wait_for_terminal_state(client, session_id)
        assert terminal_payload["proof_summary"]["overall_status"] == "inconclusive"
        assert terminal_payload["live_state"]["recording_state"] == "paused"
        assert (
            terminal_payload["live_state"]["recording_pause_reason"]
            == "Recording paused until the subject moves farther from the camera."
        )
        assert terminal_payload["proof_summary"]["recorded_frames"] == 0
        assert_no_rgb_artifact(terminal_payload)
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_session_api_stays_inconclusive_if_challenge_is_not_completed() -> None:
    tmp_path = make_workspace_temp_path()
    try:
        frames = build_frames([non_planar_depth(980.0) for _ in range(12)])
        client = make_client(tmp_path, frames=frames)
        start_response = client.post(
            "/api/v1/capture/sessions",
            json={"asset_id": "asset-challenge"},
        )
        session_id = start_response.json()["session_id"]

        terminal_payload = wait_for_terminal_state(client, session_id)
        assert terminal_payload["proof_summary"]["overall_status"] == "inconclusive"
        assert terminal_payload["live_state"]["recording_state"] == "paused"
        assert (
            terminal_payload["live_state"]["recording_pause_reason"]
            == "Recording paused until the current challenge is completed."
        )
        assert terminal_payload["proof_summary"]["recorded_frames"] == 0
        assert terminal_payload["proof_summary"]["passed_challenges"] == 0
        assert_no_rgb_artifact(terminal_payload)
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
