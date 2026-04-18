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

export interface VerifiedReceipt {
  canonicalMessage: string;
  recoveredAddress: string;
  payloadHash: string;
  signatureValid: boolean;
}
