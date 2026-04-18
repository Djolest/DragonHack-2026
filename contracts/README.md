# Contracts

The contracts package contains the Flare-facing anchor contract for OAKProof. The MVP contract stores the receipt digest, the asset digest, and the storage URI associated with a proof receipt.

## Run

```bash
npm install
npm run compile
npm run test
npm run deploy:coston2
```

## Deployment Output

Deployments are written to `contracts/deployments/{network}.json`.

## Notes

- After deployment, copy the emitted contract address into `backend/.env` as `BACKEND_ANCHOR_CONTRACT_ADDRESS`.
- `TODO(next):` emit richer metadata or add role-based access control once the MVP anchor flow is validated.
