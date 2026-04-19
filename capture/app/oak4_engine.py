from __future__ import annotations

import time
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Final

import cv2
import numpy as np

try:
    import depthai as dai
except ImportError:  # pragma: no cover - hardware dependency
    dai = None


RGB_SOCKET: Final[object] = None if dai is None else dai.CameraBoardSocket.CAM_A
LEFT_SOCKET: Final[object] = None if dai is None else dai.CameraBoardSocket.CAM_B
RIGHT_SOCKET: Final[object] = None if dai is None else dai.CameraBoardSocket.CAM_C


class UnsupportedDeviceError(RuntimeError):
    """Raised when the connected device cannot provide stereo RGB-D output."""


@dataclass(frozen=True, slots=True)
class Oak4RuntimeConfig:
    fps: float = 20.0
    rgb_size: tuple[int, int] = (1280, 960)
    stereo_size: tuple[int, int] = (1280, 800)
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


@dataclass(frozen=True, slots=True)
class SyncedFrame:
    rgb_frame: np.ndarray
    depth_frame: np.ndarray
    timestamp_seconds: float


class FrameSource:
    def open(self) -> DeviceSummary:
        raise NotImplementedError

    def next_frame(self) -> SyncedFrame | None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


def enum_name(value: object) -> str:
    text = str(value)
    if "X_LINK_" in text:
        return text.split("X_LINK_", maxsplit=1)[1]
    if "." in text:
        return text.rsplit(".", maxsplit=1)[1]
    return text


def _matching_device(target_device_id: str | None) -> object:
    assert dai is not None
    devices = dai.Device.getAllAvailableDevices()
    if not devices:
        raise RuntimeError("No DepthAI device detected. Connect an OAK4 camera and try again.")

    if target_device_id is None:
        return devices[0]

    for device_info in devices:
        device_id = str(getattr(device_info, "deviceId", "") or "")
        if device_id == target_device_id:
            return device_info
    raise RuntimeError(f"DepthAI device {target_device_id} was not found.")


def summarize_device(device_info: object, device: object) -> DeviceSummary:
    assert dai is not None
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
    except RuntimeError:
        product_name = None
        board_name = None
        board_revision = None

    usb_speed: str | None = None
    try:
        usb_speed = enum_name(device.getUsbSpeed())
    except RuntimeError:
        usb_speed = None

    return DeviceSummary(
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


def validate_stereo_oak4(summary: DeviceSummary) -> None:
    required_sockets = {"CAM_A", "CAM_B", "CAM_C"}
    available_sockets = set(summary.connected_sockets)

    if summary.platform != "RVC4":
        raise UnsupportedDeviceError(
            "This capture flow requires a stereo-capable OAK4 device on the RVC4 platform."
        )

    missing_sockets = sorted(required_sockets - available_sockets)
    if missing_sockets:
        raise UnsupportedDeviceError(
            "The connected OAK4 device cannot provide stereo RGB-D output. "
            f"Missing sockets: {', '.join(missing_sockets)}."
        )


def configure_rvc4_stereo_depth(stereo: object) -> None:
    assert dai is not None

    # RVC4 DENSITY favors higher fill-rate and is a better fit for our
    # challenge/anti-screen flow than the more conservative ACCURACY preset.
    stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.DENSITY)
    stereo.setPostProcessingHardwareResources(3, 3)
    stereo.setRectifyEdgeFillColor(0)


def build_rgbd_queue(pipeline: object, config: Oak4RuntimeConfig) -> object:
    assert dai is not None
    rgb_camera = pipeline.create(dai.node.Camera).build(RGB_SOCKET)
    left_camera = pipeline.create(dai.node.Camera).build(LEFT_SOCKET)
    right_camera = pipeline.create(dai.node.Camera).build(RIGHT_SOCKET)

    stereo = pipeline.create(dai.node.StereoDepth)
    configure_rvc4_stereo_depth(stereo)

    align = pipeline.create(dai.node.ImageAlign)
    align.setInterpolation(dai.Interpolation.DEFAULT_DISPARITY_DEPTH)
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


def extract_synced_frames(message_group: object) -> tuple[object, object]:
    assert dai is not None
    rgb_message = message_group["rgb"]
    depth_message = message_group["depth"]
    if not isinstance(rgb_message, dai.ImgFrame) or not isinstance(depth_message, dai.ImgFrame):
        raise RuntimeError("Received an incomplete synchronized RGB-depth message group.")
    return rgb_message, depth_message


class Oak4FrameSource(FrameSource):
    def __init__(
        self,
        *,
        runtime_config: Oak4RuntimeConfig,
        oak_device_id: str | None,
    ) -> None:
        self.runtime_config = runtime_config
        self.oak_device_id = oak_device_id
        self._stack: ExitStack | None = None
        self._queue: object | None = None
        self._device_summary: DeviceSummary | None = None

    def open(self) -> DeviceSummary:
        if dai is None:  # pragma: no cover - import guard
            raise RuntimeError(
                "DepthAI is not installed in this environment. Install dependencies or enable CAPTURE_SIMULATE."
            )

        device_info = _matching_device(self.oak_device_id)
        stack = ExitStack()
        device = stack.enter_context(dai.Device(device_info))
        summary = summarize_device(device_info, device)
        validate_stereo_oak4(summary)
        pipeline = stack.enter_context(dai.Pipeline(device))
        queue = build_rgbd_queue(pipeline, self.runtime_config)
        pipeline.start()

        self._stack = stack
        self._queue = queue
        self._device_summary = summary
        return summary

    def next_frame(self) -> SyncedFrame | None:
        if self._queue is None:
            raise RuntimeError("Frame source must be opened before reading frames.")

        message_group = self._queue.get()
        if message_group is None:
            return None
        rgb_message, depth_message = extract_synced_frames(message_group)
        return SyncedFrame(
            rgb_frame=rgb_message.getCvFrame(),
            depth_frame=depth_message.getFrame(),
            timestamp_seconds=time.monotonic(),
        )

    def close(self) -> None:
        if self._stack is not None:
            self._stack.close()
            self._stack = None
            self._queue = None


class SimulatedFrameSource(FrameSource):
    def __init__(self, *, runtime_config: Oak4RuntimeConfig) -> None:
        self.runtime_config = runtime_config
        self._frame_index = 0
        self._timestamp_seconds = 0.0

    def open(self) -> DeviceSummary:
        return DeviceSummary(
            name="simulated-oak4",
            device_id="simulate",
            state="SIMULATED",
            platform="RVC4",
            product_name="OAK4-SIM",
            board_name="SIM-BOARD",
            board_revision="SIM",
            connected_sockets=("CAM_A", "CAM_B", "CAM_C"),
            camera_sensors={"CAM_A": "SIM_RGB", "CAM_B": "SIM_LEFT", "CAM_C": "SIM_RIGHT"},
            usb_speed="SIMULATED",
        )

    def next_frame(self) -> SyncedFrame:
        self._frame_index += 1
        frame_interval = 1.0 / max(1.0, self.runtime_config.fps)
        self._timestamp_seconds += frame_interval
        time.sleep(frame_interval)

        rgb_width, rgb_height = self.runtime_config.rgb_size
        xs = np.linspace(0.0, 1.0, rgb_width, dtype=np.float32)
        ys = np.linspace(0.0, 1.0, rgb_height, dtype=np.float32)
        x_grid, y_grid = np.meshgrid(xs, ys)

        rgb_frame = np.zeros((rgb_height, rgb_width, 3), dtype=np.uint8)
        rgb_frame[..., 0] = np.clip(60 + (110 * x_grid), 0, 255).astype(np.uint8)
        rgb_frame[..., 1] = np.clip(80 + (120 * y_grid), 0, 255).astype(np.uint8)
        rgb_frame[..., 2] = np.clip(90 + (90 * (1.0 - x_grid)), 0, 255).astype(np.uint8)

        depth_frame = (
            850.0
            + (240.0 * x_grid)
            + (180.0 * y_grid)
            + (60.0 * np.sin((self._frame_index / 18.0) + (4.0 * x_grid)))
        ).astype(np.float32)

        center_w0 = int(rgb_width * 0.2)
        center_w1 = int(rgb_width * 0.8)
        center_h0 = int(rgb_height * 0.2)
        center_h1 = int(rgb_height * 0.8)
        motion_phase = (np.sin(self._frame_index / 14.0) + 1.0) / 2.0
        object_depth = 700.0 - (260.0 * motion_phase)
        depth_frame[center_h0:center_h1, center_w0:center_w1] = object_depth
        rgb_frame[center_h0:center_h1, center_w0:center_w1, 2] = 220

        return SyncedFrame(
            rgb_frame=rgb_frame,
            depth_frame=depth_frame.astype(np.uint16),
            timestamp_seconds=self._timestamp_seconds,
        )

    def close(self) -> None:
        return None


def colorize_depth(
    depth_frame: np.ndarray,
    *,
    min_depth_mm: float = 200.0,
    max_depth_mm: float = 4000.0,
) -> np.ndarray:
    if depth_frame.size == 0:
        return np.zeros((1, 1, 3), dtype=np.uint8)

    valid_mask = depth_frame > 0
    if not np.any(valid_mask):
        return np.zeros((depth_frame.shape[0], depth_frame.shape[1], 3), dtype=np.uint8)

    depth_float = depth_frame.astype(np.float32)
    normalized = np.zeros_like(depth_float, dtype=np.uint8)
    valid_depth = depth_float[valid_mask]
    near_depth = max(min_depth_mm, float(np.percentile(valid_depth, 2)))
    far_depth = min(max_depth_mm, float(np.percentile(valid_depth, 98)))
    far_depth = max(near_depth + 1.0, far_depth)

    log_depth = np.zeros_like(depth_float, dtype=np.float32)
    clipped_depth = np.clip(depth_float, near_depth, far_depth)
    np.log(clipped_depth, out=log_depth, where=valid_mask)

    log_near = float(np.log(near_depth))
    log_far = float(np.log(far_depth))
    if log_far > log_near:
        scaled = np.clip(
            (log_depth - log_near) * (255.0 / (log_far - log_near)),
            0.0,
            255.0,
        )
        normalized = scaled.astype(np.uint8)

    depth_color = cv2.applyColorMap(normalized, cv2.COLORMAP_TURBO)
    depth_color[~valid_mask] = 0
    return depth_color
