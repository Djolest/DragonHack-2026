import { FormEvent, startTransition, useState } from "react";

import { fetchReceipt, fetchVerification } from "./lib/api";
import { parseReceiptEnvelope, verifyReceiptEnvelope } from "./lib/receipt";
import type {
  ReceiptRecord,
  SignedReceiptEnvelope,
  VerificationResult,
  VerifiedReceipt
} from "./types";

const defaultBackendUrl = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export default function App() {
  const [backendUrl, setBackendUrl] = useState(defaultBackendUrl);
  const [receiptId, setReceiptId] = useState("");
  const [receiptText, setReceiptText] = useState("");
  const [record, setRecord] = useState<ReceiptRecord | null>(null);
  const [verification, setVerification] = useState<VerifiedReceipt | null>(null);
  const [backendVerification, setBackendVerification] = useState<VerificationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runVerification(receipt: SignedReceiptEnvelope) {
    const localVerification = await verifyReceiptEnvelope(receipt);
    startTransition(() => {
      setVerification(localVerification);
    });
  }

  async function handleFetch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
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
      setLoading(false);
    }
  }

  async function handleAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
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
      setLoading(false);
    }
  }

  const signatureHealthy =
    verification &&
    verification.signatureValid &&
    verification.payloadHash === (record?.receipt_hash ?? verification.payloadHash);

  return (
    <main className="app-shell">
      <section className="hero-card">
        <div>
          <p className="eyebrow">DragonHack MVP</p>
          <h1>OAKProof verifier console</h1>
          <p className="hero-copy">
            Validate signed proof receipts from the OAK4 capture station, inspect the payload
            digest, and compare local verification with backend anchor status.
          </p>
        </div>
        <div className="hero-status">
          <span className="status-chip">Local signature verification</span>
          <span className="status-chip">Backend record lookup</span>
          <span className="status-chip">Flare anchor visibility</span>
        </div>
      </section>

      <section className="grid">
        <form className="panel" onSubmit={handleFetch}>
          <div className="panel-header">
            <h2>Fetch from backend</h2>
            <p>Pull a stored receipt record from FastAPI.</p>
          </div>

          <label>
            <span>Backend URL</span>
            <input
              value={backendUrl}
              onChange={(event) => setBackendUrl(event.target.value)}
              placeholder="http://127.0.0.1:8000"
            />
          </label>

          <label>
            <span>Receipt ID</span>
            <input
              value={receiptId}
              onChange={(event) => setReceiptId(event.target.value)}
              placeholder="oakproof-..."
            />
          </label>

          <button type="submit" disabled={loading || receiptId.trim().length === 0}>
            {loading ? "Loading..." : "Fetch receipt"}
          </button>
        </form>

        <form className="panel" onSubmit={handleAnalyze}>
          <div className="panel-header">
            <h2>Paste receipt JSON</h2>
            <p>Verify any signed receipt in-browser without backend trust.</p>
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

          <button type="submit" disabled={loading || receiptText.trim().length === 0}>
            {loading ? "Verifying..." : "Verify pasted receipt"}
          </button>
        </form>
      </section>

      {error ? <section className="error-banner">{error}</section> : null}

      <section className="results-grid">
        <article className="panel result-panel">
          <div className="panel-header">
            <h2>Verification summary</h2>
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
              <dd>{record?.receipt.payload.storage_uri ?? "n/a"}</dd>
            </div>
          </dl>
        </article>

        <article className="panel result-panel">
          <div className="panel-header">
            <h2>Backend status</h2>
            <p>What the API currently knows about this receipt.</p>
          </div>

          <dl className="stats-list">
            <div>
              <dt>Receipt ID</dt>
              <dd>{(record?.receipt_id ?? receiptId) || "n/a"}</dd>
            </div>
            <div>
              <dt>Anchored</dt>
              <dd className={backendVerification?.anchored ? "good" : "warn"}>
                {backendVerification ? (backendVerification.anchored ? "yes" : "no") : "n/a"}
              </dd>
            </div>
            <div>
              <dt>Backend signer</dt>
              <dd>{backendVerification?.signer_address ?? record?.signer_address ?? "n/a"}</dd>
            </div>
            <div>
              <dt>Explorer</dt>
              <dd>
                {backendVerification?.anchor_tx_url ? (
                  <a href={backendVerification.anchor_tx_url} target="_blank" rel="noreferrer">
                    Open transaction
                  </a>
                ) : (
                  "n/a"
                )}
              </dd>
            </div>
          </dl>
        </article>
      </section>

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
