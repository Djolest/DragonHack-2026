# Delivery Task List

## Bootstrap Complete

- [x] Monorepo structure created for `capture`, `backend`, `contracts`, `verifier`, and `docs`.
- [x] Python 3.11 starter services scaffolded with FastAPI and typed models.
- [x] Hardhat scaffold added for Flare Coston2 contract development.
- [x] Vite React verifier starter added with in-browser signature verification.
- [x] Environment examples and run instructions documented.

## Next Prompt Priorities

- [ ] `TODO(next):` implement the real DepthAI v3 OAK4 capture pipeline and metadata extraction in `capture/app/depthai_client.py`.
- [ ] `TODO(next):` add upload and verification tests for `capture` and `backend`.
- [ ] `TODO(next):` generate contract artifacts and pipe ABI + deployment addresses into the verifier frontend.
- [ ] `TODO(next):` introduce async job processing for anchor submissions and retryable failures.
- [ ] `TODO(next):` add authentication for operator-triggered captures and protected backend actions.
- [ ] `TODO(next):` switch local file storage to a pluggable storage adapter so S3/IPFS can replace disk later.

## Suggested Prompt Order

1. Build the real OAK4 capture flow and emit production receipt metadata.
2. Wire deployment output into the backend and add automated Flare anchoring.
3. Teach the verifier to read contract state directly from Flare and compare it to the receipt.
4. Add tests, linting, and CI polish once the functional flow is stable.
