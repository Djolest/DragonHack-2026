# OAKProof MVP Monorepo

OAKProof is a DragonHack MVP built around one browser app, one capture-station FastAPI service, and one receipt/anchor FastAPI service. The station records proof on a Luxonis OAK4 device, signs the resulting receipt, stores MVP artifacts locally, and the backend can anchor the receipt digest on Flare Coston2 for independent verification.

## Stack

- `verifier/`: Vite + React + TypeScript web app. This is the unified browser client for both recording workflows and verification workflows.
- `capture/`: Python 3.11 FastAPI station backend that owns OAK4 capture sessions, local artifact storage, and receipt generation.
- `backend/`: Python 3.11 FastAPI receipt/anchor service for ingestion, local persistence, signature verification, and Flare anchoring.
- `contracts/`: Hardhat TypeScript project with the `OAKProofAnchor` contract for Flare Coston2.
- `docs/`: architecture notes, env matrix, and next-step task list.

## Product Shape

- `verifier/` is the only blessed user-facing app. The current implementation is verification-first, and capture controls should live here rather than in a separate viewer product.
- `capture/` stays headless and browser-driven: it exposes the station-side FastAPI endpoints that the web app uses to start, inspect, and stop capture sessions.
- `backend/` stays headless and browser-driven: it stores normalized receipt records and handles optional Flare anchoring.

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

11. Start the unified web app:

    ```bash
    npm run dev:verifier
    ```

## Local MVP Flow

1. The browser app in `verifier/` is the single entrypoint for product workflows. Today it already covers verification, and capture flows should target the same app.
2. `capture` produces the proof asset, stores it on local disk, builds a signed receipt, and can optionally POST it to `backend`.
3. `backend` verifies the receipt signature, stores the record locally, and anchors the digests to Flare when a contract address and funded anchor key are configured.

## Important Starter Assumptions

- The capture service defaults to `CAPTURE_SIMULATE=true` so the repo is usable even when no physical OAK4 device is attached.
- The backend defaults to local JSON storage under `backend/data/`.
- Flare anchoring is disabled until `BACKEND_ANCHOR_CONTRACT_ADDRESS` and `BACKEND_ANCHOR_PRIVATE_KEY` are configured.
- `capture/app/depthai_client.py` is a legacy seam and is not part of the current session-based demo path.
- `TODO(next):` comments mark the safest next implementation prompts.

## Docs

- [docs/demo.md](docs/demo.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/environment.md](docs/environment.md)
- [docs/tasks.md](docs/tasks.md)
