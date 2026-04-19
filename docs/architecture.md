# OAKProof Architecture

## Purpose

OAKProof is organized around a single browser app backed by two FastAPI services. The capture station records proof on a Luxonis OAK4 device, signs a structured receipt, persists MVP files locally, and the receipt service can anchor the proof digest on Flare Coston2 so an independent verifier can confirm what was captured and when.

## Service Boundaries

### `verifier/`

- Blessed browser app for both operator capture flows and verification flows.
- Current implementation already handles receipt verification and Flare transaction inspection in-browser.
- New user-facing recording controls should call the `capture/` API from this app instead of introducing a separate viewer product.

### `capture/`

- Station-side FastAPI backend that owns OAK4 session runtime, local artifact storage, and receipt generation.
- Exposes `/api/v1/capture/sessions*` plus `/assets/{path}` for the browser app.
- Signs the receipt with the station wallet using an EIP-191 message signature.
- For verified sessions, hashes the recorded video, writes a signed receipt, and can auto-forward it to `backend/`.
- The live path runs through `service.py`, `session_runtime.py`, and `oak4_engine.py`; `depthai_client.py` is legacy and not part of the current demo flow.

### `backend/`

- FastAPI receipt/anchor service for the web app.
- Validates the signature and signer allowlist.
- Stores normalized receipt records under `backend/data/records/`.
- Anchors receipt and asset digests to the `OAKProofAnchor` contract.
- Exposes verification endpoints for the browser app.

### `contracts/`

- Anchors the immutable digest tuple:
  - `receiptIdHash`
  - `receiptDigest`
  - `assetDigest`
  - `storageUri`

## MVP Data Flow

1. The browser app in `verifier/` is the single user-facing entrypoint for both recording and verification.
2. For recording, the browser app starts and stops sessions through `capture`'s `/api/v1/capture/sessions*` endpoints.
3. The capture service saves artifacts under `capture/data/captures/YYYYMMDD/`, writes proof metadata, and finalizes a signed receipt.
4. The capture service can auto-submit the signed receipt to `backend/`.
5. Backend stores `backend/data/records/{receipt_id}.json` and can anchor digests on Flare Coston2 inline on ingest.
6. The same browser app fetches receipt records, validates the signature, decodes the Flare transaction, and compares the tx digest to the uploaded video hash.

## Trust Model

- The capture station private key is the trust root for receipt authorship.
- The backend is the current MVP authority for local record retrieval and chain submission.
- The smart contract is the public timestamped anchor for immutable receipt digests.
- The browser app can already perform local signature checks without trusting the backend.

## Planned Next Hardening

- `TODO(next):` wire capture session controls and live session status into the unified browser app.
- `TODO(next):` harden the OAK4 session runtime metadata and proof outputs produced by `capture/`.
- `TODO(next):` move anchoring to an async worker with retries and receipt state transitions.
- `TODO(next):` generate contract ABI artifacts for the browser app so it can read anchors directly from Flare.
- `TODO(next):` add authn/authz for capture operators and backend admin actions.
