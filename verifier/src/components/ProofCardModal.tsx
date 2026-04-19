import { useEffect, useState } from "react";

import type {
  BackendHealth,
  SignedReceiptEnvelope,
  ReceiptRecord,
  TransactionProofResult,
  VerificationResult,
  VerifiedReceipt
} from "../types";

function firstDefined(...values: Array<string | null | undefined>): string | null {
  for (const value of values) {
    if (value) {
      return value;
    }
  }
  return null;
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

function isUrl(value: string): boolean {
  return value.startsWith("http://") || value.startsWith("https://");
}

function buildPseudoMatrix(value: string, size = 21): boolean[] {
  let seed = 2166136261;
  for (const character of value) {
    seed ^= character.charCodeAt(0);
    seed = Math.imul(seed, 16777619) >>> 0;
  }

  function inFinderPattern(x: number, y: number): boolean | null {
    const inTopLeft = x < 7 && y < 7;
    const inTopRight = x >= size - 7 && y < 7;
    const inBottomLeft = x < 7 && y >= size - 7;
    if (!inTopLeft && !inTopRight && !inBottomLeft) {
      return null;
    }

    const localX = inTopRight ? x - (size - 7) : x;
    const localY = inBottomLeft ? y - (size - 7) : y;
    const outer = localX === 0 || localX === 6 || localY === 0 || localY === 6;
    const inner = localX >= 2 && localX <= 4 && localY >= 2 && localY <= 4;
    return outer || inner;
  }

  return Array.from({ length: size * size }, (_, index) => {
    const x = index % size;
    const y = Math.floor(index / size);
    const finder = inFinderPattern(x, y);
    if (finder !== null) {
      return finder;
    }

    seed ^= seed << 13;
    seed ^= seed >>> 17;
    seed ^= seed << 5;
    seed >>>= 0;
    return ((seed >>> ((x + y) % 16)) & 1) === 1;
  });
}

interface ModalFrameProps {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
}

function ModalFrame({ isOpen, onClose, children }: ModalFrameProps) {
  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="glass-panel modal-panel" onClick={(event) => event.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}

interface ProofCardModalProps {
  isOpen: boolean;
  onClose: () => void;
  receiptId: string;
  activeReceipt: SignedReceiptEnvelope | null;
  record: ReceiptRecord | null;
  verification: VerifiedReceipt | null;
  backendVerification: VerificationResult | null;
  backendHealth: BackendHealth | null;
  transactionProof: TransactionProofResult | null;
  selectedVideoHash: string | null;
}

interface QrTarget {
  id: string;
  label: string;
  value: string;
}

export function ProofCardModal({
  isOpen,
  onClose,
  receiptId,
  activeReceipt,
  record,
  verification,
  backendVerification,
  backendHealth,
  transactionProof,
  selectedVideoHash
}: ProofCardModalProps) {
  const targets: QrTarget[] = [
    firstDefined(
      transactionProof?.tx_hash,
      backendVerification?.anchor_tx_hash,
      record?.anchor_tx_hash
    )
      ? {
          id: "tx",
          label: "Transaction Hash",
          value:
            firstDefined(
              transactionProof?.tx_hash,
              backendVerification?.anchor_tx_hash,
              record?.anchor_tx_hash
            ) || ""
        }
      : null,
    receiptId || record?.receipt_id
      ? { id: "receipt", label: "Receipt ID", value: receiptId || record?.receipt_id || "" }
      : null,
    firstDefined(transactionProof?.explorer_url, backendVerification?.anchor_tx_url, record?.anchor_tx_url)
      ? {
          id: "explorer",
          label: "Explorer URL",
          value:
            firstDefined(
              transactionProof?.explorer_url,
              backendVerification?.anchor_tx_url,
              record?.anchor_tx_url
            ) || ""
        }
      : null,
    firstDefined(
      activeReceipt?.payload.storage_uri,
      record?.receipt.payload.storage_uri,
      transactionProof?.storage_uri
    )
      ? {
          id: "storage",
          label: "Storage URI",
          value:
            firstDefined(
              activeReceipt?.payload.storage_uri,
              record?.receipt.payload.storage_uri,
              transactionProof?.storage_uri
            ) || ""
        }
      : null
  ].filter((target): target is QrTarget => target !== null);

  const [selectedTargetId, setSelectedTargetId] = useState<string | null>(
    targets.find((target) => target.id === "tx")?.id ?? targets[0]?.id ?? null
  );
  const [copyLabel, setCopyLabel] = useState("Copy payload");

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    setSelectedTargetId(
      targets.find((target) => target.id === "tx")?.id ?? targets[0]?.id ?? null
    );
    setCopyLabel("Copy payload");
  }, [isOpen, receiptId, activeReceipt, record, backendVerification, transactionProof]);

  const selectedTarget =
    targets.find((target) => target.id === selectedTargetId) ?? targets[0] ?? null;
  const matrix = selectedTarget ? buildPseudoMatrix(selectedTarget.value) : [];
  const signatureStatus = verification
    ? verification.signatureValid === true &&
      verification.payloadHash === (record?.receipt_hash ?? verification.payloadHash)
    : null;

  function statusLabel(value: boolean | null | undefined): string {
    if (value === true) {
      return "yes";
    }
    if (value === false) {
      return "no";
    }
    return "n/a";
  }

  async function handleCopy() {
    if (!selectedTarget) {
      return;
    }

    try {
      await navigator.clipboard.writeText(selectedTarget.value);
      setCopyLabel("Copied");
      window.setTimeout(() => setCopyLabel("Copy payload"), 1400);
    } catch {
      setCopyLabel("Copy failed");
      window.setTimeout(() => setCopyLabel("Copy payload"), 1400);
    }
  }

  return (
    <ModalFrame isOpen={isOpen} onClose={onClose}>
      <div className="modal-header">
        <div>
          <p className="section-kicker">Proof card</p>
          <h3>Shared receipt snapshot</h3>
          <p className="modal-copy">
            A single modal for proof inspection, anchor links, and QR-oriented handoff actions.
          </p>
        </div>
        <button type="button" className="close-button" onClick={onClose}>
          Close
        </button>
      </div>

      <section className="modal-summary-grid">
        <article className="modal-summary-card">
          <span>Receipt</span>
          <strong>{clipMiddle(receiptId || record?.receipt_id, 14)}</strong>
        </article>
        <article className="modal-summary-card">
          <span>Signer</span>
          <strong>
            {clipMiddle(
              verification?.recoveredAddress ??
                backendVerification?.signer_address ??
                record?.signer_address ??
                transactionProof?.signer_address,
              12
            )}
          </strong>
        </article>
        <article className="modal-summary-card">
          <span>Video hash</span>
          <strong>{clipMiddle(selectedVideoHash ?? transactionProof?.asset_hash, 12)}</strong>
        </article>
        <article className="modal-summary-card">
          <span>Transaction</span>
          <strong>
            {clipMiddle(
              transactionProof?.tx_hash ??
                backendVerification?.anchor_tx_hash ??
                record?.anchor_tx_hash ??
                transactionProof?.explorer_url ??
                backendVerification?.anchor_tx_url ??
                record?.anchor_tx_url,
              12
            )}
          </strong>
        </article>
      </section>

      <section className="modal-body-grid">
        <article className="glass-panel modal-inner-card">
          <div className="panel-heading">
            <p className="section-kicker">Verification</p>
            <h3>Current state</h3>
          </div>

          <dl className="info-list">
            <div>
              <dt>Signature valid</dt>
              <dd>{statusLabel(signatureStatus)}</dd>
            </div>
            <div>
              <dt>Anchoring mode</dt>
              <dd>{backendHealth?.anchoringMode ?? "n/a"}</dd>
            </div>
            <div>
              <dt>Anchored</dt>
              <dd>{statusLabel(backendVerification?.anchored)}</dd>
            </div>
            <div>
              <dt>Transaction decoded</dt>
              <dd>{statusLabel(transactionProof?.decoded)}</dd>
            </div>
            <div>
              <dt>Record found for tx</dt>
              <dd>{statusLabel(transactionProof?.record_found)}</dd>
            </div>
            <div>
              <dt>Record consistent</dt>
              <dd>{statusLabel(transactionProof?.record_consistent)}</dd>
            </div>
            <div>
              <dt>Video hash match</dt>
              <dd>{statusLabel(transactionProof?.asset_hash_matches)}</dd>
            </div>
          </dl>
        </article>

        <article className="glass-panel modal-inner-card">
          <div className="panel-heading">
            <p className="section-kicker">QR actions</p>
            <h3>Select a proof payload</h3>
            <p className="helper-copy">
              Pick the payload you want to hand off, copy it, or open it directly when it is a
              link.
            </p>
          </div>

          <div className="qr-action-row">
            {targets.length > 0 ? (
              targets.map((target) => (
                <button
                  key={target.id}
                  type="button"
                  className={`qr-target-button${selectedTarget?.id === target.id ? " is-active" : ""}`}
                  onClick={() => setSelectedTargetId(target.id)}
                >
                  {target.label}
                </button>
              ))
            ) : (
              <span className="secondary-link is-disabled">No proof payload loaded yet</span>
            )}
          </div>

          {selectedTarget ? (
            <div className="qr-preview-shell">
              <div className="qr-grid" style={{ gridTemplateColumns: "repeat(21, 1fr)" }}>
                {matrix.map((cell, index) => (
                  <span key={index} className={`qr-cell${cell ? " is-filled" : ""}`} />
                ))}
              </div>

              <div className="qr-preview-meta">
                <strong>{selectedTarget.label}</strong>
                <code>{selectedTarget.value}</code>
                <p className="helper-copy">
                  This view highlights the chosen payload for QR export. Use the copied value with
                  your preferred QR encoder if you need a scan-ready code.
                </p>

                <div className="action-row">
                  <button type="button" className="secondary-button" onClick={handleCopy}>
                    {copyLabel}
                  </button>
                  {isUrl(selectedTarget.value) ? (
                    <a
                      className="secondary-link"
                      href={selectedTarget.value}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open link
                    </a>
                  ) : (
                    <span className="secondary-link is-disabled">Text payload</span>
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </article>
      </section>
    </ModalFrame>
  );
}
