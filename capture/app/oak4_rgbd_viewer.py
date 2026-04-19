from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import cv2

from .config import DEFAULT_VERIFICATION_CONFIG_PATH
from .depth_challenge import load_verification_config
from .oak4_engine import Oak4RuntimeConfig, colorize_depth
from .preview import (
    FrameBufferingPreviewObserver,
    PreviewFrameBuffer,
    PreviewSnapshot,
    annotate_depth_frame,
    annotate_rgb_frame,
    placeholder_frame,
)
from .session_runtime import CaptureSessionManager
from .storage import LocalStorage

LOGGER = logging.getLogger("oakproof.oak4_rgbd_viewer")

RGB_WINDOW_NAME = "OAK4 RGB"
DEPTH_WINDOW_NAME = "OAK4 Aligned Depth"


class OpenCvPreviewObserver(FrameBufferingPreviewObserver):
    pass


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
        observer_factory=lambda _session_id: OpenCvPreviewObserver(frame_buffer),
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
