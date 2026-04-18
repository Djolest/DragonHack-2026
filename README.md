# OAKProof MVP Monorepo

OAKProof is a DragonHack MVP for capturing physical proof from a Luxonis OAK4 station, signing the resulting receipt, storing the files locally for the MVP, and anchoring the receipt digest on Flare Coston2 for independent verification.

## Stack

- `capture/`: Python 3.11 capture station service using FastAPI and a DepthAI v3 integration seam.
- `backend/`: Python 3.11 FastAPI API for receipt ingestion, local persistence, signature verification, and Flare anchoring.
- `contracts/`: Hardhat TypeScript project with the `OAKProofAnchor` contract for Flare Coston2.
- `verifier/`: Vite + React + TypeScript verifier UI.
- `docs/`: architecture notes, env matrix, and next-step task list.

## Quickstart

1. Copy `capture/.env.example` to `capture/.env`.
2. Copy `backend/.env.example` to `backend/.env`.
3. Copy `contracts/.env.example` to `contracts/.env`.
4. Copy `verifier/.env.example` to `verifier/.env`.
5. Install Node workspaces from the repo root:

   ```bash
   npm install
   ```

6. Create and activate a Python 3.11 virtual environment for `capture/`, then install it:

   ```bash
   cd capture
   python -m venv .venv
   .venv\Scripts\activate
   pip install -e .[dev]
   ```

7. Repeat for `backend/`:

   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate
   pip install -e .[dev]
   ```

8. Compile and test the contract package:

   ```bash
   npm run compile:contracts
   npm run test:contracts
   ```

9. Start the backend:

   ```bash
   cd backend
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

10. Start the capture service:

    ```bash
    cd capture
    python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
    ```

11. Start the verifier UI:

    ```bash
    npm run dev:verifier
    ```

## Local MVP Flow

1. `capture` produces a proof asset, stores it under local disk, builds a signed receipt, and optionally POSTs it to `backend`.
2. `backend` verifies the receipt signature, stores the record locally, and anchors the digests to Flare when a contract address and funded anchor key are configured.
3. `verifier` fetches or pastes a receipt, recomputes the signed message, verifies the signer, and displays backend/chain status.

## Important Starter Assumptions

- The capture service defaults to `CAPTURE_SIMULATE=true` so the repo is usable before the physical OAK4 pipeline is implemented.
- The backend defaults to local JSON storage under `backend/data/`.
- Flare anchoring is disabled until `BACKEND_ANCHOR_CONTRACT_ADDRESS` and `BACKEND_ANCHOR_PRIVATE_KEY` are configured.
- `TODO(next):` comments mark the safest next implementation prompts.

## Docs

- [docs/architecture.md](docs/architecture.md)
- [docs/environment.md](docs/environment.md)
- [docs/tasks.md](docs/tasks.md)
