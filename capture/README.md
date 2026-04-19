# Capture Service

The capture package now contains two entrypoints:

- the FastAPI station service used by the OAKProof MVP
- a standalone DepthAI v3 OAK4 RGB-D viewer that connects to the first available stereo OAK4 device, runs `StereoDepth` plus `ImageAlign`, and shows synchronized RGB and aligned depth windows

## OAK4 RGB-D Viewer

### What it does

- connects to the first available DepthAI device
- prints device metadata and connected camera sensors
- validates that the device is a stereo-capable OAK4 model
- builds a DepthAI v3 pipeline with:
  - `Camera` on `CAM_A` for RGB
  - `Camera` on `CAM_B` and `CAM_C` for the stereo pair
  - `StereoDepth` for depth computation
  - `ImageAlign` to align depth to the RGB camera
  - `Sync` to emit synchronized RGB/depth pairs
- runs a physically grounded challenge:
  - draw a center ROI
  - compute aligned depth metrics in that ROI
  - ask the user to place a hand in the box and move it toward the camera
- tracks:
  - valid depth ratio
  - median depth
  - depth standard deviation
  - forward depth delta over time
  - least-squares plane-fit RMS
- displays:
  - `OAK4 RGB`
  - `OAK4 Aligned Depth`
- exits cleanly when you press `q`
- writes a JSON challenge summary to `capture/data/oak4_challenge_summary.json`

### Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

You can also install the package in editable mode:

```bash
pip install -e .[dev]
```

### Run

From the `capture/` directory:

```bash
python -m app.oak4_rgbd_viewer
```

To use a different threshold profile or summary output path:

```bash
python -m app.oak4_rgbd_viewer --config .\config\anti_replay_thresholds.json --summary-path .\data\session-01.json
```

If you installed the editable package entrypoint:

```bash
oak4-rgbd-viewer
```

### Troubleshooting Stereo Availability

- If the app exits with a message about missing `CAM_B` or `CAM_C`, the connected device is not a stereo OAK4 model for this workflow. `StereoDepth` needs a calibrated left/right pair, so a non-stereo model cannot produce aligned RGB-D output.
- If the device is detected but reported as non-`RVC4`, it is not an OAK4-class device. This viewer intentionally refuses to run because the requested pipeline targets stereo OAK4 hardware.
- If no devices are detected, reconnect the camera, verify data-capable USB or network connectivity, and rerun the script.
- If the device is slow to boot or connect, Luxonis documents `DEPTHAI_CONNECT_TIMEOUT`, `DEPTHAI_BOOTUP_TIMEOUT`, and `DEPTHAI_LEVEL=debug` as useful diagnostics and tuning knobs.
- If RGB appears but depth is sparse or unstable, make sure both stereo sensors are uncovered, the scene has visible texture, and the device calibration is intact.
- If the challenge stays `INCONCLUSIVE`, lower `min_valid_depth_ratio`, widen the ROI slightly, or reduce `max_depth_mm` so the metric ignores distant background.
- If replay risk is always `ELEVATED`, relax `max_plane_fit_rms_mm` or `max_depth_std_mm` after capturing a few real-hand sessions in your room.

## FastAPI Station Service

Run the API service with:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
```

### Session Endpoints

- `POST /api/v1/capture/sessions`
- `GET /api/v1/capture/sessions/{session_id}`
- `POST /api/v1/capture/sessions/{session_id}/stop`

Example request:

```json
{
  "asset_id": "batch-001",
  "operator_id": "operator-a",
  "notes": "First intake capture",
  "tags": ["intake", "oak4"]
}
```

### Notes

- The FastAPI capture service still defaults to simulation mode for the broader MVP receipt flow.
- Verified sessions now hash `rgb.mp4`, write a signed `receipt.json`, and can auto-submit that receipt to the backend for Flare anchoring.
- Static assets are exposed from `GET /assets/{path}` so the verifier can inspect locally stored artifacts during the MVP phase.
