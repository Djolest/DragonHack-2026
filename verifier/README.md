# Verifier Frontend

The verifier is a browser-first UI for validating OAKProof receipts. It can either fetch a receipt record from the backend or verify a pasted receipt JSON payload directly in the browser by recomputing the signed message and recovering the signer address.

## Run

```bash
npm install
npm run dev
```

## Notes

- The verifier trusts the receipt schema but independently checks the EIP-191 signature and SHA-256 payload hash.
- `TODO(next):` add ABI-powered direct chain reads so the browser can validate contract storage without depending on the backend verification endpoint.
