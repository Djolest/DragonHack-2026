from __future__ import annotations

import argparse
import json
import logging
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import Final

import cv2
import depthai as dai
import numpy as np

from .depth_challenge import (
    ChallengeFrameState,
    DepthChallengeTracker,
    RoiBox,
    compute_center_roi,
    load_challenge_config,
    write_summary_json,
)

LOGGER = logging.getLogger("oakproof.oak4_rgbd_viewer")

RGB_SOCKET: Final[dai.CameraBoardSocket] = dai.CameraBoardSocket.CAM_A
LEFT_SOCKET: Final[dai.CameraBoardSocket] = dai.CameraBoardSocket.CAM_B
RIGHT_SOCKET: Final[dai.CameraBoardSocket] = dai.CameraBoardSocket.CAM_C

RGB_WINDOW_NAME: Final[str] = "OAK4 RGB"
DEPTH_WINDOW_NAME: Final[str] = "OAK4 Aligned Depth"
CHALLENGE_NAME: Final[str] = "Place your hand in the center box and move it toward the camera"

DEFAULT_CONFIG_PATH: Final[Path] = (
    Path(__file__).resolve().parents[1] / "config" / "anti_replay_thresholds.json"
)
DEFAULT_SUMMARY_PATH: Final[Path] = (
    Path(__file__).resolve().parents[1] / "data" / "oak4_challenge_summary.json"
)


class UnsupportedDeviceError(RuntimeError):
    """Raised when the first available device cannot provide stereo RGB-D output."""


@dataclass(frozen=True, slots=True)
class ViewerConfig:
    fps: float = 20.0
    rgb_size: tuple[int, int] = (1280, 960)
    stereo_size: tuple[int, int] = (640, 400)
    sync_threshold_ms: int = 50


@dataclass(frozen=True, slots=True)
class DeviceSummary:
    name: str
    device_id: str
    state: str
    platform: str
    product_name: str | None
    board_name: str | None
    board_revision: str | None
    connected_sockets: tuple[str, ...]
    camera_sensors: dict[str, str]
    usb_speed: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class FpsCounter:
    def __init__(self, window_size: int = 30) -> None:
        self._frame_times: deque[float] = deque(maxlen=window_size)

    def tick(self) -> None:
        self._frame_times.append(time.perf_counter())

    def get_fps(self) -> float:
        if len(self._frame_times) < 2:
            return 0.0
        elapsed = self._frame_times[-1] - self._frame_times[0]
        if elapsed <= 0:
            return 0.0
        return (len(self._frame_times) - 1) / elapsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OAK4 RGB-D anti-replay challenge viewer")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--summary-path", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def configure_logging(level_name: str) -> None:
    log_level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def enum_name(value: object) -> str:
    text = str(value)
    if "X_LINK_" in text:
        return text.split("X_LINK_", maxsplit=1)[1]
    if "." in text:
        return text.rsplit(".", maxsplit=1)[1]
    return text


def first_available_device() -> dai.DeviceInfo:
    LOGGER.info("Searching for available DepthAI devices")
    devices = dai.Device.getAllAvailableDevices()
    if not devices:
        raise RuntimeError("No DepthAI device detected. Connect an OAK4 camera and try again.")

    for index, device_info in enumerate(devices, start=1):
        LOGGER.info(
            "Detected device %d: name=%s id=%s state=%s",
            index,
            getattr(device_info, "name", "unknown"),
            getattr(device_info, "deviceId", "unknown"),
            enum_name(getattr(device_info, "state", "unknown")),
        )

    selected = devices[0]
    LOGGER.info(
        "Connecting to the first available device: name=%s id=%s",
        getattr(selected, "name", "unknown"),
        getattr(selected, "deviceId", "unknown"),
    )
    return selected


def summarize_device(device_info: dai.DeviceInfo, device: dai.Device) -> DeviceSummary:
    camera_sensor_names = {
        enum_name(socket): sensor_name
        for socket, sensor_name in device.getCameraSensorNames().items()
    }
    connected_sockets = tuple(sorted(enum_name(socket) for socket in device.getConnectedCameras()))

    product_name: str | None = None
    board_name: str | None = None
    board_revision: str | None = None
    try:
        eeprom = device.readCalibration().getEepromData()
        product_name = str(getattr(eeprom, "productName", "") or "") or None
        board_name = str(getattr(eeprom, "boardName", "") or "") or None
        board_revision = str(getattr(eeprom, "boardRev", "") or "") or None
    except RuntimeError as exc:
        LOGGER.warning("Unable to read calibration EEPROM details: %s", exc)

    usb_speed: str | None = None
    try:
        usb_speed = enum_name(device.getUsbSpeed())
    except RuntimeError:
        usb_speed = None

    summary = DeviceSummary(
        name=str(getattr(device_info, "name", "unknown")),
        device_id=str(device.getDeviceInfo().getDeviceId()),
        state=enum_name(getattr(device_info, "state", "unknown")),
        platform=enum_name(device.getPlatform()),
        product_name=product_name,
        board_name=board_name,
        board_revision=board_revision,
        connected_sockets=connected_sockets,
        camera_sensors=camera_sensor_names,
        usb_speed=usb_speed,
    )
    LOGGER.info("Connected device summary")
    LOGGER.info("  product=%s", summary.product_name or "unknown")
    LOGGER.info("  board=%s", summary.board_name or "unknown")
    LOGGER.info("  revision=%s", summary.board_revision or "unknown")
    LOGGER.info("  platform=%s", summary.platform)
    LOGGER.info("  usb_speed=%s", summary.usb_speed or "unknown")
    LOGGER.info("  connected_sockets=%s", ", ".join(summary.connected_sockets) or "none")
    LOGGER.info(
        "  camera_sensors=%s",
        ", ".join(f"{socket}:{sensor}" for socket, sensor in summary.camera_sensors.items()) or "none",
    )
    return summary


def validate_stereo_oak4(summary: DeviceSummary) -> None:
    required_sockets = {"CAM_A", "CAM_B", "CAM_C"}
    available_sockets = set(summary.connected_sockets)

    if summary.platform != "RVC4":
        raise UnsupportedDeviceError(
            "This viewer targets stereo OAK4 hardware on the RVC4 platform. "
            f"Detected platform={summary.platform}, product={summary.product_name or summary.name}. "
            "The center-ROI anti-replay challenge needs an OAK4 stereo device because it relies on "
            "StereoDepth and aligned RGB-depth output."
        )

    missing_sockets = sorted(required_sockets - available_sockets)
    if missing_sockets:
        raise UnsupportedDeviceError(
            "The connected OAK4 device is not a stereo-capable model for this challenge. "
            "This viewer requires CAM_A for RGB plus CAM_B and CAM_C as the calibrated stereo pair. "
            f"Missing sockets: {', '.join(missing_sockets)}. "
            f"Detected sockets: {', '.join(summary.connected_sockets) or 'none'}."
        )


def build_rgbd_queue(
    pipeline: dai.Pipeline,
    config: ViewerConfig,
) -> dai.DataOutputQueue:
    # RGB camera node: produces the main color stream from CAM_A for visualization and depth alignment.
    rgb_camera = pipeline.create(dai.node.Camera).build(RGB_SOCKET)

    # Left stereo camera node: feeds the left rectified image into the stereo matcher.
    left_camera = pipeline.create(dai.node.Camera).build(LEFT_SOCKET)

    # Right stereo camera node: feeds the right rectified image into the stereo matcher.
    right_camera = pipeline.create(dai.node.Camera).build(RIGHT_SOCKET)

    # StereoDepth node: computes dense depth from the synchronized CAM_B/C stereo pair.
    stereo = pipeline.create(dai.node.StereoDepth)
    stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.ROBOTICS)
    stereo.setLeftRightCheck(True)
    stereo.setSubpixel(True)

    # ImageAlign node: warps the depth map into CAM_A's coordinate frame.
    align = pipeline.create(dai.node.ImageAlign)

    # Sync node: groups RGB and aligned depth into timestamp-matched message bundles.
    sync = pipeline.create(dai.node.Sync)
    sync.setSyncThreshold(timedelta(milliseconds=config.sync_threshold_ms))

    rgb_output = rgb_camera.requestOutput(
        size=config.rgb_size,
        fps=config.fps,
        type=dai.ImgFrame.Type.BGR888i,
        enableUndistortion=True,
    )
    left_output = left_camera.requestOutput(size=config.stereo_size, fps=config.fps)
    right_output = right_camera.requestOutput(size=config.stereo_size, fps=config.fps)

    left_output.link(stereo.left)
    right_output.link(stereo.right)
    stereo.depth.link(align.input)
    rgb_output.link(align.inputAlignTo)
    rgb_output.link(sync.inputs["rgb"])
    align.outputAligned.link(sync.inputs["depth"])
    return sync.out.createOutputQueue()


def colorize_depth(depth_frame: np.ndarray) -> np.ndarray:
    if depth_frame.size == 0:
        return np.zeros((1, 1, 3), dtype=np.uint8)

    valid_mask = depth_frame > 0
    if not np.any(valid_mask):
        return np.zeros((depth_frame.shape[0], depth_frame.shape[1], 3), dtype=np.uint8)

    depth_float = depth_frame.astype(np.float32)
    valid_depth = depth_float[valid_mask]
    near_depth = max(float(np.percentile(valid_depth, 3)), 1.0)
    far_depth = max(float(np.percentile(valid_depth, 97)), near_depth + 1.0)

    log_depth = np.zeros_like(depth_float, dtype=np.float32)
    np.log(depth_float, out=log_depth, where=valid_mask)

    log_near = float(np.log(near_depth))
    log_far = float(np.log(far_depth))
    normalized = np.zeros_like(depth_float, dtype=np.uint8)
    if log_far > log_near:
        scaled = np.clip((log_depth - log_near) * (255.0 / (log_far - log_near)), 0.0, 255.0)
        normalized = scaled.astype(np.uint8)

    depth_color = cv2.applyColorMap(normalized, cv2.COLORMAP_TURBO)
    depth_color[~valid_mask] = 0
    return depth_color


def create_display_windows() -> None:
    cv2.namedWindow(RGB_WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.namedWindow(DEPTH_WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(RGB_WINDOW_NAME, 1280, 720)
    cv2.resizeWindow(DEPTH_WINDOW_NAME, 1280, 720)


def draw_center_roi(frame: np.ndarray, roi: RoiBox, color: tuple[int, int, int]) -> np.ndarray:
    annotated = frame.copy()
    cv2.rectangle(annotated, (roi.x0, roi.y0), (roi.x1, roi.y1), color, 2)
    cv2.putText(
        annotated,
        "CENTER ROI",
        (roi.x0, max(24, roi.y0 - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        color,
        2,
        cv2.LINE_AA,
    )
    return annotated


def status_color(frame_state: ChallengeFrameState) -> tuple[int, int, int]:
    if frame_state.live_status == "PASSED":
        return (76, 210, 106)
    if frame_state.live_status == "INCONCLUSIVE":
        return (64, 64, 255)
    return (0, 191, 255)


def build_status_lines(
    frame_state: ChallengeFrameState,
    fps: float,
    device_summary: DeviceSummary,
) -> list[str]:
    stats = frame_state.stats
    median_depth = "n/a" if stats.median_depth_mm is None else f"{stats.median_depth_mm:.0f} mm"
    depth_std = "n/a" if stats.depth_std_mm is None else f"{stats.depth_std_mm:.1f} mm"
    depth_delta = "n/a" if stats.depth_delta_mm is None else f"{stats.depth_delta_mm:.1f} mm"
    plane_fit = "n/a" if stats.plane_fit_rms_mm is None else f"{stats.plane_fit_rms_mm:.1f} mm"

    return [
        "Challenge: hand in center box, then move closer",
        f"Status: {frame_state.live_status}",
        f"Reason: {frame_state.status_reason}",
        f"Replay risk: {frame_state.replay_risk}",
        f"Risk note: {frame_state.replay_risk_reason}",
        f"Valid depth ratio: {stats.valid_depth_ratio:.2f}",
        f"Median depth: {median_depth}",
        f"Depth std: {depth_std}",
        f"Depth delta: {depth_delta}",
        f"Plane fit RMS: {plane_fit}",
        f"Max forward motion: {frame_state.max_forward_motion_mm:.1f} mm",
        f"Device: {device_summary.product_name or device_summary.name} | FPS {fps:.1f}",
    ]


def draw_status_panel(
    frame: np.ndarray,
    lines: list[str],
    panel_color: tuple[int, int, int],
) -> np.ndarray:
    overlay = frame.copy()
    panel_width = min(frame.shape[1] - 20, 640)
    panel_height = 34 + (len(lines) * 26)
    cv2.rectangle(overlay, (10, 10), (10 + panel_width, 10 + panel_height), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.42, frame, 0.58, 0.0, frame)
    cv2.rectangle(frame, (10, 10), (10 + panel_width, 10 + panel_height), panel_color, 2)

    for index, line in enumerate(lines):
        y = 36 + (index * 26)
        color = panel_color if index in {1, 3} else (240, 240, 240)
        cv2.putText(
            frame,
            line,
            (24, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            color,
            2,
            cv2.LINE_AA,
        )
    return frame


def annotate_rgb_frame(
    frame: np.ndarray,
    roi: RoiBox,
    frame_state: ChallengeFrameState,
    fps: float,
    device_summary: DeviceSummary,
) -> np.ndarray:
    color = status_color(frame_state)
    annotated = draw_center_roi(frame, roi, color)
    return draw_status_panel(annotated, build_status_lines(frame_state, fps, device_summary), color)


def annotate_depth_frame(
    depth_color: np.ndarray,
    roi: RoiBox,
    frame_state: ChallengeFrameState,
) -> np.ndarray:
    annotated = draw_center_roi(depth_color, roi, status_color(frame_state))
    stats = frame_state.stats
    summary = (
        f"valid={stats.valid_depth_ratio:.2f} "
        f"median={stats.median_depth_mm:.0f}mm "
        if stats.median_depth_mm is not None
        else "valid=0.00 median=n/a "
    )
    cv2.putText(
        annotated,
        summary.strip(),
        (24, annotated.shape[0] - 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return annotated


def extract_synced_frames(message_group: dai.MessageGroup) -> tuple[dai.ImgFrame, dai.ImgFrame]:
    rgb_message = message_group["rgb"]
    depth_message = message_group["depth"]
    if not isinstance(rgb_message, dai.ImgFrame) or not isinstance(depth_message, dai.ImgFrame):
        raise RuntimeError("Received an incomplete synchronized RGB-depth message group.")
    return rgb_message, depth_message


def build_summary_payload(
    *,
    tracker: DepthChallengeTracker,
    device_summary: DeviceSummary,
    last_state: ChallengeFrameState | None,
) -> dict[str, object]:
    return tracker.build_summary(device_info=device_summary.to_dict(), last_state=last_state)


def run_display_loop(
    pipeline: dai.Pipeline,
    queue: dai.DataOutputQueue,
    challenge_tracker: DepthChallengeTracker,
    device_summary: DeviceSummary,
    summary_path: Path,
) -> dict[str, object]:
    fps_counter = FpsCounter()
    last_state: ChallengeFrameState | None = None
    create_display_windows()

    LOGGER.info("Starting pipeline")
    pipeline.start()
    LOGGER.info("Pipeline started. Press 'q' in an OpenCV window to exit.")

    while pipeline.isRunning():
        message_group = queue.get()
        if not isinstance(message_group, dai.MessageGroup):
            LOGGER.debug("Skipping unexpected message type: %s", type(message_group).__name__)
            continue

        rgb_message, depth_message = extract_synced_frames(message_group)
        rgb_frame = rgb_message.getCvFrame()
        depth_frame = depth_message.getFrame()

        roi = compute_center_roi(
            rgb_frame.shape,
            roi_width_fraction=challenge_tracker.config.roi_width_fraction,
            roi_height_fraction=challenge_tracker.config.roi_height_fraction,
        )
        last_state = challenge_tracker.update(depth_frame, roi)
        fps_counter.tick()

        rgb_preview = annotate_rgb_frame(
            rgb_frame,
            roi,
            last_state,
            fps_counter.get_fps(),
            device_summary,
        )
        depth_preview = annotate_depth_frame(colorize_depth(depth_frame), roi, last_state)

        cv2.imshow(RGB_WINDOW_NAME, rgb_preview)
        cv2.imshow(DEPTH_WINDOW_NAME, depth_preview)

        if (cv2.waitKey(1) & 0xFF) == ord("q"):
            LOGGER.info("Exit requested by user")
            break

    summary = build_summary_payload(
        tracker=challenge_tracker,
        device_summary=device_summary,
        last_state=last_state,
    )
    write_summary_json(summary_path, summary)
    LOGGER.info("Challenge summary written to %s", summary_path)
    LOGGER.info("Challenge summary JSON:\n%s", json.dumps(summary, indent=2, sort_keys=True))
    return summary


def run_viewer(
    viewer_config: ViewerConfig,
    *,
    challenge_config_path: Path,
    summary_path: Path,
) -> dict[str, object]:
    challenge_config = load_challenge_config(challenge_config_path)
    LOGGER.info("Loaded challenge thresholds from %s", challenge_config_path)

    device_info = first_available_device()
    with dai.Device(device_info) as device:
        device_summary = summarize_device(device_info, device)
        validate_stereo_oak4(device_summary)

        challenge_tracker = DepthChallengeTracker(challenge_config)
        with dai.Pipeline(device) as pipeline:
            queue = build_rgbd_queue(pipeline, viewer_config)
            return run_display_loop(
                pipeline,
                queue,
                challenge_tracker,
                device_summary,
                summary_path,
            )


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    viewer_config = ViewerConfig()

    try:
        run_viewer(
            viewer_config,
            challenge_config_path=args.config.resolve(),
            summary_path=args.summary_path.resolve(),
        )
    except UnsupportedDeviceError as exc:
        LOGGER.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        LOGGER.info("Interrupted by user")
        return 0
    except RuntimeError as exc:
        LOGGER.error("DepthAI runtime failure: %s", exc)
        return 1
    finally:
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
