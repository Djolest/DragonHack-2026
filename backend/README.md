# Backend Service

The backend is the receipt authority for the MVP. It verifies signed receipts from the capture station, stores them on local disk, anchors the digests to Flare Coston2 when configured, and decodes transaction payloads for the verifier UI.

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
- `GET /api/v1/transactions/{tx_hash}`
- `GET /tx/{tx_hash}`

## Notes

- Local records are stored under `backend/data/records/`.
- If `BACKEND_ANCHOR_CONTRACT_ADDRESS` is blank, anchoring is intentionally disabled so local development stays frictionless.
- `POST /api/v1/receipts` can now anchor inline when `BACKEND_ANCHOR_ON_INGEST=true` and chain credentials are configured.
- The transaction endpoint understands both the current contract-based anchor transactions and the older `proof:{...}` payload transactions from the earlier Flask prototype.
- `TODO(next):` add durable queueing and retry handling so anchoring is not performed inline on the API request path.
