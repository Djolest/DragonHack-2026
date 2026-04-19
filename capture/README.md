# Capture Station Backend

`capture/` is the station-side FastAPI backend for OAKProof. In the blessed product shape, the browser app in `verifier/` is the only user-facing client, and it talks to this service for recording workflows while `backend/` handles receipt persistence and anchoring.

Install the package from `capture/` with:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

## Run The Station Service

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

- The station service is the live capture path for the MVP, whether it is running against real OAK4 hardware or simulation mode.
- Verified sessions hash `rgb.mp4`, write a signed `receipt.json`, and can auto-submit that receipt to the backend for Flare anchoring.
- Static assets are exposed from `GET /assets/{path}` so the browser app can inspect locally stored artifacts during the MVP phase.
- The current session-based flow runs through `app/service.py`, `app/session_runtime.py`, and `app/oak4_engine.py`.

## Legacy Local Utilities

- `python -m app.oak4_rgbd_viewer` remains available as a local hardware diagnostic tool.
- The RGB-D viewer is not part of the live browser-first demo path and should not be treated as the primary product UX.
- `app/depthai_client.py` is also legacy and is not used by the current session-based capture flow.
