# Backend Service

The backend is the receipt authority for the MVP. It verifies signed receipts from the capture station, stores them under local disk, and optionally anchors the digests to Flare Coston2 using the deployed `OAKProofAnchor` contract.

## Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Endpoints

- `GET /health`
- `POST /api/v1/receipts`
- `GET /api/v1/receipts/{receipt_id}`
- `POST /api/v1/receipts/{receipt_id}/anchor`
- `GET /api/v1/receipts/{receipt_id}/verify`

## Notes

- Local records are stored under `backend/data/records/`.
- If `BACKEND_ANCHOR_CONTRACT_ADDRESS` is blank, anchoring is intentionally disabled so local development stays frictionless.
- `TODO(next):` add durable queueing and retry handling so anchoring is not performed inline on the API request path.
