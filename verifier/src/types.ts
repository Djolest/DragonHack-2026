export interface ReceiptEmbeddedProofSummary {
  overall_status?: string;
  status_reason?: string;
  frames_processed?: number;
  recorded_frames?: number;
  recorded_duration_seconds?: number;
  passed_challenges?: number;
  failed_challenges?: number;
  [key: string]: unknown;
}

export interface ReceiptMetadata {
  proof_summary?: ReceiptEmbeddedProofSummary;
  [key: string]: unknown;
}

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
  metadata: ReceiptMetadata;
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

export interface AnchorResult {
  receipt_id: string;
  anchored: boolean;
  tx_hash: string;
  tx_url: string;
  chain_id: number;
}

export interface BackendHealth {
  status: string;
  service: string;
  environment: string;
  storedReceipts: number;
  anchoringEnabled: boolean;
  anchorOnIngest: boolean;
  anchoringMode: "manual" | "automatic";
  manualAnchorAvailable: boolean;
}

export interface TransactionProofResult {
  tx_hash: string;
  proof_type: "anchor_contract" | "legacy_signed_payload";
  decoded: boolean;
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

export interface CaptureSessionArtifacts {
  session_directory: string;
  rgb_video_relative_path: string | null;
  proof_relative_path: string | null;
  receipt_relative_path: string | null;
  rgb_video_uri: string | null;
  proof_uri: string | null;
  receipt_uri: string | null;
}

export interface CaptureSceneStats {
  frame_index: number;
  valid_depth_ratio: number;
  too_close_pixel_ratio: number;
  analyzable: boolean;
  plane_fit_rms_mm: number | null;
  depth_spread_mm: number | null;
}

export interface CaptureChallengeSnapshot {
  challenge_id: number;
  state: string;
  prompt: string;
  roi: {
    x0: number;
    y0: number;
    x1: number;
    y1: number;
  } | null;
  issued_at_seconds: number | null;
  elapsed_seconds: number;
  timeout_seconds: number;
  baseline_depth_mm: number | null;
  max_forward_motion_mm: number;
  valid_frames: number;
  progress_frames: number;
  motion_duration_seconds: number;
  close_reason: string | null;
}

export interface CaptureLiveState {
  frame_index: number;
  elapsed_seconds: number;
  workflow_stage: string;
  workflow_progress_frames: number;
  recording_state: string;
  recording_pause_reason: string | null;
  recorded_frames: number;
  recorded_duration_seconds: number;
  prompt: string;
  warning: string | null;
  scene_stats: CaptureSceneStats;
  plane_like_ratio: number | null;
  median_depth_spread_mm: number | null;
  too_close_frame_ratio: number;
  analyzable_frames: number;
  challenges_issued: number;
  challenges_passed: number;
  challenges_failed: number;
  current_challenge: CaptureChallengeSnapshot | null;
  next_challenge_eta_seconds: number | null;
}

export interface CaptureDeviceInfo {
  name: string;
  device_id: string;
  state: string;
  platform: string;
  product_name: string | null;
  board_name: string | null;
  board_revision: string | null;
  connected_sockets: string[];
  camera_sensors: Record<string, string>;
  usb_speed: string | null;
}

export interface CaptureReceiptWorkflowResult {
  status: string;
  reason?: string;
  error?: string;
  receipt_id?: string;
  receipt_hash?: string;
  asset_hash?: string;
  signer_address?: string;
  submitted_to_backend?: boolean;
  anchored?: boolean;
  receipt_relative_path?: string | null;
  receipt_uri?: string | null;
  anchor_tx_hash?: string | null;
  anchor_tx_url?: string | null;
  backend_receipt_hash?: string | null;
  submission_error?: string;
}

export interface CaptureProofSummary {
  overall_status?: string;
  frames_processed?: number;
  recorded_frames?: number;
  recorded_duration_seconds?: number;
  passed_challenges?: number;
  failed_challenges?: number;
  receipt_workflow?: CaptureReceiptWorkflowResult;
  [key: string]: unknown;
}

export interface StartCaptureSessionRequest {
  asset_id: string;
  operator_id?: string | null;
  notes?: string | null;
  tags: string[];
  simulate?: boolean | null;
}

export interface CaptureSessionStatus {
  session_id: string;
  asset_id: string;
  operator_id: string | null;
  notes: string | null;
  tags: string[];
  simulate: boolean;
  state: string;
  error: string | null;
  started_at: string;
  stopped_at: string | null;
  device_info: CaptureDeviceInfo | null;
  live_state: CaptureLiveState | null;
  artifacts: CaptureSessionArtifacts | null;
  proof_summary: CaptureProofSummary | null;
}

export interface StopCaptureSessionResponse {
  session: CaptureSessionStatus;
}
