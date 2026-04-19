from __future__ import annotations

import argparse
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .config import DEFAULT_VERIFICATION_CONFIG_PATH
from .depth_challenge import LiveSessionState, RoiBox, load_verification_config
from .oak4_engine import DeviceSummary, Oak4RuntimeConfig, SyncedFrame, colorize_depth
from .session_runtime import CaptureSessionManager
from .storage import LocalStorage

LOGGER = logging.getLogger("oakproof.oak4_rgbd_viewer")

RGB_WINDOW_NAME = "OAK4 RGB"
DEPTH_WINDOW_NAME = "OAK4 Aligned Depth"


@dataclass(frozen=True, slots=True)
class PreviewSnapshot:
    frame: SyncedFrame
    live_state: LiveSessionState
    device_summary: DeviceSummary


class PreviewFrameBuffer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: PreviewSnapshot | None = None

    def update(
        self,
        frame: SyncedFrame,
        live_state: LiveSessionState,
        device_summary: DeviceSummary,
    ) -> None:
        snapshot = PreviewSnapshot(
            frame=SyncedFrame(
                rgb_frame=frame.rgb_frame.copy(),
                depth_frame=frame.depth_frame.copy(),
                timestamp_seconds=frame.timestamp_seconds,
            ),
            live_state=live_state,
            device_summary=device_summary,
        )
        with self._lock:
            self._latest = snapshot

    def latest(self) -> PreviewSnapshot | None:
        with self._lock:
            return self._latest


class OpenCvPreviewObserver:
    def __init__(self, frame_buffer: PreviewFrameBuffer) -> None:
        self.frame_buffer = frame_buffer

    def __call__(
        self,
        frame: SyncedFrame,
        live_state: LiveSessionState,
        device_summary: DeviceSummary,
    ) -> bool:
        self.frame_buffer.update(frame, live_state, device_summary)
        return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OAK4 RGB-D realness capture viewer")
    parser.add_argument("--config", type=Path, default=DEFAULT_VERIFICATION_CONFIG_PATH)
    parser.add_argument("--storage-root", type=Path, default=Path("data"))
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--asset-id", default="viewer-debug")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def configure_logging(level_name: str) -> None:
    log_level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def create_display_windows() -> None:
    cv2.namedWindow(RGB_WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.namedWindow(DEPTH_WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(RGB_WINDOW_NAME, 1280, 720)
    cv2.resizeWindow(DEPTH_WINDOW_NAME, 1280, 720)


def placeholder_frame(
    *,
    width: int,
    height: int,
    title: str,
    subtitle: str,
) -> np.ndarray:
    frame = np.full((height, width, 3), 28, dtype=np.uint8)
    cv2.putText(
        frame,
        title,
        (40, max(80, height // 2 - 20)),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (235, 235, 235),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        subtitle,
        (40, max(120, height // 2 + 24)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (180, 180, 180),
        2,
        cv2.LINE_AA,
    )
    return frame


def draw_roi(frame: np.ndarray, roi: RoiBox, color: tuple[int, int, int], label: str) -> np.ndarray:
    annotated = frame.copy()
    cv2.rectangle(annotated, (roi.x0, roi.y0), (roi.x1, roi.y1), color, 2)
    cv2.putText(
        annotated,
        label,
        (roi.x0, max(24, roi.y0 - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        color,
        2,
        cv2.LINE_AA,
    )
    return annotated


def live_panel_color(live_state: LiveSessionState) -> tuple[int, int, int]:
    if live_state.recording_state == "paused":
        return (48, 48, 255)
    if live_state.current_challenge is not None:
        return (0, 191, 255)
    return (76, 210, 106)


def build_status_lines(live_state: LiveSessionState, device_summary: DeviceSummary) -> list[str]:
    scene_stats = live_state.scene_stats
    challenge = live_state.current_challenge
    plane_ratio = "n/a" if live_state.plane_like_ratio is None else f"{live_state.plane_like_ratio:.2f}"
    current_spread = (
        "n/a" if scene_stats.depth_spread_mm is None else f"{scene_stats.depth_spread_mm:.1f} mm"
    )
    current_plane_fit = (
        "n/a" if scene_stats.plane_fit_rms_mm is None else f"{scene_stats.plane_fit_rms_mm:.1f} mm"
    )
    spread = (
        "n/a"
        if live_state.median_depth_spread_mm is None
        else f"{live_state.median_depth_spread_mm:.1f} mm"
    )
    lines = [
        f"Workflow stage: {live_state.workflow_stage}",
        f"Stage progress: {live_state.workflow_progress_frames}",
        f"Recording: {live_state.recording_state.upper()}",
        f"Pause reason: {live_state.recording_pause_reason or 'none'}",
        f"Prompt: {live_state.prompt}",
        f"Warning: {live_state.warning or 'none'}",
        (
            f"Session: {live_state.elapsed_seconds:.1f}s | "
            f"Recorded: {live_state.recorded_duration_seconds:.1f}s"
        ),
        (
            f"Frames processed/recorded: {live_state.frame_index}/"
            f"{live_state.recorded_frames}"
        ),
        f"Analyzable frames: {live_state.analyzable_frames}",
        f"Valid depth ratio: {scene_stats.valid_depth_ratio:.2f}",
        f"Too-close pixel ratio: {scene_stats.too_close_pixel_ratio:.2f}",
        f"Current depth spread: {current_spread}",
        f"Current plane-fit RMS: {current_plane_fit}",
        f"Plane-like ratio: {plane_ratio}",
        f"Median depth spread: {spread}",
        (
            f"Challenges issued/passed/failed: {live_state.challenges_issued}/"
            f"{live_state.challenges_passed}/{live_state.challenges_failed}"
        ),
    ]
    if challenge is not None:
        lines.append(
            f"Challenge {challenge.challenge_id}: {challenge.max_forward_motion_mm:.1f} mm | "
            f"progress {challenge.progress_frames} frames | motion {challenge.motion_duration_seconds:.1f}s"
        )
        lines.append(f"Challenge timer: {challenge.elapsed_seconds:.1f}s / {challenge.timeout_seconds:.1f}s")
    else:
        eta = (
            "n/a"
            if live_state.next_challenge_eta_seconds is None
            else f"{live_state.next_challenge_eta_seconds:.1f}s"
        )
        lines.append(f"Next challenge ETA: {eta}")
    lines.append(f"Device: {device_summary.product_name or device_summary.name}")
    return lines


def draw_status_panel(
    frame: np.ndarray,
    *,
    live_state: LiveSessionState,
    device_summary: DeviceSummary,
) -> np.ndarray:
    color = live_panel_color(live_state)
    overlay = frame.copy()
    lines = build_status_lines(live_state, device_summary)
    panel_width = min(frame.shape[1] - 20, 760)
    panel_height = 34 + (len(lines) * 26)
    cv2.rectangle(overlay, (10, 10), (10 + panel_width, 10 + panel_height), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.42, frame, 0.58, 0.0, frame)
    cv2.rectangle(frame, (10, 10), (10 + panel_width, 10 + panel_height), color, 2)

    for index, line in enumerate(lines):
        y = 36 + (index * 26)
        text_color = color if index in {0, 1, 2, 3, 4, 5} else (240, 240, 240)
        cv2.putText(
            frame,
            line,
            (24, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            text_color,
            2,
            cv2.LINE_AA,
        )
    return frame


def annotate_rgb_frame(
    frame: np.ndarray,
    live_state: LiveSessionState,
    device_summary: DeviceSummary,
) -> np.ndarray:
    annotated = frame.copy()
    challenge = live_state.current_challenge
    if challenge is not None and challenge.roi is not None:
        annotated = draw_roi(annotated, challenge.roi, live_panel_color(live_state), "CHALLENGE ROI")
    return draw_status_panel(annotated, live_state=live_state, device_summary=device_summary)


def annotate_depth_frame(depth_color: np.ndarray, live_state: LiveSessionState) -> np.ndarray:
    annotated = depth_color.copy()
    challenge = live_state.current_challenge
    if challenge is not None and challenge.roi is not None:
        annotated = draw_roi(annotated, challenge.roi, live_panel_color(live_state), "CHALLENGE ROI")
    return annotated


def display_snapshot(
    snapshot: PreviewSnapshot,
    *,
    preview_min_depth_mm: float,
    preview_max_depth_mm: float,
) -> None:
    rgb_preview = annotate_rgb_frame(
        snapshot.frame.rgb_frame,
        snapshot.live_state,
        snapshot.device_summary,
    )
    depth_preview = annotate_depth_frame(
        colorize_depth(
            snapshot.frame.depth_frame,
            min_depth_mm=preview_min_depth_mm,
            max_depth_mm=preview_max_depth_mm,
        ),
        snapshot.live_state,
    )
    cv2.imshow(RGB_WINDOW_NAME, rgb_preview)
    cv2.imshow(DEPTH_WINDOW_NAME, depth_preview)


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    create_display_windows()
    frame_buffer = PreviewFrameBuffer()

    runtime_config = Oak4RuntimeConfig()
    verification_config = load_verification_config(args.config.resolve())
    preview_min_depth_mm = max(100.0, float(verification_config.scene_min_depth_mm))
    preview_max_depth_mm = max(
        4000.0,
        float(verification_config.scene_max_depth_mm) * 1.75,
    )
    manager = CaptureSessionManager(
        storage=LocalStorage(args.storage_root.resolve()),
        verification_config=verification_config,
        public_base_url="http://127.0.0.1:8100",
        runtime_config=runtime_config,
        oak_device_id=None,
        observer_factory=lambda: OpenCvPreviewObserver(frame_buffer),
    )

    try:
        session = manager.start_session(
            asset_id=args.asset_id,
            operator_id="viewer",
            notes="local viewer session",
            tags=["viewer"],
            simulate=args.simulate,
        )
        LOGGER.info("Session %s started", session.session_id)

        empty_rgb = placeholder_frame(
            width=runtime_config.rgb_size[0],
            height=runtime_config.rgb_size[1],
            title="Waiting For RGB Frames",
            subtitle="The viewer is connecting to the OAK4 pipeline.",
        )
        empty_depth = placeholder_frame(
            width=runtime_config.rgb_size[0],
            height=runtime_config.rgb_size[1],
            title="Waiting For Depth Frames",
            subtitle="Press q to stop once frames appear.",
        )

        latest_snapshot: PreviewSnapshot | None = None
        while session.is_active():
            next_snapshot = frame_buffer.latest()
            if next_snapshot is not None:
                latest_snapshot = next_snapshot
                display_snapshot(
                    latest_snapshot,
                    preview_min_depth_mm=preview_min_depth_mm,
                    preview_max_depth_mm=preview_max_depth_mm,
                )
            else:
                cv2.imshow(RGB_WINDOW_NAME, empty_rgb)
                cv2.imshow(DEPTH_WINDOW_NAME, empty_depth)

            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                LOGGER.info("Exit requested by user")
                session.stop()
                break

            time.sleep(0.01)

        if latest_snapshot is None:
            cv2.imshow(RGB_WINDOW_NAME, empty_rgb)
            cv2.imshow(DEPTH_WINDOW_NAME, empty_depth)
            cv2.waitKey(1)

        snapshot = session.snapshot()
        LOGGER.info("Session finished with state=%s", snapshot["state"])
        if snapshot["proof_summary"] is not None:
            LOGGER.info(
                "Proof summary:\n%s",
                json.dumps(snapshot["proof_summary"], indent=2, sort_keys=True),
            )
        return 0
    except KeyboardInterrupt:
        LOGGER.info("Interrupted by user")
        return 0
    except Exception as exc:
        LOGGER.error("%s", exc)
        return 1
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    raise SystemExit(main())
