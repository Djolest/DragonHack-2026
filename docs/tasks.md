# Delivery Task List

## Architecture Freeze

- [x] `verifier/` is the unified browser client for both recording and verification.
- [x] `capture/` is the station-side FastAPI backend for OAK4 sessions and receipt generation.
- [x] `backend/` is the FastAPI receipt/anchor service.
- [x] `capture/app/depthai_client.py` is legacy and is not part of the live demo path.

## Bootstrap Complete

- [x] Monorepo structure created for `capture`, `backend`, `contracts`, `verifier`, and `docs`.
- [x] Python 3.11 starter services scaffolded with FastAPI and typed models.
- [x] Hardhat scaffold added for Flare Coston2 contract development.
- [x] Vite React web app starter added, with in-browser receipt verification already implemented.
- [x] Environment examples and run instructions documented.

## Next Prompt Priorities

- [ ] `TODO(next):` wire capture session start/stop/status flows into the unified `verifier/` web app against the `capture/` API.
- [ ] `TODO(next):` harden the live OAK4 station runtime and emitted metadata in `capture/app/session_runtime.py` and `capture/app/oak4_engine.py`.
- [ ] `TODO(next):` add upload and verification tests for `capture` and `backend`.
- [ ] `TODO(next):` generate contract artifacts and pipe ABI + deployment addresses into the browser app frontend.
- [ ] `TODO(next):` introduce async job processing for anchor submissions and retryable failures.
- [ ] `TODO(next):` add authentication for operator-triggered captures and protected backend actions.
- [ ] `TODO(next):` switch local file storage to a pluggable storage adapter so S3/IPFS can replace disk later.

## Suggested Prompt Order

1. Wire the browser capture flow into `verifier/` using the `capture/` session endpoints.
2. Harden the station runtime and emit production-ready receipt metadata from the live capture path.
3. Wire deployment output into the backend and add automated Flare anchoring.
4. Teach the browser app to read contract state directly from Flare and compare it to the receipt.
5. Add tests, linting, and CI polish once the functional flow is stable.
