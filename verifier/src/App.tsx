import { ChangeEvent, FormEvent, startTransition, useState } from "react";

import { fetchReceipt, fetchTransactionProof, fetchVerification } from "./lib/api";
import { parseReceiptEnvelope, sha256FileHex, verifyReceiptEnvelope } from "./lib/receipt";
import type {
  ReceiptRecord,
  SignedReceiptEnvelope,
  TransactionProofResult,
  VerificationResult,
  VerifiedReceipt
} from "./types";

const defaultBackendUrl = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";

type ActiveAction = "transaction" | "fetch" | "analyze" | null;

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function statusLabel(value: boolean | null | undefined): string {
  if (value === true) {
    return "yes";
  }
  if (value === false) {
    return "no";
  }
  return "n/a";
}

export default function App() {
  const [backendUrl, setBackendUrl] = useState(defaultBackendUrl);
  const [receiptId, setReceiptId] = useState("");
  const [receiptText, setReceiptText] = useState("");
  const [transactionHash, setTransactionHash] = useState("");
  const [selectedVideo, setSelectedVideo] = useState<File | null>(null);
  const [selectedVideoHash, setSelectedVideoHash] = useState<string | null>(null);
  const [record, setRecord] = useState<ReceiptRecord | null>(null);
  const [verification, setVerification] = useState<VerifiedReceipt | null>(null);
  const [backendVerification, setBackendVerification] = useState<VerificationResult | null>(null);
  const [transactionProof, setTransactionProof] = useState<TransactionProofResult | null>(null);
  const [activeAction, setActiveAction] = useState<ActiveAction>(null);
  const [error, setError] = useState<string | null>(null);

  async function runVerification(receipt: SignedReceiptEnvelope) {
    const localVerification = await verifyReceiptEnvelope(receipt);
    startTransition(() => {
      setVerification(localVerification);
    });
  }

  function handleVideoChange(event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0] ?? null;
    setSelectedVideo(nextFile);
    setSelectedVideoHash(null);
    setTransactionProof(null);
  }

  async function handleTransactionLookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
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
    setActiveAction("fetch");
    setError(null);

    try {
      const nextRecord = await fetchReceipt(backendUrl, receiptId.trim());
      setRecord(nextRecord);
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
    setActiveAction("analyze");
    setError(null);

    try {
      const parsed = parseReceiptEnvelope(receiptText);
      setRecord(null);
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

  const signatureHealthy =
    verification &&
    verification.signatureValid &&
    verification.payloadHash === (record?.receipt_hash ?? verification.payloadHash);
  const txMatchHealthy = transactionProof?.asset_hash_matches === true;

  return (
    <main className="app-shell">
      <section className="hero-card">
        <div>
          <p className="eyebrow">DragonHack MVP</p>
          <h1>OAKProof verifier console</h1>
          <p className="hero-copy">
            Hash a local video, inspect the Flare transaction payload, and cross-check the
            on-chain commitment against the signed receipt produced by the OAK4 station.
          </p>
        </div>
        <div className="hero-status">
          <span className="status-chip">Video SHA-256 match</span>
          <span className="status-chip">Receipt signature recovery</span>
          <span className="status-chip">Flare transaction decoding</span>
        </div>
      </section>

      <form className="panel panel-wide" onSubmit={handleTransactionLookup}>
        <div className="panel-header">
          <h2>Verify video against Flare transaction</h2>
          <p>
            Enter the transaction hash, pick the recorded video, and compare its local hash with
            the asset digest committed on chain.
          </p>
        </div>

        <div className="panel-grid">
          <label>
            <span>Backend URL</span>
            <input
              value={backendUrl}
              onChange={(event) => setBackendUrl(event.target.value)}
              placeholder="http://127.0.0.1:8000"
            />
          </label>

          <label>
            <span>Transaction hash</span>
            <input
              value={transactionHash}
              onChange={(event) => setTransactionHash(event.target.value)}
              placeholder="0x..."
            />
          </label>

          <label>
            <span>Recorded video</span>
            <input type="file" accept="video/*" onChange={handleVideoChange} />
          </label>
        </div>

        {selectedVideo ? (
          <p className="helper-text">
            Selected file: <strong>{selectedVideo.name}</strong>
            {selectedVideoHash ? ` | SHA-256 ${selectedVideoHash}` : ""}
          </p>
        ) : null}

        <button type="submit" disabled={activeAction !== null || transactionHash.trim().length === 0}>
          {activeAction === "transaction" ? "Checking Flare..." : "Verify video vs transaction"}
        </button>
      </form>

      <section className="grid">
        <form className="panel" onSubmit={handleFetch}>
          <div className="panel-header">
            <h2>Fetch receipt from backend</h2>
            <p>Load the stored receipt record when you already know the receipt ID.</p>
          </div>

          <label>
            <span>Receipt ID</span>
            <input
              value={receiptId}
              onChange={(event) => setReceiptId(event.target.value)}
              placeholder="oakproof-..."
            />
          </label>

          <button type="submit" disabled={activeAction !== null || receiptId.trim().length === 0}>
            {activeAction === "fetch" ? "Loading receipt..." : "Fetch receipt"}
          </button>
        </form>

        <form className="panel" onSubmit={handleAnalyze}>
          <div className="panel-header">
            <h2>Paste receipt JSON</h2>
            <p>Verify any signed receipt in-browser without trusting the backend.</p>
          </div>

          <label>
            <span>Receipt envelope</span>
            <textarea
              rows={18}
              value={receiptText}
              onChange={(event) => setReceiptText(event.target.value)}
              placeholder='{"payload": {...}, "signature": {...}}'
            />
          </label>

          <button
            type="submit"
            disabled={activeAction !== null || receiptText.trim().length === 0}
          >
            {activeAction === "analyze" ? "Verifying receipt..." : "Verify pasted receipt"}
          </button>
        </form>
      </section>

      {error ? <section className="error-banner">{error}</section> : null}

      <section className="results-grid">
        <article className="panel result-panel">
          <div className="panel-header">
            <h2>Flare transaction match</h2>
            <p>What the chain transaction says about the committed video hash.</p>
          </div>

          <dl className="stats-list">
            <div>
              <dt>Proof type</dt>
              <dd>{transactionProof?.proof_type ?? "n/a"}</dd>
            </div>
            <div>
              <dt>Transaction decoded</dt>
              <dd
                className={
                  transactionProof?.proof_valid
                    ? "good"
                    : transactionProof
                      ? "warn"
                      : undefined
                }
              >
                {transactionProof ? statusLabel(transactionProof.proof_valid) : "n/a"}
              </dd>
            </div>
            <div>
              <dt>Local video hash</dt>
              <dd>{selectedVideoHash ?? "n/a"}</dd>
            </div>
            <div>
              <dt>On-chain asset hash</dt>
              <dd>{transactionProof?.asset_hash ?? "n/a"}</dd>
            </div>
            <div>
              <dt>Video matches tx</dt>
              <dd className={txMatchHealthy ? "good" : transactionProof ? "warn" : undefined}>
                {transactionProof
                  ? statusLabel(transactionProof.asset_hash_matches)
                  : "n/a"}
              </dd>
            </div>
            <div>
              <dt>Explorer</dt>
              <dd>
                {transactionProof?.explorer_url ? (
                  <a href={transactionProof.explorer_url} target="_blank" rel="noreferrer">
                    Open transaction
                  </a>
                ) : (
                  "n/a"
                )}
              </dd>
            </div>
          </dl>
        </article>

        <article className="panel result-panel">
          <div className="panel-header">
            <h2>Receipt verification summary</h2>
            <p>Canonical message, signer recovery, and digest checks.</p>
          </div>

          <dl className="stats-list">
            <div>
              <dt>Signature valid</dt>
              <dd className={signatureHealthy ? "good" : "warn"}>
                {signatureHealthy ? "yes" : "not verified yet"}
              </dd>
            </div>
            <div>
              <dt>Recovered signer</dt>
              <dd>{verification?.recoveredAddress ?? "n/a"}</dd>
            </div>
            <div>
              <dt>Payload SHA-256</dt>
              <dd>{verification?.payloadHash ?? "n/a"}</dd>
            </div>
            <div>
              <dt>Storage URI</dt>
              <dd>{record?.receipt.payload.storage_uri ?? transactionProof?.storage_uri ?? "n/a"}</dd>
            </div>
          </dl>
        </article>

        <article className="panel result-panel">
          <div className="panel-header">
            <h2>Backend receipt status</h2>
            <p>What the backend currently knows about this capture receipt.</p>
          </div>

          <dl className="stats-list">
            <div>
              <dt>Receipt ID</dt>
              <dd>{record?.receipt_id ?? transactionProof?.receipt_id ?? (receiptId || "n/a")}</dd>
            </div>
            <div>
              <dt>Anchored</dt>
              <dd className={backendVerification?.anchored ? "good" : "warn"}>
                {backendVerification ? statusLabel(backendVerification.anchored) : "n/a"}
              </dd>
            </div>
            <div>
              <dt>Backend signer</dt>
              <dd>{backendVerification?.signer_address ?? record?.signer_address ?? "n/a"}</dd>
            </div>
            <div>
              <dt>Record found for tx</dt>
              <dd className={transactionProof?.record_found ? "good" : transactionProof ? "warn" : undefined}>
                {transactionProof ? statusLabel(transactionProof.record_found) : "n/a"}
              </dd>
            </div>
          </dl>
        </article>
      </section>

      {transactionProof ? (
        <section className="panel message-panel">
          <div className="panel-header">
            <h2>Decoded chain payload</h2>
            <p>The normalized transaction data returned by the backend Flare decoder.</p>
          </div>
          <pre>{prettyJson(transactionProof)}</pre>
        </section>
      ) : null}

      {verification ? (
        <section className="panel message-panel">
          <div className="panel-header">
            <h2>Canonical signed message</h2>
            <p>This is the exact payload string used for the EIP-191 signature.</p>
          </div>
          <pre>{verification.canonicalMessage}</pre>
        </section>
      ) : null}
    </main>
  );
}
