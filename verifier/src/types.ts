export interface ReceiptPayload {
  schema_version: string;
  receipt_id: string;
  capture_id: string;
  station_id: string;
  asset_id: string;
  captured_at: string;
  asset_hash: string;
  storage_uri: string;
  media_type: string;
  metadata: Record<string, unknown>;
}

export interface ReceiptSignature {
  scheme: "eip191";
  signer_address: string;
  signature: string;
}

export interface SignedReceiptEnvelope {
  payload: ReceiptPayload;
  signature: ReceiptSignature;
}

export interface ReceiptRecord {
  receipt_id: string;
  receipt: SignedReceiptEnvelope;
  receipt_hash: string;
  signature_valid: boolean;
  signer_address: string;
  anchored: boolean;
  anchor_tx_hash: string | null;
  anchor_tx_url: string | null;
  anchor_chain_id: number | null;
  created_at: string;
  updated_at: string;
  stored_at: string;
}

export interface VerificationResult {
  receipt_id: string;
  signature_valid: boolean;
  anchored: boolean;
  signer_address: string;
  receipt_hash: string;
  anchor_tx_hash: string | null;
  anchor_tx_url: string | null;
}

export interface TransactionProofResult {
  tx_hash: string;
  proof_type: "anchor_contract" | "legacy_signed_payload";
  proof_valid: boolean;
  chain_id: number | null;
  block_number: number | null;
  from_address: string | null;
  to_address: string | null;
  explorer_url: string | null;
  receipt_id: string | null;
  receipt_id_hash: string | null;
  receipt_hash: string | null;
  asset_hash: string | null;
  storage_uri: string | null;
  signer_address: string | null;
  submitter_address: string | null;
  signature: string | null;
  public_key: string | null;
  signature_valid: boolean | null;
  public_key_matches: boolean | null;
  record_found: boolean;
  record_consistent: boolean | null;
  provided_asset_hash: string | null;
  asset_hash_matches: boolean | null;
}

export interface VerifiedReceipt {
  canonicalMessage: string;
  recoveredAddress: string;
  payloadHash: string;
  signatureValid: boolean;
}
