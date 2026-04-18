# OAKProof Architecture

## Purpose

OAKProof captures a proof asset at a Luxonis OAK4 station, signs a structured receipt, persists the files locally for the MVP, and anchors the proof digest on Flare Coston2 so an independent verifier can confirm what was captured and when.

## Service Boundaries

### `capture/`

- Owns hardware integration with DepthAI v3.
- Produces the proof asset and the receipt payload.
- Signs the receipt with the station wallet using an EIP-191 message signature.
- Stores the raw asset and signed receipt locally.
- Optionally forwards the signed receipt to `backend/`.

### `backend/`

- Validates the signature and signer allowlist.
- Stores normalized receipt records under `backend/data/records/`.
- Anchors receipt and asset digests to the `OAKProofAnchor` contract.
- Exposes verification endpoints for the verifier UI.

### `contracts/`

- Anchors the immutable digest tuple:
  - `receiptIdHash`
  - `receiptDigest`
  - `assetDigest`
  - `storageUri`

### `verifier/`

- Fetches backend records or verifies pasted receipts locally.
- Rebuilds the exact signed message.
- Recovers the signing address in the browser.
- Displays Flare explorer links when anchoring is complete.

## MVP Data Flow

1. Operator triggers `POST /api/v1/capture`.
2. Capture service saves the asset under `capture/data/captures/YYYYMMDD/`.
3. Capture service signs a canonical JSON receipt payload.
4. Backend receives the receipt and stores `backend/data/records/{receipt_id}.json`.
5. Backend anchors digests on Flare Coston2 when configured.
6. Verifier UI validates the signature and presents the anchor state.

## Trust Model

- The capture station private key is the trust root for receipt authorship.
- The backend is the current MVP authority for local record retrieval and chain submission.
- The smart contract is the public timestamped anchor for immutable receipt digests.
- The verifier can already perform local signature checks without trusting the backend.

## Planned Next Hardening

- `TODO(next):` implement the real OAK4 camera pipeline with synchronized RGB/depth metadata.
- `TODO(next):` move anchoring to an async worker with retries and receipt state transitions.
- `TODO(next):` generate contract ABI artifacts for the verifier so it can read anchors directly from Flare.
- `TODO(next):` add authn/authz for capture operators and backend admin actions.
