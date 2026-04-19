# Verifier Frontend

The verifier is a browser-first UI for validating OAKProof receipts. It can fetch a receipt record from the backend, verify a pasted receipt JSON payload directly in the browser, or hash a local video and compare it to the asset digest committed inside a Flare transaction.

## Run

```bash
npm install
npm run dev
```

## Notes

- The verifier trusts the receipt schema but independently checks the EIP-191 signature and SHA-256 payload hash.
- The transaction panel works with both the current anchor-contract tx format and the earlier `proof:{...}` payload transactions.
- `TODO(next):` add ABI-powered direct chain reads so the browser can validate contract storage without depending on the backend verification endpoint.
