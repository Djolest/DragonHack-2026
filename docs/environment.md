# Environment Variables

## Capture

- `CAPTURE_APP_NAME`: FastAPI application name.
- `CAPTURE_APP_ENV`: environment label such as `development`.
- `CAPTURE_HOST`: bind host for local runs.
- `CAPTURE_PORT`: bind port for local runs.
- `CAPTURE_LOG_LEVEL`: logging verbosity.
- `CAPTURE_STORAGE_ROOT`: local root for captured files and signed receipt JSON.
- `CAPTURE_PUBLIC_BASE_URL`: public base URL used when generating `storage_uri`.
- `CAPTURE_BACKEND_BASE_URL`: backend API base URL for auto-submission.
- `CAPTURE_CORS_ALLOW_ORIGINS`: comma-separated allowed origins or `*`.
- `CAPTURE_STATION_ID`: logical station identifier embedded in every receipt.
- `CAPTURE_STATION_SIGNER_PRIVATE_KEY`: EVM private key used to sign receipts.
- `CAPTURE_SIMULATE`: `true` to use the built-in simulated SVG capture path.
- `CAPTURE_OAK_DEVICE_ID`: optional DepthAI device ID for a fixed OAK unit.
- `CAPTURE_AUTO_SUBMIT_TO_BACKEND`: auto-POST each new receipt to the backend.
- `CAPTURE_RECEIPT_NAMESPACE`: prefix used for generated receipt IDs.
- `CAPTURE_REQUEST_TIMEOUT_SECONDS`: timeout used for backend submission.

## Backend

- `BACKEND_APP_NAME`: FastAPI application name.
- `BACKEND_APP_ENV`: environment label such as `development`.
- `BACKEND_HOST`: bind host for local runs.
- `BACKEND_PORT`: bind port for local runs.
- `BACKEND_LOG_LEVEL`: logging verbosity.
- `BACKEND_STORAGE_ROOT`: local root for receipt records.
- `BACKEND_CORS_ALLOW_ORIGINS`: comma-separated frontend origins or `*`.
- `BACKEND_CAPTURE_SIGNER_ALLOWLIST`: comma-separated trusted station signer addresses.
- `BACKEND_FLARE_RPC_URL`: Flare Coston2 RPC endpoint.
- `BACKEND_FLARE_CHAIN_ID`: Flare Coston2 chain ID, currently `114`.
- `BACKEND_FLARE_EXPLORER_BASE_URL`: explorer base URL for transaction links.
- `BACKEND_ANCHOR_CONTRACT_ADDRESS`: deployed `OAKProofAnchor` contract address.
- `BACKEND_ANCHOR_PRIVATE_KEY`: backend wallet that submits anchor transactions.
- `BACKEND_ANCHOR_GAS_LIMIT`: gas limit used for anchor transactions.
- `BACKEND_ANCHOR_TIMEOUT_SECONDS`: timeout when waiting for a mined anchor transaction.

## Contracts

- `COSTON2_RPC_URL`: Flare Coston2 RPC endpoint for Hardhat.
- `DEPLOYER_PRIVATE_KEY`: deployer account private key.

## Verifier

- `VITE_BACKEND_URL`: backend base URL used by the browser.
- `VITE_FLARE_EXPLORER_BASE_URL`: explorer base URL for future direct-chain UI work.
