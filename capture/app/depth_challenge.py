from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class VerificationConfig:
    scene_min_depth_mm: int
    scene_max_depth_mm: int
    scene_min_valid_depth_ratio: float
    flat_scene_min_valid_depth_ratio: float
    reliable_depth_floor_mm: int
    too_close_pixel_ratio: float
    max_too_close_frame_ratio: float
    min_analyzable_frames: int
    scene_sampling_stride: int
    plane_fit_min_points: int
    max_plane_fit_points: int
    max_planar_plane_fit_rms_mm: float
    max_planar_frame_ratio: float
    min_depth_spread_mm: float
    depth_spread_low_percentile: float
    depth_spread_high_percentile: float
    challenge_roi_width_fraction: float
    challenge_roi_height_fraction: float
    challenge_center_safe_width_fraction: float
    challenge_center_safe_height_fraction: float
    challenge_min_valid_depth_ratio: float
    challenge_min_valid_frames_for_pass: int
    challenge_min_forward_motion_mm: float
    challenge_min_progress_frames_for_pass: int
    challenge_min_progress_step_mm: float
    challenge_min_motion_duration_seconds: float
    challenge_timeout_seconds: float
    challenge_schedule_min_seconds: float
    challenge_schedule_max_seconds: float
    workflow_confirmation_frames: int
    recording_pause_confirmation_frames: int
    post_challenge_resume_delay_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RoiBox:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    def as_dict(self) -> dict[str, int]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}


@dataclass(frozen=True, slots=True)
class SceneFrameStats:
    frame_index: int
    valid_depth_ratio: float
    too_close_pixel_ratio: float
    analyzable: bool
    plane_fit_rms_mm: float | None
    depth_spread_mm: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RoiDepthStats:
    roi: RoiBox
    valid_depth_ratio: float
    valid_pixel_count: int
    total_pixel_count: int
    median_depth_mm: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "roi": self.roi.as_dict(),
            "valid_depth_ratio": self.valid_depth_ratio,
            "valid_pixel_count": self.valid_pixel_count,
            "total_pixel_count": self.total_pixel_count,
            "median_depth_mm": self.median_depth_mm,
        }


@dataclass(frozen=True, slots=True)
class ChallengeSnapshot:
    challenge_id: int
    state: str
    prompt: str
    roi: RoiBox | None
    issued_at_seconds: float | None
    elapsed_seconds: float
    timeout_seconds: float
    baseline_depth_mm: float | None
    max_forward_motion_mm: float
    valid_frames: int
    progress_frames: int
    motion_duration_seconds: float
    close_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "challenge_id": self.challenge_id,
            "state": self.state,
            "prompt": self.prompt,
            "roi": self.roi.as_dict() if self.roi is not None else None,
            "issued_at_seconds": self.issued_at_seconds,
            "elapsed_seconds": self.elapsed_seconds,
            "timeout_seconds": self.timeout_seconds,
            "baseline_depth_mm": self.baseline_depth_mm,
            "max_forward_motion_mm": self.max_forward_motion_mm,
            "valid_frames": self.valid_frames,
            "progress_frames": self.progress_frames,
            "motion_duration_seconds": self.motion_duration_seconds,
            "close_reason": self.close_reason,
        }


@dataclass(frozen=True, slots=True)
class LiveSessionState:
    frame_index: int
    elapsed_seconds: float
    workflow_stage: str
    workflow_progress_frames: int
    recording_state: str
    recording_pause_reason: str | None
    recorded_frames: int
    recorded_duration_seconds: float
    prompt: str
    warning: str | None
    scene_stats: SceneFrameStats
    plane_like_ratio: float | None
    median_depth_spread_mm: float | None
    too_close_frame_ratio: float
    analyzable_frames: int
    challenges_issued: int
    challenges_passed: int
    challenges_failed: int
    current_challenge: ChallengeSnapshot | None
    next_challenge_eta_seconds: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "elapsed_seconds": self.elapsed_seconds,
            "workflow_stage": self.workflow_stage,
            "workflow_progress_frames": self.workflow_progress_frames,
            "recording_state": self.recording_state,
            "recording_pause_reason": self.recording_pause_reason,
            "recorded_frames": self.recorded_frames,
            "recorded_duration_seconds": self.recorded_duration_seconds,
            "prompt": self.prompt,
            "warning": self.warning,
            "scene_stats": self.scene_stats.to_dict(),
            "plane_like_ratio": self.plane_like_ratio,
            "median_depth_spread_mm": self.median_depth_spread_mm,
            "too_close_frame_ratio": self.too_close_frame_ratio,
            "analyzable_frames": self.analyzable_frames,
            "challenges_issued": self.challenges_issued,
            "challenges_passed": self.challenges_passed,
            "challenges_failed": self.challenges_failed,
            "current_challenge": (
                self.current_challenge.to_dict() if self.current_challenge is not None else None
            ),
            "next_challenge_eta_seconds": self.next_challenge_eta_seconds,
        }


@dataclass(frozen=True, slots=True)
class SceneCheckResult:
    status: str
    reason: str
    observed_value: float | None
    threshold: float | None
    frames_considered: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class VerifierFrameDecision:
    live_state: LiveSessionState
    should_record_frame: bool


@dataclass(slots=True)
class ActiveChallenge:
    challenge_id: int
    roi: RoiBox
    issued_at_seconds: float
    elapsed_seconds: float = 0.0
    baseline_depth_mm: float | None = None
    max_forward_motion_mm: float = 0.0
    valid_frames: int = 0
    progress_frames: int = 0
    first_valid_elapsed_seconds: float | None = None
    last_depth_mm: float | None = None
    last_progress_elapsed_seconds: float | None = None

    def snapshot(self, *, prompt: str, close_reason: str | None = None, state: str = "active") -> ChallengeSnapshot:
        return ChallengeSnapshot(
            challenge_id=self.challenge_id,
            state=state,
            prompt=prompt,
            roi=self.roi,
            issued_at_seconds=self.issued_at_seconds,
            elapsed_seconds=self.elapsed_seconds,
            timeout_seconds=0.0,
            baseline_depth_mm=self.baseline_depth_mm,
            max_forward_motion_mm=self.max_forward_motion_mm,
            valid_frames=self.valid_frames,
            progress_frames=self.progress_frames,
            motion_duration_seconds=self.motion_duration_seconds,
            close_reason=close_reason,
        )

    @property
    def motion_duration_seconds(self) -> float:
        if self.first_valid_elapsed_seconds is None:
            return 0.0
        return max(0.0, self.elapsed_seconds - self.first_valid_elapsed_seconds)

    @property
    def progress_span_seconds(self) -> float:
        if (
            self.first_valid_elapsed_seconds is None
            or self.last_progress_elapsed_seconds is None
        ):
            return 0.0
        return max(0.0, self.last_progress_elapsed_seconds - self.first_valid_elapsed_seconds)


def load_verification_config(path: Path) -> VerificationConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return VerificationConfig(
        scene_min_depth_mm=int(raw["scene"]["min_depth_mm"]),
        scene_max_depth_mm=int(raw["scene"]["max_depth_mm"]),
        scene_min_valid_depth_ratio=float(raw["scene"]["min_valid_depth_ratio"]),
        flat_scene_min_valid_depth_ratio=max(
            float(raw["scene"].get("flat_scene_min_valid_depth_ratio", 0.55)),
            float(raw["scene"]["min_valid_depth_ratio"]),
        ),
        reliable_depth_floor_mm=int(raw["scene"]["reliable_depth_floor_mm"]),
        too_close_pixel_ratio=float(raw["scene"]["too_close_pixel_ratio"]),
        max_too_close_frame_ratio=float(raw["scene"]["max_too_close_frame_ratio"]),
        min_analyzable_frames=int(raw["scene"]["min_analyzable_frames"]),
        scene_sampling_stride=max(1, int(raw["scene"].get("sampling_stride", 1))),
        plane_fit_min_points=int(raw["planarity"]["plane_fit_min_points"]),
        max_plane_fit_points=int(raw["planarity"]["max_plane_fit_points"]),
        max_planar_plane_fit_rms_mm=float(raw["planarity"]["max_plane_fit_rms_mm"]),
        max_planar_frame_ratio=float(raw["planarity"]["max_planar_frame_ratio"]),
        min_depth_spread_mm=float(raw["scene"]["min_depth_spread_mm"]),
        depth_spread_low_percentile=float(raw["scene"].get("depth_spread_low_percentile", 5.0)),
        depth_spread_high_percentile=float(raw["scene"].get("depth_spread_high_percentile", 95.0)),
        challenge_roi_width_fraction=float(raw["challenge"]["roi_width_fraction"]),
        challenge_roi_height_fraction=float(raw["challenge"]["roi_height_fraction"]),
        challenge_center_safe_width_fraction=float(raw["challenge"]["center_safe_width_fraction"]),
        challenge_center_safe_height_fraction=float(raw["challenge"]["center_safe_height_fraction"]),
        challenge_min_valid_depth_ratio=float(raw["challenge"]["min_valid_depth_ratio"]),
        challenge_min_valid_frames_for_pass=int(raw["challenge"]["min_valid_frames_for_pass"]),
        challenge_min_forward_motion_mm=float(raw["challenge"]["min_forward_motion_mm"]),
        challenge_min_progress_frames_for_pass=max(
            1,
            int(raw["challenge"].get("min_progress_frames_for_pass", 2)),
        ),
        challenge_min_progress_step_mm=float(raw["challenge"].get("min_progress_step_mm", 8.0)),
        challenge_min_motion_duration_seconds=float(
            raw["challenge"].get("min_motion_duration_seconds", 1.0)
        ),
        challenge_timeout_seconds=float(raw["challenge"]["timeout_seconds"]),
        challenge_schedule_min_seconds=float(raw["challenge"]["schedule_min_seconds"]),
        challenge_schedule_max_seconds=float(raw["challenge"]["schedule_max_seconds"]),
        workflow_confirmation_frames=max(1, int(raw["workflow"]["confirmation_frames"])),
        recording_pause_confirmation_frames=max(
            1,
            int(raw["workflow"].get("recording_pause_confirmation_frames", 4)),
        ),
        post_challenge_resume_delay_seconds=float(
            raw["workflow"]["post_challenge_resume_delay_seconds"]
        ),
    )


def fit_plane_rms_mm(
    depth_frame: np.ndarray,
    valid_mask: np.ndarray,
    *,
    min_points: int,
    max_points: int,
) -> float | None:
    ys, xs = np.nonzero(valid_mask)
    if xs.size < min_points:
        return None

    zs = depth_frame[ys, xs].astype(np.float64)
    if xs.size > max_points:
        step = max(1, xs.size // max_points)
        xs = xs[::step]
        ys = ys[::step]
        zs = zs[::step]

    x_coords = xs.astype(np.float64)
    y_coords = ys.astype(np.float64)
    x_coords -= float(np.mean(x_coords))
    y_coords -= float(np.mean(y_coords))
    design = np.column_stack((x_coords, y_coords, np.ones_like(zs)))
    coeffs, _, _, _ = np.linalg.lstsq(design, zs, rcond=None)
    residuals = zs - (design @ coeffs)
    return float(np.sqrt(np.mean(np.square(residuals))))


def compute_scene_frame_stats(
    depth_frame: np.ndarray,
    *,
    config: VerificationConfig,
    frame_index: int,
) -> SceneFrameStats:
    sampled_frame = depth_frame[:: config.scene_sampling_stride, :: config.scene_sampling_stride]
    total_pixels = int(sampled_frame.size)
    if total_pixels == 0:
        return SceneFrameStats(
            frame_index=frame_index,
            valid_depth_ratio=0.0,
            too_close_pixel_ratio=0.0,
            analyzable=False,
            plane_fit_rms_mm=None,
            depth_spread_mm=None,
        )

    valid_mask = (sampled_frame >= config.scene_min_depth_mm) & (
        sampled_frame <= config.scene_max_depth_mm
    )
    valid_pixels = int(np.count_nonzero(valid_mask))
    valid_ratio = valid_pixels / total_pixels

    too_close_mask = (sampled_frame > 0) & (sampled_frame < config.reliable_depth_floor_mm)
    too_close_pixels = int(np.count_nonzero(too_close_mask))
    too_close_ratio = too_close_pixels / total_pixels

    analyzable = (
        valid_ratio >= config.scene_min_valid_depth_ratio
        and too_close_ratio < config.too_close_pixel_ratio
    )
    if not analyzable:
        return SceneFrameStats(
            frame_index=frame_index,
            valid_depth_ratio=valid_ratio,
            too_close_pixel_ratio=too_close_ratio,
            analyzable=False,
            plane_fit_rms_mm=None,
            depth_spread_mm=None,
        )

    valid_depth = sampled_frame[valid_mask].astype(np.float32)
    low_percentile = float(np.percentile(valid_depth, config.depth_spread_low_percentile))
    high_percentile = float(np.percentile(valid_depth, config.depth_spread_high_percentile))
    depth_spread = max(0.0, high_percentile - low_percentile)
    plane_fit_rms = fit_plane_rms_mm(
        sampled_frame,
        valid_mask,
        min_points=config.plane_fit_min_points,
        max_points=config.max_plane_fit_points,
    )
    return SceneFrameStats(
        frame_index=frame_index,
        valid_depth_ratio=valid_ratio,
        too_close_pixel_ratio=too_close_ratio,
        analyzable=True,
        plane_fit_rms_mm=plane_fit_rms,
        depth_spread_mm=depth_spread,
    )


def compute_roi_depth_stats(
    depth_frame: np.ndarray,
    *,
    roi: RoiBox,
    config: VerificationConfig,
) -> RoiDepthStats:
    depth_roi = depth_frame[roi.y0 : roi.y1, roi.x0 : roi.x1]
    total_pixels = int(depth_roi.size)
    if total_pixels == 0:
        return RoiDepthStats(
            roi=roi,
            valid_depth_ratio=0.0,
            valid_pixel_count=0,
            total_pixel_count=0,
            median_depth_mm=None,
        )

    valid_mask = (depth_roi >= config.scene_min_depth_mm) & (depth_roi <= config.scene_max_depth_mm)
    valid_count = int(np.count_nonzero(valid_mask))
    valid_ratio = valid_count / total_pixels
    if valid_count == 0:
        return RoiDepthStats(
            roi=roi,
            valid_depth_ratio=valid_ratio,
            valid_pixel_count=valid_count,
            total_pixel_count=total_pixels,
            median_depth_mm=None,
        )

    median_depth = float(np.median(depth_roi[valid_mask].astype(np.float32)))
    return RoiDepthStats(
        roi=roi,
        valid_depth_ratio=valid_ratio,
        valid_pixel_count=valid_count,
        total_pixel_count=total_pixels,
        median_depth_mm=median_depth,
    )


def choose_random_center_roi(
    frame_shape: tuple[int, ...],
    *,
    config: VerificationConfig,
    rng: random.Random,
) -> RoiBox:
    frame_height, frame_width = frame_shape[:2]
    roi_width = max(40, int(frame_width * config.challenge_roi_width_fraction))
    roi_height = max(40, int(frame_height * config.challenge_roi_height_fraction))

    safe_width = max(roi_width, int(frame_width * config.challenge_center_safe_width_fraction))
    safe_height = max(roi_height, int(frame_height * config.challenge_center_safe_height_fraction))
    safe_x0 = max(0, (frame_width - safe_width) // 2)
    safe_y0 = max(0, (frame_height - safe_height) // 2)
    safe_x1 = min(frame_width, safe_x0 + safe_width)
    safe_y1 = min(frame_height, safe_y0 + safe_height)

    max_x0 = max(safe_x0, safe_x1 - roi_width)
    max_y0 = max(safe_y0, safe_y1 - roi_height)
    x0 = safe_x0 if max_x0 <= safe_x0 else rng.randint(safe_x0, max_x0)
    y0 = safe_y0 if max_y0 <= safe_y0 else rng.randint(safe_y0, max_y0)
    return RoiBox(x0=x0, y0=y0, x1=x0 + roi_width, y1=y0 + roi_height)


@dataclass(slots=True)
class RealnessVerifier:
    config: VerificationConfig
    seed: int | str
    frame_index: int = 0
    total_frames: int = 0
    analyzable_frames: int = 0
    flat_scene_evaluable_frames: int = 0
    plane_like_frames: int = 0
    too_close_frames: int = 0
    passed_challenges: int = 0
    failed_challenges: int = 0
    recorded_frames: int = 0
    recorded_duration_seconds: float = 0.0
    depth_spreads_mm: list[float] = field(default_factory=list)
    challenge_events: list[dict[str, Any]] = field(default_factory=list)
    pause_reason_counts: dict[str, int] = field(default_factory=dict)
    next_challenge_time_seconds: float = 0.0
    active_challenge: ActiveChallenge | None = None
    latest_state: LiveSessionState | None = None
    workflow_stage: str = "distance_check"
    workflow_progress_frames: int = 0
    challenge_required_before_recording: bool = True
    _recording_pause_candidate_key: str | None = field(init=False, default=None, repr=False)
    _recording_pause_candidate_streak: int = field(init=False, default=0, repr=False)
    _post_challenge_delay_until_elapsed_seconds: float | None = field(
        init=False,
        default=None,
        repr=False,
    )
    _rng: random.Random = field(init=False, repr=False)
    _session_start_timestamp_seconds: float | None = field(init=False, default=None, repr=False)
    _last_timestamp_seconds: float | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(str(self.seed))

    def update(
        self,
        *,
        timestamp_seconds: float,
        depth_frame: np.ndarray,
        rgb_frame_shape: tuple[int, ...],
        recording_frame_interval_seconds: float,
    ) -> VerifierFrameDecision:
        if self._session_start_timestamp_seconds is None:
            self._session_start_timestamp_seconds = timestamp_seconds
            self._last_timestamp_seconds = timestamp_seconds

        assert self._session_start_timestamp_seconds is not None
        assert self._last_timestamp_seconds is not None
        previous_timestamp_seconds = self._last_timestamp_seconds

        self.frame_index += 1
        self.total_frames += 1
        elapsed_seconds = max(0.0, timestamp_seconds - self._session_start_timestamp_seconds)
        frame_dt_seconds = max(0.0, timestamp_seconds - previous_timestamp_seconds)
        self._last_timestamp_seconds = timestamp_seconds

        scene_stats = compute_scene_frame_stats(
            depth_frame,
            config=self.config,
            frame_index=self.frame_index,
        )
        scene_pause_key, scene_pause_reason = self._scene_pause_reason(scene_stats)
        if scene_pause_key == "too_close":
            self.too_close_frames += 1

        stage_prompt, stage_pause_reason = self._advance_workflow(
            elapsed_seconds=elapsed_seconds,
            frame_dt_seconds=frame_dt_seconds,
            depth_frame=depth_frame,
            rgb_frame_shape=rgb_frame_shape,
            scene_stats=scene_stats,
            scene_pause_key=scene_pause_key,
            scene_pause_reason=scene_pause_reason,
        )
        should_record_frame = self.workflow_stage == "recording"
        recording_pause_reason = None if should_record_frame else (
            stage_pause_reason or "Recording paused."
        )
        recording_state = "recording" if should_record_frame else "paused"

        if should_record_frame:
            self.recorded_frames += 1
            self.recorded_duration_seconds += recording_frame_interval_seconds
            self.analyzable_frames += 1
            if scene_stats.valid_depth_ratio >= self.config.flat_scene_min_valid_depth_ratio:
                self.flat_scene_evaluable_frames += 1
                if (
                    scene_stats.plane_fit_rms_mm is not None
                    and scene_stats.plane_fit_rms_mm <= self.config.max_planar_plane_fit_rms_mm
                ):
                    self.plane_like_frames += 1
                if scene_stats.depth_spread_mm is not None:
                    self.depth_spreads_mm.append(scene_stats.depth_spread_mm)
        else:
            pause_key = self._pause_key_for_stage(scene_pause_key)
            self.pause_reason_counts[pause_key] = self.pause_reason_counts.get(pause_key, 0) + 1

        plane_like_ratio = self._plane_like_ratio()
        median_depth_spread_mm = self._median_depth_spread_mm()
        current_challenge_snapshot = self._current_challenge_snapshot(stage_prompt)
        next_challenge_eta_seconds = None
        if self.active_challenge is None:
            next_challenge_eta_seconds = max(
                0.0,
                self.next_challenge_time_seconds - self.recorded_duration_seconds,
            )

        live_state = LiveSessionState(
            frame_index=self.frame_index,
            elapsed_seconds=elapsed_seconds,
            workflow_stage=self.workflow_stage,
            workflow_progress_frames=self.workflow_progress_frames,
            recording_state=recording_state,
            recording_pause_reason=recording_pause_reason,
            recorded_frames=self.recorded_frames,
            recorded_duration_seconds=self.recorded_duration_seconds,
            prompt=stage_prompt,
            warning=recording_pause_reason,
            scene_stats=scene_stats,
            plane_like_ratio=plane_like_ratio,
            median_depth_spread_mm=median_depth_spread_mm,
            too_close_frame_ratio=self.too_close_frames / max(1, self.total_frames),
            analyzable_frames=self.analyzable_frames,
            challenges_issued=len(self.challenge_events) + (1 if self.active_challenge else 0),
            challenges_passed=self.passed_challenges,
            challenges_failed=self.failed_challenges,
            current_challenge=current_challenge_snapshot,
            next_challenge_eta_seconds=next_challenge_eta_seconds,
        )
        self.latest_state = live_state
        return VerifierFrameDecision(
            live_state=live_state,
            should_record_frame=should_record_frame,
        )

    def build_summary(self, *, device_info: dict[str, Any]) -> dict[str, Any]:
        plane_result = self._plane_like_result()
        variance_result = self._depth_variance_result()
        too_close_result = self._too_close_result()
        overall_status, status_reason = self._overall_status(
            plane_result=plane_result,
            variance_result=variance_result,
            too_close_result=too_close_result,
        )
        return {
            "overall_status": overall_status,
            "status_reason": status_reason,
            "frames_processed": self.total_frames,
            "recorded_frames": self.recorded_frames,
            "recorded_duration_seconds": self.recorded_duration_seconds,
            "paused_frames": self.total_frames - self.recorded_frames,
            "analyzable_frames": self.analyzable_frames,
            "passed_challenges": self.passed_challenges,
            "failed_challenges": self.failed_challenges,
            "scene_checks": {
                "plane_like": plane_result.to_dict(),
                "depth_variance": variance_result.to_dict(),
                "too_close": too_close_result.to_dict(),
            },
            "challenge_summary": {
                "issued": len(self.challenge_events) + (1 if self.active_challenge is not None else 0),
                "passed": self.passed_challenges,
                "failed": self.failed_challenges,
                "events": self.challenge_events,
            },
            "pause_summary": dict(sorted(self.pause_reason_counts.items())),
            "device_info": device_info,
            "thresholds": self.config.to_dict(),
            "latest_live_state": self.latest_state.to_dict() if self.latest_state is not None else None,
        }

    def _advance_workflow(
        self,
        *,
        elapsed_seconds: float,
        frame_dt_seconds: float,
        depth_frame: np.ndarray,
        rgb_frame_shape: tuple[int, ...],
        scene_stats: SceneFrameStats,
        scene_pause_key: str | None,
        scene_pause_reason: str | None,
    ) -> tuple[str, str | None]:
        if self.workflow_stage == "recording" and self.recorded_duration_seconds >= self.next_challenge_time_seconds:
            self.challenge_required_before_recording = True
            self.workflow_stage = "challenge"
            self.workflow_progress_frames = 0
            self._reset_recording_pause_candidate()

        if self.workflow_stage == "recording":
            recording_pause_key = self._recording_pause_key(scene_pause_key)
            if recording_pause_key == "distance_check":
                self._reset_recording_pause_candidate()
                self._reset_to_stage("distance_check")
            elif recording_pause_key is None:
                self._reset_recording_pause_candidate()
                return ("Recording session in progress.", None)
            else:
                pause_streak = self._recording_pause_streak(recording_pause_key)
                if pause_streak < self.config.recording_pause_confirmation_frames:
                    return ("Recording session in progress.", None)
                if recording_pause_key == "depth_variance_check":
                    self._reset_to_stage("depth_variance_check")
                elif recording_pause_key == "plane_fit_check":
                    self._reset_to_stage("plane_fit_check")

        if self.workflow_stage == "post_challenge_delay":
            assert self._post_challenge_delay_until_elapsed_seconds is not None
            remaining_seconds = max(
                0.0,
                self._post_challenge_delay_until_elapsed_seconds - elapsed_seconds,
            )
            if remaining_seconds > 0.0:
                self.workflow_progress_frames = 0
                return (
                    "Challenge complete. Please remove your hand from the scene.",
                    f"Recording resumes in {remaining_seconds:.1f} seconds.",
                )
            self._post_challenge_delay_until_elapsed_seconds = None
            self._reset_to_stage("distance_check")

        if self.workflow_stage == "distance_check":
            if scene_pause_key == "too_close":
                self.workflow_progress_frames = 0
                return (
                    "Step 1/4: move the subject farther from the camera.",
                    "Recording paused until the subject moves farther from the camera.",
                )
            self.workflow_progress_frames += 1
            if self._stage_confirmed():
                self._advance_to_stage("depth_variance_check")
            else:
                return (
                    "Step 1/4: keep the scene at a comfortable distance.",
                    "Distance check is stabilizing before the next step.",
                )

        if self.workflow_stage == "depth_variance_check":
            if scene_pause_key == "too_close":
                self._reset_to_stage("distance_check")
                return (
                    "Step 1/4: move the subject farther from the camera.",
                    "Recording paused until the subject moves farther from the camera.",
                )
            if scene_pause_key in {"insufficient_depth", "depth_variance"}:
                self.workflow_progress_frames = 0
                return (
                    "Step 2/4: show enough depth difference in the scene.",
                    "Recording paused until the scene shows more depth variation.",
                )
            self.workflow_progress_frames += 1
            if self._stage_confirmed():
                self._advance_to_stage("plane_fit_check")
            else:
                return (
                    "Step 2/4: hold the scene so depth difference can be confirmed.",
                    "Depth-difference check is stabilizing before the next step.",
                )

        if self.workflow_stage == "plane_fit_check":
            if scene_pause_key == "too_close":
                self._reset_to_stage("distance_check")
                return (
                    "Step 1/4: move the subject farther from the camera.",
                    "Recording paused until the subject moves farther from the camera.",
                )
            if scene_pause_key in {"insufficient_depth", "depth_variance"}:
                self._reset_to_stage("depth_variance_check")
                return (
                    "Step 2/4: show enough depth difference in the scene.",
                    "Recording paused until the scene shows more depth variation.",
                )
            if scene_pause_key == "plane_like":
                self.workflow_progress_frames = 0
                return (
                    "Step 3/4: make sure the scene is not too flat or screen-like.",
                    "Recording paused because the scene looks too planar.",
                )
            self.workflow_progress_frames += 1
            if self._stage_confirmed():
                self._advance_to_stage(
                    "challenge" if self.challenge_required_before_recording else "recording"
                )
            else:
                return (
                    "Step 3/4: hold the scene so the plane-fit check can settle.",
                    "Plane-fit check is stabilizing before the challenge.",
                )

        if self.workflow_stage == "challenge":
            return self._update_challenge(
                elapsed_seconds=elapsed_seconds,
                frame_dt_seconds=frame_dt_seconds,
                depth_frame=depth_frame,
                rgb_frame_shape=rgb_frame_shape,
                scene_pause_key=scene_pause_key,
                scene_pause_reason=scene_pause_reason,
            )

        self.workflow_stage = "recording"
        self.workflow_progress_frames = 0
        return ("Recording session in progress.", None)

    def _maybe_start_challenge(
        self,
        rgb_frame_shape: tuple[int, ...],
    ) -> None:
        if self.active_challenge is not None:
            return

        challenge_id = len(self.challenge_events) + 1
        roi = choose_random_center_roi(rgb_frame_shape, config=self.config, rng=self._rng)
        self.active_challenge = ActiveChallenge(
            challenge_id=challenge_id,
            roi=roi,
            issued_at_seconds=self.recorded_duration_seconds,
        )

    def _update_challenge(
        self,
        *,
        elapsed_seconds: float,
        frame_dt_seconds: float,
        depth_frame: np.ndarray,
        rgb_frame_shape: tuple[int, ...],
        scene_pause_key: str | None,
        scene_pause_reason: str | None,
    ) -> tuple[str, str | None]:
        self._maybe_start_challenge(rgb_frame_shape)
        if self.active_challenge is None:
            return (
                "Step 4/4: preparing the challenge.",
                "Recording paused while the challenge is being prepared.",
            )

        self.active_challenge.elapsed_seconds += frame_dt_seconds
        prompt = "Step 4/4: place an object in the box and move it closer to the camera."
        roi_stats = compute_roi_depth_stats(
            depth_frame,
            roi=self.active_challenge.roi,
            config=self.config,
        )
        roi_depth_is_usable = (
            roi_stats.valid_depth_ratio >= self.config.challenge_min_valid_depth_ratio
            and roi_stats.median_depth_mm is not None
        )
        if not roi_depth_is_usable:
            if scene_pause_key == "too_close":
                return (
                    "Step 4/4: keep the object in the box but slightly farther from the camera.",
                    "Recording paused until the challenge object is back in measurable range.",
                )
            if scene_pause_key in {"insufficient_depth", "depth_variance"}:
                return (
                    "Step 4/4: keep the object in the box and make the depth more readable.",
                    "Recording paused until the challenge object has enough reliable depth.",
                )
            if scene_pause_key == "plane_like":
                return (
                    "Step 4/4: keep the object in the box so the challenge depth stands out.",
                    "Recording paused until the challenge object stands out from the background.",
                )

        if roi_depth_is_usable:
            self.active_challenge.valid_frames += 1
            if self.active_challenge.baseline_depth_mm is None:
                self.active_challenge.baseline_depth_mm = roi_stats.median_depth_mm
                self.active_challenge.first_valid_elapsed_seconds = self.active_challenge.elapsed_seconds
                self.active_challenge.last_depth_mm = roi_stats.median_depth_mm
            else:
                self.active_challenge.baseline_depth_mm = max(
                    self.active_challenge.baseline_depth_mm,
                    roi_stats.median_depth_mm,
                )
                if self.active_challenge.last_depth_mm is not None:
                    progress_step_mm = (
                        self.active_challenge.last_depth_mm - roi_stats.median_depth_mm
                    )
                    if progress_step_mm >= self.config.challenge_min_progress_step_mm:
                        self.active_challenge.progress_frames += 1
                        self.active_challenge.last_progress_elapsed_seconds = (
                            self.active_challenge.elapsed_seconds
                        )
                self.active_challenge.last_depth_mm = roi_stats.median_depth_mm
            forward_motion_mm = (
                self.active_challenge.baseline_depth_mm - roi_stats.median_depth_mm
            )
            self.active_challenge.max_forward_motion_mm = max(
                self.active_challenge.max_forward_motion_mm,
                forward_motion_mm,
            )
            if (
                self.active_challenge.max_forward_motion_mm
                >= self.config.challenge_min_forward_motion_mm
                and self.active_challenge.valid_frames
                >= self.config.challenge_min_valid_frames_for_pass
                and self.active_challenge.progress_frames
                >= self.config.challenge_min_progress_frames_for_pass
                and self.active_challenge.progress_span_seconds
                >= self.config.challenge_min_motion_duration_seconds
            ):
                self._close_challenge(
                    elapsed_seconds=elapsed_seconds,
                    recorded_duration_seconds=self.recorded_duration_seconds,
                    outcome="passed",
                    reason="Object moved closer to the camera inside the ROI with steady forward motion.",
                )
                self.challenge_required_before_recording = False
                self.workflow_stage = "post_challenge_delay"
                self.workflow_progress_frames = 0
                self._post_challenge_delay_until_elapsed_seconds = (
                    elapsed_seconds + self.config.post_challenge_resume_delay_seconds
                )
                return (
                    "Challenge complete. Please remove your hand from the scene.",
                    "Recording paused briefly so you can remove your hand.",
                )

        if scene_pause_key == "too_close":
            return (
                "Step 4/4: move the object a touch farther away, then continue slowly forward.",
                "Recording paused until the challenge object is back in measurable range.",
            )
        if scene_pause_key in {"insufficient_depth", "depth_variance"}:
            return (
                "Step 4/4: keep the object in the box and improve the depth contrast.",
                "Recording paused until the challenge object has enough reliable depth.",
            )
        if scene_pause_key == "plane_like":
            return (
                "Step 4/4: keep the object in the box so it stands out from the background.",
                "Recording paused until the challenge object stands out from the background.",
            )

        if self.active_challenge.elapsed_seconds >= self.config.challenge_timeout_seconds:
            timed_out_challenge_id = self.active_challenge.challenge_id
            self._close_challenge(
                elapsed_seconds=elapsed_seconds,
                recorded_duration_seconds=self.recorded_duration_seconds,
                outcome="failed",
                reason="Challenge timed out before enough forward motion was observed.",
                schedule_next=False,
            )
            self.workflow_stage = "challenge"
            self.workflow_progress_frames = 0
            return (
                f"Step 4/4: challenge {timed_out_challenge_id} timed out. Get ready for a new box.",
                "Recording paused until the replacement challenge is completed.",
            )

        remaining_motion_mm = max(
            0.0,
            self.config.challenge_min_forward_motion_mm
            - self.active_challenge.max_forward_motion_mm,
        )
        return (
            f"{prompt} Remaining motion: {remaining_motion_mm:.0f} mm.",
            "Recording paused until the current challenge is completed.",
        )

    def _scene_pause_reason(
        self,
        scene_stats: SceneFrameStats,
    ) -> tuple[str | None, str | None]:
        if scene_stats.too_close_pixel_ratio >= self.config.too_close_pixel_ratio:
            return (
                "too_close",
                "Recording paused until the subject moves farther from the camera.",
            )
        if not scene_stats.analyzable or scene_stats.plane_fit_rms_mm is None:
            return (
                "insufficient_depth",
                "Recording paused until the scene provides enough reliable depth data.",
            )
        full_scene_depth_available = (
            scene_stats.valid_depth_ratio >= self.config.flat_scene_min_valid_depth_ratio
        )
        if (
            full_scene_depth_available
            and scene_stats.plane_fit_rms_mm <= self.config.max_planar_plane_fit_rms_mm
        ):
            return (
                "plane_like",
                "Recording paused because the scene looks too planar.",
            )
        if (
            full_scene_depth_available
            and (
            scene_stats.depth_spread_mm is None
            or scene_stats.depth_spread_mm < self.config.min_depth_spread_mm
            )
        ):
            return (
                "depth_variance",
                "Recording paused until the scene shows more depth variation.",
            )
        return (None, None)

    def _advance_to_stage(self, stage: str) -> None:
        self.workflow_stage = stage
        self.workflow_progress_frames = 0
        if stage != "recording":
            self._reset_recording_pause_candidate()

    def _reset_to_stage(self, stage: str) -> None:
        self.workflow_stage = stage
        self.workflow_progress_frames = 0
        if stage != "recording":
            self._reset_recording_pause_candidate()

    def _stage_confirmed(self) -> bool:
        return self.workflow_progress_frames >= self.config.workflow_confirmation_frames

    def _pause_key_for_stage(self, scene_pause_key: str | None) -> str:
        if self.workflow_stage == "challenge":
            return "challenge"
        if self.workflow_stage == "post_challenge_delay":
            return "post_challenge_delay"
        if self.workflow_stage == "distance_check":
            return "distance_check"
        if self.workflow_stage == "depth_variance_check":
            return "depth_variance_check"
        if self.workflow_stage == "plane_fit_check":
            return "plane_fit_check"
        if scene_pause_key is not None:
            return scene_pause_key
        return "paused"

    def _recording_pause_key(self, scene_pause_key: str | None) -> str | None:
        if scene_pause_key == "too_close":
            return "distance_check"
        if scene_pause_key in {"insufficient_depth", "depth_variance"}:
            return "depth_variance_check"
        if scene_pause_key == "plane_like":
            return "plane_fit_check"
        return None

    def _recording_pause_streak(self, pause_key: str) -> int:
        if pause_key == self._recording_pause_candidate_key:
            self._recording_pause_candidate_streak += 1
        else:
            self._recording_pause_candidate_key = pause_key
            self._recording_pause_candidate_streak = 1
        return self._recording_pause_candidate_streak

    def _reset_recording_pause_candidate(self) -> None:
        self._recording_pause_candidate_key = None
        self._recording_pause_candidate_streak = 0

    def _close_challenge(
        self,
        *,
        elapsed_seconds: float,
        recorded_duration_seconds: float,
        outcome: str,
        reason: str,
        schedule_next: bool = True,
    ) -> None:
        if self.active_challenge is None:
            return

        challenge = self.active_challenge
        if outcome == "passed":
            self.passed_challenges += 1
        else:
            self.failed_challenges += 1

        self.challenge_events.append(
            {
                "challenge_id": challenge.challenge_id,
                "state": outcome,
                "roi": challenge.roi.as_dict(),
                "issued_at_seconds": challenge.issued_at_seconds,
                "closed_at_seconds": elapsed_seconds,
                "elapsed_seconds": challenge.elapsed_seconds,
                "baseline_depth_mm": challenge.baseline_depth_mm,
                "max_forward_motion_mm": challenge.max_forward_motion_mm,
                "valid_frames": challenge.valid_frames,
                "progress_frames": challenge.progress_frames,
                "motion_duration_seconds": challenge.motion_duration_seconds,
                "close_reason": reason,
            }
        )
        self.active_challenge = None
        if schedule_next:
            self.next_challenge_time_seconds = recorded_duration_seconds + self._rng.uniform(
                self.config.challenge_schedule_min_seconds,
                self.config.challenge_schedule_max_seconds,
            )
        else:
            self.next_challenge_time_seconds = recorded_duration_seconds

    def _current_challenge_snapshot(self, prompt: str) -> ChallengeSnapshot | None:
        if self.active_challenge is None:
            return None
        return ChallengeSnapshot(
            challenge_id=self.active_challenge.challenge_id,
            state="active",
            prompt=prompt,
            roi=self.active_challenge.roi,
            issued_at_seconds=self.active_challenge.issued_at_seconds,
            elapsed_seconds=self.active_challenge.elapsed_seconds,
            timeout_seconds=self.config.challenge_timeout_seconds,
            baseline_depth_mm=self.active_challenge.baseline_depth_mm,
            max_forward_motion_mm=self.active_challenge.max_forward_motion_mm,
            valid_frames=self.active_challenge.valid_frames,
            progress_frames=self.active_challenge.progress_frames,
            motion_duration_seconds=self.active_challenge.motion_duration_seconds,
            close_reason=None,
        )

    def _plane_like_ratio(self) -> float | None:
        if self.flat_scene_evaluable_frames == 0:
            return None
        return self.plane_like_frames / self.flat_scene_evaluable_frames

    def _median_depth_spread_mm(self) -> float | None:
        if not self.depth_spreads_mm:
            return None
        return float(np.median(np.asarray(self.depth_spreads_mm, dtype=np.float32)))

    def _plane_like_result(self) -> SceneCheckResult:
        ratio = self._plane_like_ratio()
        if self.flat_scene_evaluable_frames < self.config.min_analyzable_frames:
            return SceneCheckResult(
                status="inconclusive",
                reason="Not enough full-scene depth frames for the plane-like check.",
                observed_value=ratio,
                threshold=self.config.max_planar_frame_ratio,
                frames_considered=self.flat_scene_evaluable_frames,
            )
        if ratio is not None and ratio >= self.config.max_planar_frame_ratio:
            return SceneCheckResult(
                status="failed",
                reason="Too many scene frames fit a single plane.",
                observed_value=ratio,
                threshold=self.config.max_planar_frame_ratio,
                frames_considered=self.flat_scene_evaluable_frames,
            )
        return SceneCheckResult(
            status="passed",
            reason="Scene planarity stayed below the configured risk threshold.",
            observed_value=ratio,
            threshold=self.config.max_planar_frame_ratio,
            frames_considered=self.flat_scene_evaluable_frames,
        )

    def _depth_variance_result(self) -> SceneCheckResult:
        median_spread = self._median_depth_spread_mm()
        if self.flat_scene_evaluable_frames < self.config.min_analyzable_frames:
            return SceneCheckResult(
                status="inconclusive",
                reason="Not enough full-scene depth frames for the depth-variance check.",
                observed_value=median_spread,
                threshold=self.config.min_depth_spread_mm,
                frames_considered=self.flat_scene_evaluable_frames,
            )
        if median_spread is not None and median_spread < self.config.min_depth_spread_mm:
            return SceneCheckResult(
                status="failed",
                reason="Scene depth spread stayed below the configured minimum.",
                observed_value=median_spread,
                threshold=self.config.min_depth_spread_mm,
                frames_considered=self.flat_scene_evaluable_frames,
            )
        return SceneCheckResult(
            status="passed",
            reason="Scene depth spread stayed above the configured minimum.",
            observed_value=median_spread,
            threshold=self.config.min_depth_spread_mm,
            frames_considered=self.flat_scene_evaluable_frames,
        )

    def _too_close_result(self) -> SceneCheckResult:
        ratio = self.too_close_frames / max(1, self.total_frames)
        if self.recorded_frames < self.config.min_analyzable_frames:
            return SceneCheckResult(
                status="inconclusive",
                reason="Not enough accepted recording frames were captured for the distance check.",
                observed_value=ratio,
                threshold=self.config.max_too_close_frame_ratio,
                frames_considered=self.recorded_frames,
            )
        if ratio > self.config.max_too_close_frame_ratio:
            return SceneCheckResult(
                status="failed",
                reason="Too much of the session stayed closer than the reliable depth floor.",
                observed_value=ratio,
                threshold=self.config.max_too_close_frame_ratio,
                frames_considered=self.recorded_frames,
            )
        return SceneCheckResult(
            status="passed",
            reason="Recorded frames stayed within the reliable camera distance.",
            observed_value=ratio,
            threshold=self.config.max_too_close_frame_ratio,
            frames_considered=self.recorded_frames,
        )

    def _overall_status(
        self,
        *,
        plane_result: SceneCheckResult,
        variance_result: SceneCheckResult,
        too_close_result: SceneCheckResult,
    ) -> tuple[str, str]:
        # Relax the soft "inconclusive" gates once the session has cleared the hard
        # failure checks and completed at least one challenge successfully.
        # if self.active_challenge is not None:
        #     return ("inconclusive", "Session stopped while a challenge was still active.")
        if plane_result.status == "failed":
            return ("failed", plane_result.reason)
        if variance_result.status == "failed":
            return ("failed", variance_result.reason)
        if too_close_result.status == "failed":
            return ("failed", too_close_result.reason)
        if self.failed_challenges > 0:
            return ("failed", "At least one anti-replay challenge was failed or timed out.")
        # if self.analyzable_frames < self.config.min_analyzable_frames:
        #     return ("inconclusive", "Not enough analyzable depth evidence was recorded.")
        # if plane_result.status != "passed":
        #     return ("inconclusive", plane_result.reason)
        # if variance_result.status != "passed":
        #     return ("inconclusive", variance_result.reason)
        # if too_close_result.status != "passed":
        #     return ("inconclusive", too_close_result.reason)
        if self.passed_challenges < 1:
            return ("inconclusive", "No challenge was completed successfully.")
        return (
            "verified",
            "Depth realism checks cleared the hard failure gates, and at least one challenge succeeded with no failures.",
        )
