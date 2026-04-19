from __future__ import annotations

import numpy as np

from app.depth_challenge import RealnessVerifier, VerificationConfig


FRAME_HEIGHT = 120
FRAME_WIDTH = 160
RGB_FRAME_SHAPE = (FRAME_HEIGHT, FRAME_WIDTH, 3)


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


def far_background_depth() -> np.ndarray:
    depth = np.full((FRAME_HEIGHT, FRAME_WIDTH), 3600, dtype=np.uint16)
    depth[18:102, 26:134] = 820
    return depth


def update_verifier(verifier: RealnessVerifier, frames: list[np.ndarray], dt_seconds: float = 1.0):
    live_state = None
    for index, depth_frame in enumerate(frames):
        decision = verifier.update(
            timestamp_seconds=float(index) * dt_seconds,
            depth_frame=depth_frame,
            rgb_frame_shape=RGB_FRAME_SHAPE,
            recording_frame_interval_seconds=dt_seconds,
        )
        live_state = decision.live_state
    assert live_state is not None
    return live_state


def test_planar_scene_pauses_recording_until_valid() -> None:
    verifier = RealnessVerifier(config=build_config(), seed="plane-test")
    live_state = update_verifier(verifier, [planar_depth() for _ in range(6)])
    summary = verifier.build_summary(device_info={"name": "sim"})

    assert live_state.recording_state == "paused"
    assert live_state.recording_pause_reason == "Recording paused because the scene looks too planar."
    assert summary["overall_status"] == "inconclusive"
    assert summary["recorded_frames"] == 0


def test_low_variance_scene_pauses_recording_until_valid() -> None:
    verifier = RealnessVerifier(config=build_config(min_depth_spread_mm=80.0), seed="variance-test")
    live_state = update_verifier(verifier, [low_spread_depth() for _ in range(6)])
    summary = verifier.build_summary(device_info={"name": "sim"})

    assert live_state.recording_state == "paused"
    assert (
        live_state.recording_pause_reason
        == "Recording paused until the scene shows more depth variation."
    )
    assert summary["overall_status"] == "inconclusive"
    assert summary["recorded_frames"] == 0


def test_too_close_scene_pauses_recording_until_valid() -> None:
    verifier = RealnessVerifier(config=build_config(), seed="too-close-test")
    live_state = update_verifier(verifier, [too_close_depth() for _ in range(6)])
    summary = verifier.build_summary(device_info={"name": "sim"})

    assert live_state.recording_state == "paused"
    assert (
        live_state.recording_pause_reason
        == "Recording paused until the subject moves farther from the camera."
    )
    assert summary["overall_status"] == "inconclusive"
    assert summary["recorded_frames"] == 0


def test_challenge_pauses_recording_until_completed_and_then_reschedules() -> None:
    verifier = RealnessVerifier(
        config=build_config(
            challenge_schedule_min_seconds=50.0,
            challenge_schedule_max_seconds=50.0,
            challenge_min_motion_duration_seconds=2.0,
        ),
        seed="challenge-test",
    )
    live_state = update_verifier(
        verifier,
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
        ],
    )

    summary = verifier.build_summary(device_info={"name": "sim"})
    assert summary["overall_status"] == "verified"
    assert summary["passed_challenges"] >= 1
    assert summary["recorded_frames"] > 0
    assert summary["recorded_frames"] < summary["frames_processed"]
    assert live_state.recording_state == "recording"
    assert live_state.next_challenge_eta_seconds is not None
    assert 40.0 <= live_state.next_challenge_eta_seconds <= 50.0

    next_state = verifier.update(
        timestamp_seconds=10.0,
        depth_frame=non_planar_depth(980.0),
        rgb_frame_shape=RGB_FRAME_SHAPE,
        recording_frame_interval_seconds=1.0,
    )
    assert next_state.live_state.current_challenge is None


def test_recording_ignores_brief_depth_variance_wobble() -> None:
    verifier = RealnessVerifier(
        config=build_config(
            min_depth_spread_mm=120.0,
            recording_pause_confirmation_frames=3,
        ),
        seed="recording-variance-hysteresis",
    )
    verifier.workflow_stage = "recording"
    verifier.challenge_required_before_recording = False
    verifier.next_challenge_time_seconds = 999.0
    verifier.recorded_duration_seconds = 10.0

    decisions = []
    for index, depth_frame in enumerate(
        [
            non_planar_depth(620.0),
            low_spread_depth(),
            low_spread_depth(),
            non_planar_depth(620.0),
        ]
    ):
        decisions.append(
            verifier.update(
                timestamp_seconds=float(index),
                depth_frame=depth_frame,
                rgb_frame_shape=RGB_FRAME_SHAPE,
                recording_frame_interval_seconds=1.0,
            )
        )

    assert all(decision.should_record_frame for decision in decisions)
    assert verifier.workflow_stage == "recording"
    assert verifier.recorded_frames == 4
    assert verifier.latest_state is not None
    assert verifier.latest_state.recording_state == "recording"


def test_recording_does_not_pause_when_only_partial_scene_has_reliable_depth() -> None:
    verifier = RealnessVerifier(
        config=build_config(
            scene_max_depth_mm=2200,
            flat_scene_min_valid_depth_ratio=0.55,
            recording_pause_confirmation_frames=2,
        ),
        seed="partial-depth-coverage",
    )
    verifier.workflow_stage = "recording"
    verifier.challenge_required_before_recording = False
    verifier.next_challenge_time_seconds = 999.0
    verifier.recorded_duration_seconds = 10.0

    decisions = []
    for index in range(4):
        decisions.append(
            verifier.update(
                timestamp_seconds=float(index),
                depth_frame=far_background_depth(),
                rgb_frame_shape=RGB_FRAME_SHAPE,
                recording_frame_interval_seconds=1.0,
            )
        )

    assert all(decision.should_record_frame for decision in decisions)
    assert verifier.workflow_stage == "recording"
    assert verifier.latest_state is not None
    assert verifier.latest_state.recording_state == "recording"


def test_challenge_timeout_marks_failure_and_reissues() -> None:
    verifier = RealnessVerifier(
        config=build_config(
            workflow_confirmation_frames=1,
            challenge_timeout_seconds=3.0,
        ),
        seed="challenge-timeout",
    )
    live_state = update_verifier(verifier, [non_planar_depth(980.0) for _ in range(6)])
    summary = verifier.build_summary(device_info={"name": "sim"})

    assert live_state.recording_state == "paused"
    assert live_state.current_challenge is not None
    assert live_state.current_challenge.challenge_id == 2
    assert summary["failed_challenges"] == 1
    assert summary["challenge_summary"]["events"][0]["state"] == "failed"
    assert "timed out" in summary["challenge_summary"]["events"][0]["close_reason"]


def test_too_close_scene_check_fails_when_ratio_exceeds_threshold() -> None:
    verifier = RealnessVerifier(
        config=build_config(
            min_analyzable_frames=2,
            workflow_confirmation_frames=1,
            recording_pause_confirmation_frames=1,
        ),
        seed="too-close-ratio",
    )
    verifier.workflow_stage = "recording"
    verifier.challenge_required_before_recording = False
    verifier.next_challenge_time_seconds = 999.0
    verifier.recorded_duration_seconds = 10.0

    for index, depth_frame in enumerate(
        [
            non_planar_depth(620.0),
            too_close_depth(),
            too_close_depth(),
            non_planar_depth(620.0),
        ]
    ):
        verifier.update(
            timestamp_seconds=float(index),
            depth_frame=depth_frame,
            rgb_frame_shape=RGB_FRAME_SHAPE,
            recording_frame_interval_seconds=1.0,
        )

    summary = verifier.build_summary(device_info={"name": "sim"})
    assert summary["scene_checks"]["too_close"]["status"] == "failed"
    assert summary["scene_checks"]["too_close"]["observed_value"] > 0.3


def test_challenge_requires_steady_progress_over_time() -> None:
    verifier = RealnessVerifier(
        config=build_config(
            workflow_confirmation_frames=1,
            challenge_min_valid_frames_for_pass=3,
            challenge_min_progress_frames_for_pass=3,
            challenge_min_motion_duration_seconds=1.0,
        ),
        seed="challenge-steady-progress",
    )
    live_state = update_verifier(
        verifier,
        [
            non_planar_depth(980.0),
            non_planar_depth(620.0),
            non_planar_depth(620.0),
            non_planar_depth(620.0),
            non_planar_depth(620.0),
        ],
        dt_seconds=0.1,
    )

    assert live_state.recording_state == "paused"
    assert live_state.current_challenge is not None
    assert live_state.current_challenge.progress_frames < 3
    assert live_state.current_challenge.max_forward_motion_mm >= 90.0


def test_challenge_can_pass_when_close_motion_triggers_scene_too_close() -> None:
    verifier = RealnessVerifier(
        config=build_config(
            challenge_min_valid_frames_for_pass=4,
            challenge_min_progress_frames_for_pass=3,
            challenge_min_motion_duration_seconds=1.0,
        ),
        seed="challenge-close-object",
    )
    verifier.workflow_stage = "challenge"

    live_state = update_verifier(
        verifier,
        [
            non_planar_depth(980.0),
            non_planar_depth(930.0),
            non_planar_depth(860.0),
            non_planar_depth(210.0),
            non_planar_depth(210.0),
        ],
        dt_seconds=1.0,
    )

    summary = verifier.build_summary(device_info={"name": "sim"})
    assert summary["passed_challenges"] >= 1
    assert live_state.recording_state in {"paused", "recording"}
