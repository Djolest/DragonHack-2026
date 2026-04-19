# Demo Runbook

## Start

```bash
npm run demo
```

Assumes `backend/.venv` and `capture/.venv` already exist and have their local dependencies installed.

## Operator Flow

1. Open the verifier app at `http://127.0.0.1:5173`.
2. In `Record`, start a station session, watch the preview, and stop once the proof summary looks good.
3. Let the station produce the signed receipt and local artifacts.
4. Switch to `Verify`, fetch the receipt by ID, and confirm the signer and embedded proof summary.
5. If there is a tx hash, verify the transaction against the local video file.
6. Open the proof card when you need to share the tx hash, explorer link, or receipt ID by QR-style handoff.

## If Anchoring Is Slow

- Keep the demo honest: show the receipt as signed and stored first, then explain that anchoring is asynchronous from the operator’s point of view.
- If the backend is in manual mode, use `Anchor now` from the Verify tab only when you are ready to wait on chain.
- If chain confirmation is lagging, continue the demo with receipt verification and local-file hashing, then refresh the tx step once the backend has the anchored record.

## Honest Limitations

- The browser verifies signatures and hashes locally, but it does not make a decoded transaction trustworthy by itself.
- The capture preview is HTTP-polled JPEG, not a low-latency streaming stack.
- QR scanning depends on browser support for `BarcodeDetector`; image upload is the fallback.
- The demo is still local-first: artifacts and receipt records are stored on disk on the demo machine.
