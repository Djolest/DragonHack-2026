import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent
} from "react";

import { parseReceiptEnvelope } from "../lib/receipt";
import type {
  BackendHealth,
  ReceiptEmbeddedProofSummary,
  ReceiptRecord,
  SignedReceiptEnvelope,
  TransactionProofResult,
  VerificationResult,
  VerifiedReceipt
} from "../types";

type QrDetectionSource = HTMLVideoElement | ImageBitmap;

interface DetectedQrCode {
  rawValue?: string;
}

interface QrDetectorLike {
  detect(source: QrDetectionSource): Promise<DetectedQrCode[]>;
}

type QrDetectorConstructor = new (options?: { formats?: string[] }) => QrDetectorLike;

function statusLabel(value: boolean | null | undefined): string {
  if (value === true) {
    return "yes";
  }
  if (value === false) {
    return "no";
  }
  return "n/a";
}

function clipMiddle(value: string | null | undefined, edge = 12): string {
  if (!value) {
    return "n/a";
  }
  if (value.length <= edge * 2 + 3) {
    return value;
  }
  return `${value.slice(0, edge)}...${value.slice(-edge)}`;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function createQrDetector(): QrDetectorLike | null {
  const detectorConstructor = (
    globalThis as typeof globalThis & { BarcodeDetector?: QrDetectorConstructor }
  ).BarcodeDetector;
  if (!detectorConstructor) {
    return null;
  }
  return new detectorConstructor({ formats: ["qr_code"] });
}

function normalizeTxHashCandidate(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const normalized = value.startsWith("0x") ? value : `0x${value}`;
  return /^0x[a-fA-F0-9]{64}$/.test(normalized) ? normalized : null;
}

function extractTransactionHash(value: string): string | null {
  const directMatch = value.match(/\b0x[a-fA-F0-9]{64}\b/);
  if (directMatch) {
    return directMatch[0];
  }

  try {
    const url = new URL(value);
    const segments = url.pathname.split("/").filter(Boolean);
    const lastSegment = segments.at(-1) ?? null;
    if (segments.includes("tx") || segments.includes("transactions")) {
      return normalizeTxHashCandidate(lastSegment);
    }
  } catch {
    return normalizeTxHashCandidate(value.trim());
  }

  return null;
}

function extractReceiptIdFromUrl(value: string): string | null {
  try {
    const url = new URL(value);
    const segments = url.pathname.split("/").filter(Boolean);
    const receiptSegmentIndex = segments.lastIndexOf("receipts");
    if (receiptSegmentIndex !== -1 && segments[receiptSegmentIndex + 1]) {
      return decodeURIComponent(segments[receiptSegmentIndex + 1]);
    }
  } catch {
    return null;
  }

  return null;
}

function getReceiptProofSummary(
  receipt: SignedReceiptEnvelope | null
): ReceiptEmbeddedProofSummary | null {
  const proofSummary = receipt?.payload.metadata.proof_summary;
  if (!proofSummary || typeof proofSummary !== "object" || Array.isArray(proofSummary)) {
    return null;
  }
  return proofSummary;
}

function formatProofSummaryValue(label: string, value: unknown): string {
  if (typeof value === "number") {
    if (label === "Duration" || label === "Recorded Duration") {
      return `${value.toFixed(1)} s`;
    }
    return `${value}`;
  }
  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }
  return "n/a";
}

interface VerifyTabProps {
  receiptId: string;
  receiptText: string;
  transactionHash: string;
  selectedVideo: File | null;
  selectedVideoHash: string | null;
  activeReceipt: SignedReceiptEnvelope | null;
  record: ReceiptRecord | null;
  verification: VerifiedReceipt | null;
  backendVerification: VerificationResult | null;
  backendHealth: BackendHealth | null;
  transactionProof: TransactionProofResult | null;
  activeAction: "transaction" | "fetch" | "analyze" | "anchor" | null;
  error: string | null;
  signatureHealthy: boolean;
  canAnchorNow: boolean;
  decodedTransactionText: string | null;
  canonicalMessage: string | null;
  onReceiptIdChange: (value: string) => void;
  onReceiptTextChange: (value: string) => void;
  onTransactionHashChange: (value: string) => void;
  onVideoChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onFetchSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onAnalyzeSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onAnchorNow: () => void;
  onTransactionSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onOpenProofCard: () => void;
}

export function VerifyTab({
  receiptId,
  receiptText,
  transactionHash,
  selectedVideo,
  selectedVideoHash,
  activeReceipt,
  record,
  verification,
  backendVerification,
  backendHealth,
  transactionProof,
  activeAction,
  error,
  signatureHealthy,
  canAnchorNow,
  decodedTransactionText,
  canonicalMessage,
  onReceiptIdChange,
  onReceiptTextChange,
  onTransactionHashChange,
  onVideoChange,
  onFetchSubmit,
  onAnalyzeSubmit,
  onAnchorNow,
  onTransactionSubmit,
  onOpenProofCard
}: VerifyTabProps) {
  const [qrFeedback, setQrFeedback] = useState<string | null>(null);
  const [isQrScannerOpen, setIsQrScannerOpen] = useState(false);
  const qrVideoRef = useRef<HTMLVideoElement | null>(null);
  const qrImageInputRef = useRef<HTMLInputElement | null>(null);

  const proofSummary = getReceiptProofSummary(activeReceipt);
  const signatureStatus = verification ? signatureHealthy : null;
  const txDecoded = transactionProof?.decoded ?? null;
  const txRecordFound = transactionProof?.record_found ?? null;
  const txRecordConsistent = transactionProof?.record_consistent ?? null;
  const txAssetHashMatches = transactionProof?.asset_hash_matches ?? null;

  const proofSummaryItems = [
    { label: "Overall Status", value: proofSummary?.overall_status },
    { label: "Frames Processed", value: proofSummary?.frames_processed },
    { label: "Recorded Frames", value: proofSummary?.recorded_frames },
    { label: "Recorded Duration", value: proofSummary?.recorded_duration_seconds },
    { label: "Passed Challenges", value: proofSummary?.passed_challenges },
    { label: "Failed Challenges", value: proofSummary?.failed_challenges }
  ].filter((item) => item.value !== undefined);

  function applyScannedPayload(rawValue: string) {
    const trimmed = rawValue.trim();
    if (!trimmed) {
      throw new Error("QR payload was empty.");
    }

    const txHash = extractTransactionHash(trimmed);
    if (txHash) {
      onTransactionHashChange(txHash);
      setQrFeedback("Transaction hash loaded from QR.");
      return;
    }

    try {
      const parsed = parseReceiptEnvelope(trimmed);
      onReceiptTextChange(JSON.stringify(parsed, null, 2));
      onReceiptIdChange(parsed.payload.receipt_id);
      setQrFeedback("Receipt envelope loaded from QR.");
      return;
    } catch {
      const receiptIdFromUrl = extractReceiptIdFromUrl(trimmed);
      if (receiptIdFromUrl) {
        onReceiptIdChange(receiptIdFromUrl);
        setQrFeedback("Receipt ID loaded from QR.");
        return;
      }
    }

    onReceiptIdChange(trimmed);
    setQrFeedback("QR payload loaded as a receipt ID.");
  }

  function handleOpenQrScanner() {
    setQrFeedback(null);
    if (!createQrDetector()) {
      setQrFeedback("Live QR scanning is not supported in this browser. Use the QR image upload fallback.");
      return;
    }
    setIsQrScannerOpen(true);
  }

  async function handleQrImageChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    event.target.value = "";
    if (!file) {
      return;
    }

    const detector = createQrDetector();
    if (!detector) {
      setQrFeedback("QR detection is not supported in this browser. Paste the receipt or tx manually.");
      return;
    }

    try {
      const bitmap = await createImageBitmap(file);
      try {
        const detections = await detector.detect(bitmap);
        const scannedValue = detections.find((entry) => entry.rawValue?.trim())?.rawValue;
        if (!scannedValue) {
          throw new Error("No QR code was found in the uploaded image.");
        }
        applyScannedPayload(scannedValue);
      } finally {
        bitmap.close();
      }
    } catch (caughtError) {
      setQrFeedback(
        caughtError instanceof Error
          ? caughtError.message
          : "Failed to read the QR image."
      );
    }
  }

  useEffect(() => {
    if (!isQrScannerOpen) {
      return undefined;
    }

    const detector = createQrDetector();
    if (!detector) {
      setQrFeedback("Live QR scanning is not supported in this browser. Use the QR image upload fallback.");
      setIsQrScannerOpen(false);
      return undefined;
    }
    const liveDetector = detector;

    let cancelled = false;
    let stream: MediaStream | null = null;
    let detectIntervalId: number | null = null;
    let detectionInFlight = false;

    async function startScanner() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } },
          audio: false
        });

        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        const video = qrVideoRef.current;
        if (!video) {
          return;
        }

        video.srcObject = stream;
        await video.play();
        setQrFeedback("Point the camera at a receipt or tx QR code.");

        detectIntervalId = window.setInterval(async () => {
          if (cancelled || detectionInFlight || !video || video.readyState < 2) {
            return;
          }

          detectionInFlight = true;
          try {
            const detections = await liveDetector.detect(video);
            const scannedValue = detections.find((entry) => entry.rawValue?.trim())?.rawValue;
            if (scannedValue) {
              applyScannedPayload(scannedValue);
              setIsQrScannerOpen(false);
            }
          } catch {
            return;
          } finally {
            detectionInFlight = false;
          }
        }, 320);
      } catch (caughtError) {
        setQrFeedback(
          caughtError instanceof Error
            ? caughtError.message
            : "Could not open the camera for QR scanning."
        );
        setIsQrScannerOpen(false);
      }
    }

    void startScanner();

    return () => {
      cancelled = true;
      if (detectIntervalId !== null) {
        window.clearInterval(detectIntervalId);
      }
      const video = qrVideoRef.current;
      if (video) {
        video.pause();
        video.srcObject = null;
      }
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
    };
  }, [isQrScannerOpen, onReceiptIdChange, onReceiptTextChange, onTransactionHashChange]);

  return (
    <div className="tab-stack">
      <form className="glass-panel panel-surface verify-shell" onSubmit={onTransactionSubmit}>
        <div className="verify-shell-stage">
          <div className="verify-stage-window">
            <div className="verify-stage-overlay" />
            <div className="verify-stage-copy">
              <p className="section-kicker">Verify</p>
              <h3>Video provenance without uploads</h3>
              <p>
                Match a local video against the Flare proof while keeping the existing browser-side
                SHA-256 hashing and receipt signature checks intact.
              </p>
            </div>

            <label className="field-shell file-shell">
              <span>Recorded video</span>
              <input type="file" accept="video/*" onChange={onVideoChange} />
            </label>

            {selectedVideo ? (
              <div className="selected-file-card">
                <strong>{selectedVideo.name}</strong>
                <span>{formatFileSize(selectedVideo.size)}</span>
                <span>
                  {selectedVideoHash ? clipMiddle(selectedVideoHash, 14) : "SHA-256 pending"}
                </span>
              </div>
            ) : (
              <p className="helper-copy">
                Pick a local video to compute the browser-side SHA-256 hash and compare it to the
                decoded transaction proof.
              </p>
            )}
          </div>
        </div>

        <div className="verify-shell-controls">
          <div className="panel-heading">
            <p className="section-kicker">Transaction proof</p>
            <h3>Verify tx + local video</h3>
          </div>

          <label className="field-shell">
            <span>Transaction hash</span>
            <input
              value={transactionHash}
              onChange={(event) => onTransactionHashChange(event.target.value)}
              placeholder="0x..."
            />
          </label>

          <button
            type="submit"
            className="primary-button"
            disabled={activeAction !== null || transactionHash.trim().length === 0}
          >
            {activeAction === "transaction" ? "Checking Flare..." : "Verify"}
          </button>

          <div className="status-row">
            <span className={`status-pill${txDecoded === true ? " is-good" : ""}`}>
              Decoded {statusLabel(txDecoded)}
            </span>
            <span className={`status-pill${txRecordFound === true ? " is-good" : ""}`}>
              Trusted record {statusLabel(txRecordFound)}
            </span>
            <span className={`status-pill${txRecordConsistent === true ? " is-good" : ""}`}>
              Consistent {statusLabel(txRecordConsistent)}
            </span>
            <span className={`status-pill${txAssetHashMatches === true ? " is-good" : ""}`}>
              Local file match {statusLabel(txAssetHashMatches)}
            </span>
          </div>

          <div className="verify-tool-row">
            <button type="button" className="secondary-button" onClick={handleOpenQrScanner}>
              Scan QR
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => qrImageInputRef.current?.click()}
            >
              Upload QR image
            </button>
            <button type="button" className="secondary-button" onClick={onOpenProofCard}>
              Share proof card
            </button>
            {transactionProof?.explorer_url ? (
              <a
                className="secondary-link"
                href={transactionProof.explorer_url}
                target="_blank"
                rel="noreferrer"
              >
                Open tx
              </a>
            ) : (
              <span className="secondary-link is-disabled">Awaiting tx</span>
            )}
          </div>

          <input
            ref={qrImageInputRef}
            type="file"
            accept="image/*"
            className="visually-hidden"
            onChange={handleQrImageChange}
          />

          {qrFeedback ? <p className="qr-status-banner">{qrFeedback}</p> : null}
        </div>
      </form>

      <section className="dual-panel-grid">
        <form className="glass-panel panel-surface" onSubmit={onFetchSubmit}>
          <div className="panel-heading">
            <p className="section-kicker">Fetch receipt</p>
            <h3>Load backend receipt data</h3>
            <p>Reuse the current backend fetch and verification endpoints without changing them.</p>
          </div>

          <label className="field-shell">
            <span>Receipt ID</span>
            <input
              value={receiptId}
              onChange={(event) => onReceiptIdChange(event.target.value)}
              placeholder="oakproof-..."
            />
          </label>

          <button
            type="submit"
            className="primary-button"
            disabled={activeAction !== null || receiptId.trim().length === 0}
          >
            {activeAction === "fetch" ? "Loading receipt..." : "Fetch receipt"}
          </button>
        </form>

        <form className="glass-panel panel-surface" onSubmit={onAnalyzeSubmit}>
          <div className="panel-heading">
            <p className="section-kicker">Paste receipt JSON</p>
            <h3>Verify envelopes in-browser</h3>
            <p>
              Parse the signed receipt payload locally, rebuild the canonical message, and recover
              the signer directly in the browser.
            </p>
          </div>

          <label className="field-shell">
            <span>Receipt envelope</span>
            <textarea
              rows={14}
              value={receiptText}
              onChange={(event) => onReceiptTextChange(event.target.value)}
              placeholder='{"payload": {...}, "signature": {...}}'
            />
          </label>

          <button
            type="submit"
            className="primary-button"
            disabled={activeAction !== null || receiptText.trim().length === 0}
          >
            {activeAction === "analyze" ? "Verifying receipt..." : "Verify pasted receipt"}
          </button>
        </form>
      </section>

      {error ? <section className="error-banner">{error}</section> : null}

      <section className="result-grid">
        <article className="glass-panel panel-surface result-card">
          <div className="panel-heading">
            <p className="section-kicker">Verification order</p>
            <h3>Demo verdict</h3>
          </div>

          <dl className="info-list verification-flow-list">
            <div>
              <dt>Signature valid</dt>
              <dd>{statusLabel(signatureStatus)}</dd>
            </div>
            <div>
              <dt>Signer recovered</dt>
              <dd>{clipMiddle(verification?.recoveredAddress, 14)}</dd>
            </div>
            <div>
              <dt>TX decoded</dt>
              <dd>{statusLabel(txDecoded)}</dd>
            </div>
            <div>
              <dt>Trusted record found</dt>
              <dd>{statusLabel(txRecordFound)}</dd>
            </div>
            <div>
              <dt>Record consistent</dt>
              <dd>{statusLabel(txRecordConsistent)}</dd>
            </div>
            <div>
              <dt>Local file matches tx</dt>
              <dd>{statusLabel(txAssetHashMatches)}</dd>
            </div>
          </dl>
        </article>

        <article className="glass-panel panel-surface result-card">
          <div className="panel-heading">
            <p className="section-kicker">Embedded summary</p>
            <h3>Receipt proof summary</h3>
          </div>

          {proofSummary && proofSummaryItems.length > 0 ? (
            <>
              <div className="proof-summary-grid">
                {proofSummaryItems.map((item) => (
                  <div key={item.label} className="proof-summary-item">
                    <span>{item.label}</span>
                    <strong>{formatProofSummaryValue(item.label, item.value)}</strong>
                  </div>
                ))}
              </div>
              {typeof proofSummary.status_reason === "string" && proofSummary.status_reason ? (
                <p className="proof-summary-note">{proofSummary.status_reason}</p>
              ) : null}
            </>
          ) : (
            <p className="helper-copy">
              No compact `receipt.payload.metadata.proof_summary` block is present in the active
              receipt yet.
            </p>
          )}
        </article>

        <article className="glass-panel panel-surface result-card">
          <div className="panel-heading">
            <p className="section-kicker">Chain + backend</p>
            <h3>Supporting details</h3>
          </div>

          <dl className="info-list">
            <div>
              <dt>Proof type</dt>
              <dd>{transactionProof?.proof_type ?? "n/a"}</dd>
            </div>
            <div>
              <dt>Receipt ID</dt>
              <dd>{clipMiddle(activeReceipt?.payload.receipt_id ?? record?.receipt_id ?? receiptId, 14)}</dd>
            </div>
            <div>
              <dt>Backend anchored</dt>
              <dd>{statusLabel(backendVerification?.anchored)}</dd>
            </div>
            <div>
              <dt>Anchoring mode</dt>
              <dd>{backendHealth?.anchoringMode ?? "n/a"}</dd>
            </div>
            <div>
              <dt>On-chain asset hash</dt>
              <dd>{clipMiddle(transactionProof?.asset_hash, 14)}</dd>
            </div>
            <div>
              <dt>Storage URI</dt>
              <dd>
                {clipMiddle(
                  activeReceipt?.payload.storage_uri ?? record?.receipt.payload.storage_uri ?? transactionProof?.storage_uri,
                  14
                )}
              </dd>
            </div>
          </dl>

          <div className="action-row">
            {canAnchorNow ? (
              <button
                type="button"
                className="secondary-button"
                onClick={onAnchorNow}
                disabled={activeAction !== null}
              >
                {activeAction === "anchor" ? "Anchoring..." : "Anchor now"}
              </button>
            ) : (
              <span className="secondary-link is-disabled">
                {backendVerification?.anchored === true || record?.anchored === true
                  ? "Already anchored"
                  : backendHealth?.anchoringMode === "manual"
                    ? "Manual anchor unavailable"
                    : "Auto or unknown mode"}
              </span>
            )}
          </div>
        </article>
      </section>

      <section className="detail-grid">
        {decodedTransactionText ? (
          <article className="glass-panel panel-surface detail-card">
            <div className="panel-heading">
              <p className="section-kicker">Decoded payload</p>
              <h3>Normalized chain data</h3>
            </div>
            <pre>{decodedTransactionText}</pre>
          </article>
        ) : null}

        {canonicalMessage ? (
          <article className="glass-panel panel-surface detail-card">
            <div className="panel-heading">
              <p className="section-kicker">Canonical message</p>
              <h3>Exact signed payload</h3>
            </div>
            <pre>{canonicalMessage}</pre>
          </article>
        ) : null}
      </section>

      {isQrScannerOpen ? (
        <div className="qr-scanner-backdrop" onClick={() => setIsQrScannerOpen(false)}>
          <div
            className="glass-panel qr-scanner-panel"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <p className="section-kicker">QR scan</p>
                <h3>Scan a receipt or tx code</h3>
                <p className="modal-copy">
                  Point the camera at a QR code containing a transaction hash, receipt ID, or full
                  receipt envelope.
                </p>
              </div>
              <button
                type="button"
                className="close-button"
                onClick={() => setIsQrScannerOpen(false)}
              >
                Close
              </button>
            </div>

            <div className="qr-scanner-video-shell">
              <video ref={qrVideoRef} className="qr-scanner-video" playsInline muted autoPlay />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
