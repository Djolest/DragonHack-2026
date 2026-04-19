from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Iterator

import cv2
import numpy as np

from .depth_challenge import LiveSessionState, RoiBox, VerificationConfig
from .oak4_engine import DeviceSummary, Oak4RuntimeConfig, SyncedFrame, colorize_depth


JPEG_MEDIA_TYPE = "image/jpeg"
MJPEG_BOUNDARY = "oakproofframe"
MJPEG_MEDIA_TYPE = f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}"
DEFAULT_RGB_PREVIEW_WIDTH = 960
DEFAULT_RGB_PREVIEW_QUALITY = 72
DEFAULT_DEPTH_PREVIEW_WIDTH = 360
DEFAULT_DEPTH_PREVIEW_QUALITY = 55


@dataclass(frozen=True, slots=True)
class PreviewSnapshot:
    frame: SyncedFrame
    live_state: LiveSessionState
    device_summary: DeviceSummary


@dataclass(slots=True)
class CachedPreviewFrame:
    snapshot: PreviewSnapshot
    rgb_frame: np.ndarray
    rgb_jpeg: bytes
    depth_frame: np.ndarray
    depth_jpeg: bytes
    version: int


class PreviewFrameBuffer:
    def __init__(
        self,
        *,
        preview_min_depth_mm: float = 100.0,
        preview_max_depth_mm: float = 4000.0,
        default_rgb_width: int | None = DEFAULT_RGB_PREVIEW_WIDTH,
        default_rgb_height: int | None = None,
        default_rgb_quality: int = DEFAULT_RGB_PREVIEW_QUALITY,
        default_depth_width: int | None = DEFAULT_DEPTH_PREVIEW_WIDTH,
        default_depth_height: int | None = None,
        default_depth_quality: int = DEFAULT_DEPTH_PREVIEW_QUALITY,
    ) -> None:
        self.preview_min_depth_mm = preview_min_depth_mm
        self.preview_max_depth_mm = preview_max_depth_mm
        self.default_rgb_width = default_rgb_width
        self.default_rgb_height = default_rgb_height
        self.default_rgb_quality = default_rgb_quality
        self.default_depth_width = default_depth_width
        self.default_depth_height = default_depth_height
        self.default_depth_quality = default_depth_quality
        self._condition = threading.Condition()
        self._latest: CachedPreviewFrame | None = None
        self._version = 0

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
        rgb_frame = render_rgb_preview(snapshot)
        depth_frame = render_depth_preview(
            snapshot,
            preview_min_depth_mm=self.preview_min_depth_mm,
            preview_max_depth_mm=self.preview_max_depth_mm,
        )
        default_rgb_frame = resize_preview_frame(
            rgb_frame,
            width=self.default_rgb_width,
            height=self.default_rgb_height,
        )
        default_depth_frame = resize_preview_frame(
            depth_frame,
            width=self.default_depth_width,
            height=self.default_depth_height,
        )
        rgb_jpeg = encode_jpeg(default_rgb_frame, quality=self.default_rgb_quality)
        depth_jpeg = encode_jpeg(default_depth_frame, quality=self.default_depth_quality)

        with self._condition:
            self._version += 1
            self._latest = CachedPreviewFrame(
                snapshot=snapshot,
                rgb_frame=rgb_frame,
                rgb_jpeg=rgb_jpeg,
                depth_frame=depth_frame,
                depth_jpeg=depth_jpeg,
                version=self._version,
            )
            self._condition.notify_all()

    def latest(self) -> PreviewSnapshot | None:
        with self._condition:
            latest = self._latest
            return latest.snapshot if latest is not None else None

    def latest_cached(self) -> CachedPreviewFrame | None:
        with self._condition:
            return self._latest

    def wait_for_newer(
        self,
        last_version: int,
        *,
        timeout_seconds: float | None = None,
    ) -> CachedPreviewFrame | None:
        deadline = (
            None if timeout_seconds is None else time.monotonic() + max(0.0, timeout_seconds)
        )
        with self._condition:
            while True:
                latest = self._latest
                if latest is not None and latest.version > last_version:
                    return latest
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0.0:
                        return None
                    self._condition.wait(timeout=remaining)
                else:
                    self._condition.wait()


class FrameBufferingPreviewObserver:
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
        lines.append(
            f"Challenge timer: {challenge.elapsed_seconds:.1f}s / {challenge.timeout_seconds:.1f}s"
        )
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


def render_rgb_preview(snapshot: PreviewSnapshot) -> np.ndarray:
    return annotate_rgb_frame(
        snapshot.frame.rgb_frame,
        snapshot.live_state,
        snapshot.device_summary,
    )


def render_depth_preview(
    snapshot: PreviewSnapshot,
    *,
    preview_min_depth_mm: float,
    preview_max_depth_mm: float,
) -> np.ndarray:
    return annotate_depth_frame(
        colorize_depth(
            snapshot.frame.depth_frame,
            min_depth_mm=preview_min_depth_mm,
            max_depth_mm=preview_max_depth_mm,
        ),
        snapshot.live_state,
    )


def encode_jpeg(frame: np.ndarray, *, quality: int = 90) -> bytes:
    success, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not success:
        raise RuntimeError("Failed to encode preview frame as JPEG.")
    return encoded.tobytes()


def encode_mjpeg_chunk(jpeg_bytes: bytes, *, boundary: str = MJPEG_BOUNDARY) -> bytes:
    header = (
        f"--{boundary}\r\n"
        f"Content-Type: {JPEG_MEDIA_TYPE}\r\n"
        f"Content-Length: {len(jpeg_bytes)}\r\n\r\n"
    ).encode("ascii")
    return header + jpeg_bytes + b"\r\n"


def resize_preview_frame(
    frame: np.ndarray,
    *,
    width: int | None = None,
    height: int | None = None,
) -> np.ndarray:
    original_height, original_width = frame.shape[:2]
    if original_width <= 0 or original_height <= 0:
        return frame

    width_scale = (
        float(width) / float(original_width)
        if width is not None and 0 < width < original_width
        else 1.0
    )
    height_scale = (
        float(height) / float(original_height)
        if height is not None and 0 < height < original_height
        else 1.0
    )
    scale = min(width_scale, height_scale)
    if scale >= 1.0:
        return frame

    resized_width = max(1, int(round(original_width * scale)))
    resized_height = max(1, int(round(original_height * scale)))
    return cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_AREA)


def uses_default_preview_request(
    *,
    width: int | None,
    height: int | None,
    quality: int,
    default_width: int | None,
    default_height: int | None,
    default_quality: int,
) -> bool:
    return (
        width == default_width
        and height == default_height
        and quality == default_quality
    )


class SessionPreviewRegistry:
    def __init__(
        self,
        *,
        runtime_config: Oak4RuntimeConfig,
        verification_config: VerificationConfig,
    ) -> None:
        self.runtime_config = runtime_config
        self.preview_min_depth_mm = max(100.0, float(verification_config.scene_min_depth_mm))
        self.preview_max_depth_mm = max(
            4000.0,
            float(verification_config.scene_max_depth_mm) * 1.75,
        )
        self.default_rgb_width = DEFAULT_RGB_PREVIEW_WIDTH
        self.default_rgb_height: int | None = None
        self.default_rgb_quality = DEFAULT_RGB_PREVIEW_QUALITY
        self.default_depth_width = DEFAULT_DEPTH_PREVIEW_WIDTH
        self.default_depth_height: int | None = None
        self.default_depth_quality = DEFAULT_DEPTH_PREVIEW_QUALITY
        self._lock = threading.Lock()
        self._buffers: dict[str, PreviewFrameBuffer] = {}

    def observer_for_session(self, session_id: str) -> FrameBufferingPreviewObserver:
        return FrameBufferingPreviewObserver(self._buffer_for_session(session_id))

    def latest_rgb_jpeg(
        self,
        session_id: str,
        *,
        width: int | None = DEFAULT_RGB_PREVIEW_WIDTH,
        height: int | None = None,
        quality: int = DEFAULT_RGB_PREVIEW_QUALITY,
    ) -> bytes:
        cached = self.latest_cached_preview(session_id)
        if cached is None:
            return self._placeholder_jpeg(
                title="Waiting For RGB Preview",
                subtitle=f"Session {session_id} has not produced a frame yet.",
                width=width,
                height=height,
                quality=quality,
            )
        if uses_default_preview_request(
            width=width,
            height=height,
            quality=quality,
            default_width=self.default_rgb_width,
            default_height=self.default_rgb_height,
            default_quality=self.default_rgb_quality,
        ):
            return cached.rgb_jpeg
        frame = resize_preview_frame(cached.rgb_frame, width=width, height=height)
        return encode_jpeg(frame, quality=quality)

    def iter_rgb_mjpeg(
        self,
        session_id: str,
        *,
        width: int | None = DEFAULT_RGB_PREVIEW_WIDTH,
        height: int | None = None,
        quality: int = DEFAULT_RGB_PREVIEW_QUALITY,
        fps: float = 12.0,
    ) -> Iterator[bytes]:
        frame_interval_seconds = 1.0 / max(1.0, fps)
        placeholder_bytes: bytes | None = None
        last_version = -1
        last_emit_seconds = 0.0

        while True:
            cached = self.wait_for_newer_preview(
                session_id,
                last_version,
                timeout_seconds=frame_interval_seconds,
            )
            if cached is None:
                if placeholder_bytes is None:
                    placeholder_bytes = self._placeholder_jpeg(
                        title="Waiting For RGB Preview",
                        subtitle=f"Session {session_id} has not produced a frame yet.",
                        width=width,
                        height=height,
                        quality=quality,
                    )
                if last_version < 0:
                    yield encode_mjpeg_chunk(placeholder_bytes)
                    last_emit_seconds = time.monotonic()
                continue

            if last_version >= 0:
                elapsed_seconds = time.monotonic() - last_emit_seconds
                if elapsed_seconds < frame_interval_seconds:
                    time.sleep(frame_interval_seconds - elapsed_seconds)
                    latest_cached = self.latest_cached_preview(session_id)
                    if latest_cached is not None:
                        cached = latest_cached

            last_version = cached.version
            yield encode_mjpeg_chunk(
                self._rgb_jpeg_for_request(
                    cached,
                    width=width,
                    height=height,
                    quality=quality,
                )
            )
            last_emit_seconds = time.monotonic()

    def latest_depth_jpeg(
        self,
        session_id: str,
        *,
        width: int | None = DEFAULT_DEPTH_PREVIEW_WIDTH,
        height: int | None = None,
        quality: int = DEFAULT_DEPTH_PREVIEW_QUALITY,
    ) -> bytes:
        cached = self.latest_cached_preview(session_id)
        if cached is None:
            return self._placeholder_jpeg(
                title="Waiting For Depth Preview",
                subtitle=f"Session {session_id} has not produced a frame yet.",
                width=width,
                height=height,
                quality=quality,
            )
        if uses_default_preview_request(
            width=width,
            height=height,
            quality=quality,
            default_width=self.default_depth_width,
            default_height=self.default_depth_height,
            default_quality=self.default_depth_quality,
        ):
            return cached.depth_jpeg
        frame = resize_preview_frame(cached.depth_frame, width=width, height=height)
        return encode_jpeg(frame, quality=quality)

    def latest_snapshot(self, session_id: str) -> PreviewSnapshot | None:
        with self._lock:
            buffer = self._buffers.get(session_id)
        if buffer is None:
            return None
        return buffer.latest()

    def latest_cached_preview(self, session_id: str) -> CachedPreviewFrame | None:
        with self._lock:
            buffer = self._buffers.get(session_id)
        if buffer is None:
            return None
        return buffer.latest_cached()

    def wait_for_newer_preview(
        self,
        session_id: str,
        last_version: int,
        *,
        timeout_seconds: float | None = None,
    ) -> CachedPreviewFrame | None:
        with self._lock:
            buffer = self._buffers.get(session_id)
        if buffer is None:
            if timeout_seconds is not None:
                time.sleep(max(0.0, timeout_seconds))
            return None
        return buffer.wait_for_newer(last_version, timeout_seconds=timeout_seconds)

    def _buffer_for_session(self, session_id: str) -> PreviewFrameBuffer:
        with self._lock:
            if session_id not in self._buffers:
                self._buffers[session_id] = PreviewFrameBuffer(
                    preview_min_depth_mm=self.preview_min_depth_mm,
                    preview_max_depth_mm=self.preview_max_depth_mm,
                    default_rgb_width=self.default_rgb_width,
                    default_rgb_height=self.default_rgb_height,
                    default_rgb_quality=self.default_rgb_quality,
                    default_depth_width=self.default_depth_width,
                    default_depth_height=self.default_depth_height,
                    default_depth_quality=self.default_depth_quality,
                )
            return self._buffers[session_id]

    def _placeholder_jpeg(
        self,
        *,
        title: str,
        subtitle: str,
        width: int | None,
        height: int | None,
        quality: int,
    ) -> bytes:
        frame = placeholder_frame(
            width=self.runtime_config.rgb_size[0],
            height=self.runtime_config.rgb_size[1],
            title=title,
            subtitle=subtitle,
        )
        frame = resize_preview_frame(frame, width=width, height=height)
        return encode_jpeg(frame, quality=quality)

    def _rgb_jpeg_for_request(
        self,
        cached: CachedPreviewFrame,
        *,
        width: int | None,
        height: int | None,
        quality: int,
    ) -> bytes:
        if uses_default_preview_request(
            width=width,
            height=height,
            quality=quality,
            default_width=self.default_rgb_width,
            default_height=self.default_rgb_height,
            default_quality=self.default_rgb_quality,
        ):
            return cached.rgb_jpeg
        frame = resize_preview_frame(cached.rgb_frame, width=width, height=height)
        return encode_jpeg(frame, quality=quality)
