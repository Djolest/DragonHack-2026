from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class ChallengeConfig:
    roi_width_fraction: float
    roi_height_fraction: float
    min_depth_mm: int
    max_depth_mm: int
    min_valid_depth_ratio: float
    poor_depth_ratio: float
    min_valid_frames_for_pass: int
    min_valid_frames_for_summary: int
    min_forward_motion_mm: float
    plane_fit_min_points: int
    max_plane_fit_points: int
    max_planar_plane_fit_rms_mm: float
    max_planar_depth_std_mm: float
    elevated_planar_frame_ratio: float
    min_valid_frames_for_risk: int
    poor_depth_frame_ratio_for_inconclusive: float
    history_size: int
    recent_series_length: int

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
class DepthFrameStats:
    frame_index: int
    roi: RoiBox
    valid_depth_ratio: float
    valid_pixel_count: int
    total_pixel_count: int
    median_depth_mm: float | None
    depth_std_mm: float | None
    depth_delta_mm: float | None
    baseline_depth_mm: float | None
    plane_fit_rms_mm: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "roi": self.roi.as_dict(),
            "valid_depth_ratio": self.valid_depth_ratio,
            "valid_pixel_count": self.valid_pixel_count,
            "total_pixel_count": self.total_pixel_count,
            "median_depth_mm": self.median_depth_mm,
            "depth_std_mm": self.depth_std_mm,
            "depth_delta_mm": self.depth_delta_mm,
            "baseline_depth_mm": self.baseline_depth_mm,
            "plane_fit_rms_mm": self.plane_fit_rms_mm,
        }


@dataclass(frozen=True, slots=True)
class ChallengeFrameState:
    stats: DepthFrameStats
    live_status: str
    status_reason: str
    replay_risk: str
    replay_risk_reason: str
    max_forward_motion_mm: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "stats": self.stats.to_dict(),
            "live_status": self.live_status,
            "status_reason": self.status_reason,
            "replay_risk": self.replay_risk,
            "replay_risk_reason": self.replay_risk_reason,
            "max_forward_motion_mm": self.max_forward_motion_mm,
        }


def load_challenge_config(path: Path) -> ChallengeConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ChallengeConfig(
        roi_width_fraction=float(raw["roi"]["width_fraction"]),
        roi_height_fraction=float(raw["roi"]["height_fraction"]),
        min_depth_mm=int(raw["depth"]["min_depth_mm"]),
        max_depth_mm=int(raw["depth"]["max_depth_mm"]),
        min_valid_depth_ratio=float(raw["depth"]["min_valid_depth_ratio"]),
        poor_depth_ratio=float(raw["depth"]["poor_depth_ratio"]),
        min_valid_frames_for_pass=int(raw["motion"]["min_valid_frames_for_pass"]),
        min_valid_frames_for_summary=int(raw["motion"]["min_valid_frames_for_summary"]),
        min_forward_motion_mm=float(raw["motion"]["min_forward_motion_mm"]),
        plane_fit_min_points=int(raw["planarity"]["plane_fit_min_points"]),
        max_plane_fit_points=int(raw["planarity"]["max_plane_fit_points"]),
        max_planar_plane_fit_rms_mm=float(raw["planarity"]["max_plane_fit_rms_mm"]),
        max_planar_depth_std_mm=float(raw["planarity"]["max_depth_std_mm"]),
        elevated_planar_frame_ratio=float(raw["planarity"]["elevated_frame_ratio"]),
        min_valid_frames_for_risk=int(raw["planarity"]["min_valid_frames_for_risk"]),
        poor_depth_frame_ratio_for_inconclusive=float(
            raw["quality"]["poor_depth_frame_ratio_for_inconclusive"]
        ),
        history_size=int(raw["quality"]["history_size"]),
        recent_series_length=int(raw["quality"]["recent_series_length"]),
    )


def compute_center_roi(
    frame_shape: tuple[int, ...],
    roi_width_fraction: float,
    roi_height_fraction: float,
) -> RoiBox:
    frame_height, frame_width = frame_shape[:2]
    roi_width = max(40, int(frame_width * roi_width_fraction))
    roi_height = max(40, int(frame_height * roi_height_fraction))
    x0 = (frame_width - roi_width) // 2
    y0 = (frame_height - roi_height) // 2
    return RoiBox(x0=x0, y0=y0, x1=x0 + roi_width, y1=y0 + roi_height)


def fit_plane_rms_mm(
    depth_roi: np.ndarray,
    valid_mask: np.ndarray,
    *,
    min_points: int,
    max_points: int,
) -> float | None:
    ys, xs = np.nonzero(valid_mask)
    if xs.size < min_points:
        return None

    zs = depth_roi[ys, xs].astype(np.float64)
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


def compute_depth_stats(
    depth_frame: np.ndarray,
    roi: RoiBox,
    config: ChallengeConfig,
    frame_index: int,
    baseline_depth_mm: float | None,
) -> DepthFrameStats:
    depth_roi = depth_frame[roi.y0 : roi.y1, roi.x0 : roi.x1]
    total_pixel_count = int(depth_roi.size)
    if total_pixel_count == 0:
        return DepthFrameStats(
            frame_index=frame_index,
            roi=roi,
            valid_depth_ratio=0.0,
            valid_pixel_count=0,
            total_pixel_count=0,
            median_depth_mm=None,
            depth_std_mm=None,
            depth_delta_mm=None,
            baseline_depth_mm=baseline_depth_mm,
            plane_fit_rms_mm=None,
        )

    valid_mask = (depth_roi >= config.min_depth_mm) & (depth_roi <= config.max_depth_mm)
    valid_pixel_count = int(np.count_nonzero(valid_mask))
    valid_depth_ratio = valid_pixel_count / total_pixel_count

    if valid_pixel_count == 0:
        return DepthFrameStats(
            frame_index=frame_index,
            roi=roi,
            valid_depth_ratio=valid_depth_ratio,
            valid_pixel_count=valid_pixel_count,
            total_pixel_count=total_pixel_count,
            median_depth_mm=None,
            depth_std_mm=None,
            depth_delta_mm=None,
            baseline_depth_mm=baseline_depth_mm,
            plane_fit_rms_mm=None,
        )

    valid_depth_values = depth_roi[valid_mask].astype(np.float32)
    median_depth_mm = float(np.median(valid_depth_values))
    depth_std_mm = float(np.std(valid_depth_values))
    next_baseline_mm = (
        median_depth_mm if baseline_depth_mm is None else max(baseline_depth_mm, median_depth_mm)
    )
    depth_delta_mm = next_baseline_mm - median_depth_mm

    return DepthFrameStats(
        frame_index=frame_index,
        roi=roi,
        valid_depth_ratio=valid_depth_ratio,
        valid_pixel_count=valid_pixel_count,
        total_pixel_count=total_pixel_count,
        median_depth_mm=median_depth_mm,
        depth_std_mm=depth_std_mm,
        depth_delta_mm=depth_delta_mm,
        baseline_depth_mm=next_baseline_mm,
        plane_fit_rms_mm=fit_plane_rms_mm(
            depth_roi,
            valid_mask,
            min_points=config.plane_fit_min_points,
            max_points=config.max_plane_fit_points,
        ),
    )


def is_planar_low_variance_frame(stats: DepthFrameStats, config: ChallengeConfig) -> bool:
    if stats.plane_fit_rms_mm is None or stats.depth_std_mm is None:
        return False
    return (
        stats.plane_fit_rms_mm <= config.max_planar_plane_fit_rms_mm
        and stats.depth_std_mm <= config.max_planar_depth_std_mm
    )


class DepthChallengeTracker:
    def __init__(self, config: ChallengeConfig) -> None:
        self.config = config
        self.frame_history: deque[DepthFrameStats] = deque(maxlen=config.history_size)
        self.depth_delta_history_mm: deque[float] = deque(maxlen=config.recent_series_length)
        self.frame_index = 0
        self.total_frames = 0
        self.valid_frames = 0
        self.poor_depth_frames = 0
        self.planar_low_variance_frames = 0
        self.baseline_depth_mm: float | None = None
        self.max_forward_motion_mm = 0.0
        self.passed = False
        self.pass_frame_index: int | None = None

    def update(self, depth_frame: np.ndarray, roi: RoiBox) -> ChallengeFrameState:
        self.frame_index += 1
        self.total_frames += 1

        stats = compute_depth_stats(
            depth_frame=depth_frame,
            roi=roi,
            config=self.config,
            frame_index=self.frame_index,
            baseline_depth_mm=self.baseline_depth_mm,
        )
        self.baseline_depth_mm = stats.baseline_depth_mm
        self.frame_history.append(stats)

        if stats.valid_depth_ratio < self.config.poor_depth_ratio or stats.median_depth_mm is None:
            self.poor_depth_frames += 1

        if (
            stats.valid_depth_ratio >= self.config.min_valid_depth_ratio
            and stats.median_depth_mm is not None
            and stats.depth_delta_mm is not None
        ):
            self.valid_frames += 1
            self.max_forward_motion_mm = max(self.max_forward_motion_mm, stats.depth_delta_mm)
            self.depth_delta_history_mm.append(stats.depth_delta_mm)

            if is_planar_low_variance_frame(stats, self.config):
                self.planar_low_variance_frames += 1

        replay_risk, replay_risk_reason = self._replay_risk_state()
        live_status, status_reason = self._live_status(stats)
        return ChallengeFrameState(
            stats=stats,
            live_status=live_status,
            status_reason=status_reason,
            replay_risk=replay_risk,
            replay_risk_reason=replay_risk_reason,
            max_forward_motion_mm=self.max_forward_motion_mm,
        )

    def _live_status(self, stats: DepthFrameStats) -> tuple[str, str]:
        if self.passed:
            return "PASSED", "Forward Z-motion threshold satisfied."

        if stats.valid_depth_ratio < self.config.poor_depth_ratio or stats.median_depth_mm is None:
            return "INCONCLUSIVE", "Depth data in the ROI is too sparse."

        if stats.valid_depth_ratio < self.config.min_valid_depth_ratio:
            return "PENDING", "Keep your hand inside the center box."

        if (
            stats.depth_delta_mm is not None
            and stats.depth_delta_mm >= self.config.min_forward_motion_mm
            and self.valid_frames >= self.config.min_valid_frames_for_pass
        ):
            if not self.passed:
                self.passed = True
                self.pass_frame_index = stats.frame_index
            return "PASSED", "Forward Z-motion threshold satisfied."

        remaining_motion_mm = max(0.0, self.config.min_forward_motion_mm - self.max_forward_motion_mm)
        return "PENDING", f"Move your hand {remaining_motion_mm:.0f} mm closer to the camera."

    def _replay_risk_state(self) -> tuple[str, str]:
        if self.valid_frames < self.config.min_valid_frames_for_risk:
            return "UNKNOWN", "Collecting more valid depth frames."

        planar_ratio = self.planar_low_variance_frames / max(1, self.valid_frames)
        if planar_ratio >= self.config.elevated_planar_frame_ratio:
            return "ELEVATED", "ROI stayed highly planar and low-variance across valid frames."

        return "NORMAL", "ROI shows enough depth variation for this heuristic."

    def final_status(self) -> tuple[str, str]:
        if self.passed:
            return "passed", "Forward Z-motion exceeded the configured threshold."

        if self.total_frames == 0:
            return "inconclusive", "No frames were processed."

        poor_depth_fraction = self.poor_depth_frames / self.total_frames
        if (
            self.valid_frames < self.config.min_valid_frames_for_summary
            or poor_depth_fraction >= self.config.poor_depth_frame_ratio_for_inconclusive
        ):
            return "inconclusive", "Depth data quality was too poor for a reliable decision."

        return "not_passed", "Valid depth was observed, but forward motion did not exceed the threshold."

    def build_summary(
        self,
        *,
        device_info: dict[str, Any],
        last_state: ChallengeFrameState | None,
    ) -> dict[str, Any]:
        status, status_reason = self.final_status()
        replay_risk, replay_risk_reason = self._replay_risk_state()
        recent_depth_delta_mm = list(self.depth_delta_history_mm)

        return {
            "challenge_name": "Place your hand in the center box and move it toward the camera",
            "challenge_status": status,
            "status_reason": status_reason,
            "replay_risk": replay_risk.lower(),
            "replay_risk_reason": replay_risk_reason,
            "frames_processed": self.total_frames,
            "valid_frames": self.valid_frames,
            "poor_depth_frames": self.poor_depth_frames,
            "planar_low_variance_frames": self.planar_low_variance_frames,
            "max_forward_motion_mm": self.max_forward_motion_mm,
            "pass_frame_index": self.pass_frame_index,
            "thresholds": self.config.to_dict(),
            "device_info": device_info,
            "latest_frame": last_state.to_dict() if last_state is not None else None,
            "recent_depth_delta_mm": recent_depth_delta_mm,
        }


def write_summary_json(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
