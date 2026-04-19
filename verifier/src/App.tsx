import { ChangeEvent, FormEvent, startTransition, useEffect, useState } from "react";

import { AboutTab } from "./components/AboutTab";
import { ProofCardModal } from "./components/ProofCardModal";
import { RecordTab } from "./components/RecordTab";
import { VerifyTab } from "./components/VerifyTab";
import {
  anchorReceipt,
  fetchBackendHealth,
  fetchReceipt,
  fetchTransactionProof,
  fetchVerification
} from "./lib/api";
import { parseReceiptEnvelope, sha256FileHex, verifyReceiptEnvelope } from "./lib/receipt";
import type {
  BackendHealth,
  ReceiptRecord,
  SignedReceiptEnvelope,
  TransactionProofResult,
  VerificationResult,
  VerifiedReceipt
} from "./types";

const defaultBackendUrl = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";
const defaultCaptureUrl = import.meta.env.VITE_CAPTURE_URL ?? "http://127.0.0.1:8100";

type ActiveAction = "transaction" | "fetch" | "analyze" | "anchor" | null;
type TabId = "record" | "verify" | "about";

const tabCopy: Record<TabId, { eyebrow: string; title: string; description: string }> = {
  record: {
    eyebrow: "Station control",
    title: "Drive the OAK capture station from the same browser app.",
    description:
      "The Record tab now talks to the capture FastAPI service directly: start a session, watch annotated preview frames, and stop into proof and receipt outputs without leaving the web shell."
  },
  verify: {
    eyebrow: "Verification preserved",
    title: "Inspect receipts, compare local video hashes, and decode Flare proofs.",
    description:
      "The existing fetch, pasted-receipt, and transaction-plus-video verification paths are unchanged underneath the redesigned interface."
  },
  about: {
    eyebrow: "Architecture",
    title: "One browser app, two FastAPI services, and the same proof model.",
    description:
      "The UI is now organized as a single shell with shared state, while the receipt verification logic and typed proof records stay exactly where they already lived."
  }
};

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function firstDefined(...values: Array<string | null | undefined>): string | null {
  for (const value of values) {
    if (value) {
      return value;
    }
  }
  return null;
}

function clipMiddle(value: string | null | undefined, edge = 10): string {
  if (!value) {
    return "n/a";
  }
  if (value.length <= edge * 2 + 3) {
    return value;
  }
  return `${value.slice(0, edge)}...${value.slice(-edge)}`;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>("record");
  const [backendUrl, setBackendUrl] = useState(defaultBackendUrl);
  const [captureUrl, setCaptureUrl] = useState(defaultCaptureUrl);
  const [receiptId, setReceiptId] = useState("");
  const [receiptText, setReceiptText] = useState("");
  const [transactionHash, setTransactionHash] = useState("");
  const [selectedVideo, setSelectedVideo] = useState<File | null>(null);
  const [selectedVideoHash, setSelectedVideoHash] = useState<string | null>(null);
  const [activeReceipt, setActiveReceipt] = useState<SignedReceiptEnvelope | null>(null);
  const [record, setRecord] = useState<ReceiptRecord | null>(null);
  const [verification, setVerification] = useState<VerifiedReceipt | null>(null);
  const [backendVerification, setBackendVerification] = useState<VerificationResult | null>(null);
  const [backendHealth, setBackendHealth] = useState<BackendHealth | null>(null);
  const [transactionProof, setTransactionProof] = useState<TransactionProofResult | null>(null);
  const [activeAction, setActiveAction] = useState<ActiveAction>(null);
  const [error, setError] = useState<string | null>(null);
  const [isProofCardOpen, setIsProofCardOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setBackendHealth(null);

    void fetchBackendHealth(backendUrl)
      .then((nextHealth) => {
        if (!cancelled) {
          setBackendHealth(nextHealth);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBackendHealth(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [backendUrl]);

  async function runVerification(receipt: SignedReceiptEnvelope) {
    const localVerification = await verifyReceiptEnvelope(receipt);
    startTransition(() => {
      setVerification(localVerification);
    });
  }

  function shouldClearTransactionProof(nextReceiptId: string): boolean {
    if (!transactionProof) {
      return false;
    }

    const currentProofReceiptId =
      transactionProof.receipt_id ?? activeReceipt?.payload.receipt_id ?? record?.receipt_id ?? receiptId.trim();
    return currentProofReceiptId !== nextReceiptId;
  }

  function handleVideoChange(event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0] ?? null;
    setSelectedVideo(nextFile);
    setSelectedVideoHash(null);
    setTransactionProof(null);
  }

  async function handleTransactionLookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActiveTab("verify");
    setActiveAction("transaction");
    setError(null);

    try {
      let nextVideoHash = selectedVideoHash;
      if (selectedVideo && !nextVideoHash) {
        nextVideoHash = await sha256FileHex(selectedVideo);
        setSelectedVideoHash(nextVideoHash);
      }

      const nextTransactionProof = await fetchTransactionProof(
        backendUrl,
        transactionHash.trim(),
        nextVideoHash ?? undefined
      );
      startTransition(() => {
        setTransactionProof(nextTransactionProof);
      });

      if (!receiptId && nextTransactionProof.receipt_id) {
        setReceiptId(nextTransactionProof.receipt_id);
      }
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Failed to read the transaction from Flare."
      );
    } finally {
      setActiveAction(null);
    }
  }

  async function handleFetch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActiveTab("verify");
    setActiveAction("fetch");
    setError(null);

    try {
      const nextRecord = await fetchReceipt(backendUrl, receiptId.trim());
      if (shouldClearTransactionProof(nextRecord.receipt_id)) {
        setTransactionProof(null);
      }
      setRecord(nextRecord);
      setActiveReceipt(nextRecord.receipt);
      setReceiptText(prettyJson(nextRecord.receipt));
      await runVerification(nextRecord.receipt);

      const nextBackendVerification = await fetchVerification(
        backendUrl,
        nextRecord.receipt_id
      );
      startTransition(() => {
        setBackendVerification(nextBackendVerification);
      });
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : "Failed to fetch receipt record."
      );
    } finally {
      setActiveAction(null);
    }
  }

  async function handleAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActiveTab("verify");
    setActiveAction("analyze");
    setError(null);

    try {
      const parsed = parseReceiptEnvelope(receiptText);
      if (shouldClearTransactionProof(parsed.payload.receipt_id)) {
        setTransactionProof(null);
      }
      setRecord(null);
      setActiveReceipt(parsed);
      setReceiptId(parsed.payload.receipt_id);
      setBackendVerification(null);
      await runVerification(parsed);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : "Failed to parse or verify receipt."
      );
    } finally {
      setActiveAction(null);
    }
  }

  async function handleAnchorNow() {
    const targetReceiptId = record?.receipt_id ?? backendVerification?.receipt_id ?? receiptId.trim();
    if (!targetReceiptId) {
      return;
    }

    setActiveTab("verify");
    setActiveAction("anchor");
    setError(null);

    try {
      const anchorResult = await anchorReceipt(backendUrl, targetReceiptId);
      const [nextRecord, nextBackendVerification] = await Promise.all([
        fetchReceipt(backendUrl, targetReceiptId),
        fetchVerification(backendUrl, targetReceiptId)
      ]);
      setRecord(nextRecord);
      setActiveReceipt(nextRecord.receipt);
      setBackendVerification(nextBackendVerification);
      setTransactionHash(anchorResult.tx_hash);
      setTransactionProof(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error ? caughtError.message : "Failed to anchor the receipt."
      );
    } finally {
      setActiveAction(null);
    }
  }

  const signatureHealthy =
    Boolean(verification?.signatureValid) &&
    verification?.payloadHash === (record?.receipt_hash ?? verification?.payloadHash);
  const txRecordLinked =
    transactionProof?.record_found === true && transactionProof?.record_consistent === true;
  const txMatchHealthy = transactionProof?.asset_hash_matches === true;
  const canAnchorNow =
    backendHealth?.anchoringMode === "manual" &&
    backendHealth.manualAnchorAvailable === true &&
    (backendVerification?.anchored === false || record?.anchored === false) &&
    Boolean(record?.receipt_id ?? backendVerification?.receipt_id ?? receiptId.trim());
  const hasProofData = Boolean(
    receiptId ||
      receiptText.trim() ||
      record ||
      activeReceipt ||
      verification ||
      backendVerification ||
      transactionProof ||
      selectedVideoHash
  );

  const headline = tabCopy[activeTab];
  const currentExplorerUrl = firstDefined(
    transactionProof?.explorer_url,
    backendVerification?.anchor_tx_url,
    record?.anchor_tx_url
  );
  const currentStorageUri = firstDefined(
    activeReceipt?.payload.storage_uri,
    record?.receipt.payload.storage_uri,
    transactionProof?.storage_uri
  );
  const currentSigner = firstDefined(
    verification?.recoveredAddress,
    backendVerification?.signer_address,
    record?.signer_address,
    transactionProof?.signer_address
  );

  return (
    <div className="app-root">
      <div className="app-shell">
        <header className="glass-panel app-header">
          <div className="brand-lockup">
            <p className="brand-kicker">DragonHack MVP</p>
            <div className="brand-title-row">
              <h1>OAKProof</h1>
              <span className="brand-pill">single web app</span>
            </div>
            <p className="brand-copy">
              One browser app for station control and proof verification, backed by the capture
              service on one side and the receipt or anchor service on the other.
            </p>
          </div>

          <nav className="tab-strip" aria-label="Primary">
            {(["record", "verify", "about"] as TabId[]).map((tabId) => (
              <button
                key={tabId}
                type="button"
                className={`tab-button${activeTab === tabId ? " is-active" : ""}`}
                onClick={() => setActiveTab(tabId)}
              >
                {tabId}
              </button>
            ))}
          </nav>

          <div className="header-controls">
            <label className="header-field">
              <span>Receipt API</span>
              <input
                value={backendUrl}
                onChange={(event) => setBackendUrl(event.target.value)}
                placeholder="http://127.0.0.1:8000"
              />
            </label>

            <label className="header-field">
              <span>Station API</span>
              <input
                value={captureUrl}
                onChange={(event) => setCaptureUrl(event.target.value)}
                placeholder="http://127.0.0.1:8100"
              />
            </label>

            <button
              type="button"
              className="secondary-button"
              onClick={() => setIsProofCardOpen(true)}
              disabled={!hasProofData}
            >
              Proof card
            </button>
          </div>
        </header>

        <section className="glass-panel hero-shell">
          <div className="hero-copy">
            <p className="section-kicker">{headline.eyebrow}</p>
            <h2>{headline.title}</h2>
            <p>{headline.description}</p>

            <div className="status-row">
              <span className={`status-pill${signatureHealthy ? " is-good" : ""}`}>
                Signature {verification ? (signatureHealthy ? "ready" : "invalid") : "pending"}
              </span>
              <span className={`status-pill${txRecordLinked ? " is-good" : ""}`}>
                Chain link {txRecordLinked ? "confirmed" : "waiting"}
              </span>
              <span className={`status-pill${txMatchHealthy ? " is-good" : ""}`}>
                Video hash {txMatchHealthy ? "confirmed" : "waiting"}
              </span>
              <span className={`status-pill${backendHealth?.anchoringMode === "manual" ? " is-warn" : " is-good"}`}>
                Anchor mode {backendHealth?.anchoringMode ?? "unknown"}
              </span>
            </div>
          </div>

          <div className="hero-preview-stack">
            <div className="hero-preview-shell">
              <div className="hero-preview-bar">
                <span className="hero-window-dots">
                  <i />
                  <i />
                  <i />
                </span>
                <span>{activeTab === "record" ? "record shell" : `${activeTab} shell`}</span>
              </div>

              <div className="hero-preview-body">
                <div className="preview-orb" />
                <div className="preview-grid" />
                <div className="preview-copy">
                  <p className="section-kicker">Hero preview shell</p>
                  <h3>{receiptId ? clipMiddle(receiptId, 12) : "Ready for first proof card"}</h3>
                  <p>
                    {activeTab === "record"
                      ? "Start and stop OAK station sessions here, keep the preview fresh over HTTP, and land on proof outputs that can feed the verification side of the app."
                      : activeTab === "verify"
                        ? "Use the preserved verification flows below to fetch receipts, paste envelopes, and compare local files against on-chain data."
                        : "The shell, modal, and verification panels now live under one consistent app surface."}
                  </p>
                </div>

                <div className="hero-metric-row">
                  <div className="hero-metric">
                    <span>Signer</span>
                    <strong>{clipMiddle(currentSigner, 10)}</strong>
                  </div>
                  <div className="hero-metric">
                    <span>Video hash</span>
                    <strong>{clipMiddle(selectedVideoHash, 10)}</strong>
                  </div>
                  <div className="hero-metric">
                    <span>Storage</span>
                    <strong>{clipMiddle(currentStorageUri, 10)}</strong>
                  </div>
                </div>
              </div>
            </div>

            <div className="hero-action-row">
              <button type="button" className="primary-button" onClick={() => setActiveTab("verify")}>
                Open verify tab
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setIsProofCardOpen(true)}
                disabled={!hasProofData}
              >
                Open proof card
              </button>
              {currentExplorerUrl ? (
                <a
                  className="secondary-link"
                  href={currentExplorerUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  Explorer
                </a>
              ) : (
                <span className="secondary-link is-disabled">Explorer pending</span>
              )}
            </div>
          </div>
        </section>

        <section className="tab-section">
          {activeTab === "record" ? (
            <RecordTab
              captureUrl={captureUrl}
              onOpenProofCard={() => setIsProofCardOpen(true)}
              onReceiptIdReady={setReceiptId}
            />
          ) : null}

          {activeTab === "verify" ? (
            <VerifyTab
              receiptId={receiptId}
              receiptText={receiptText}
              transactionHash={transactionHash}
              selectedVideo={selectedVideo}
              selectedVideoHash={selectedVideoHash}
              activeReceipt={activeReceipt}
              record={record}
              verification={verification}
              backendVerification={backendVerification}
              transactionProof={transactionProof}
              activeAction={activeAction}
              error={error}
              backendHealth={backendHealth}
              signatureHealthy={signatureHealthy}
              canAnchorNow={canAnchorNow}
              decodedTransactionText={transactionProof ? prettyJson(transactionProof) : null}
              canonicalMessage={verification?.canonicalMessage ?? null}
              onReceiptIdChange={setReceiptId}
              onReceiptTextChange={setReceiptText}
              onTransactionHashChange={setTransactionHash}
              onVideoChange={handleVideoChange}
              onFetchSubmit={handleFetch}
              onAnalyzeSubmit={handleAnalyze}
              onAnchorNow={handleAnchorNow}
              onTransactionSubmit={handleTransactionLookup}
              onOpenProofCard={() => setIsProofCardOpen(true)}
            />
          ) : null}

          {activeTab === "about" ? (
            <AboutTab
              backendUrl={backendUrl}
              receiptId={receiptId}
              verification={verification}
              transactionProof={transactionProof}
              record={record}
              onOpenProofCard={() => setIsProofCardOpen(true)}
            />
          ) : null}
        </section>
      </div>

      <ProofCardModal
        isOpen={isProofCardOpen}
        onClose={() => setIsProofCardOpen(false)}
        receiptId={receiptId}
        activeReceipt={activeReceipt}
        record={record}
        verification={verification}
        backendVerification={backendVerification}
        backendHealth={backendHealth}
        transactionProof={transactionProof}
        selectedVideoHash={selectedVideoHash}
      />
    </div>
  );
}
