import type { ReceiptRecord, TransactionProofResult, VerifiedReceipt } from "../types";

function clipMiddle(value: string | null | undefined, edge = 12): string {
  if (!value) {
    return "n/a";
  }
  if (value.length <= edge * 2 + 3) {
    return value;
  }
  return `${value.slice(0, edge)}...${value.slice(-edge)}`;
}

interface AboutTabProps {
  backendUrl: string;
  receiptId: string;
  verification: VerifiedReceipt | null;
  transactionProof: TransactionProofResult | null;
  record: ReceiptRecord | null;
  onOpenProofCard: () => void;
}

export function AboutTab({
  backendUrl,
  receiptId,
  verification,
  transactionProof,
  record,
  onOpenProofCard
}: AboutTabProps) {
  return (
    <div className="tab-stack">
      <section className="mini-card-grid">
        <article className="glass-panel panel-surface mini-panel">
          <p className="section-kicker">Station</p>
          <h3>The capture station records and signs</h3>
          <p>
            The OAK station backend records the session, writes local proof artifacts, and signs a
            receipt for the captured asset.
          </p>
        </article>

        <article className="glass-panel panel-surface mini-panel">
          <p className="section-kicker">Backend</p>
          <h3>The receipt service stores and anchors digests</h3>
          <ul className="clean-list">
            <li>The backend stores normalized receipt records on local disk.</li>
            <li>It verifies the station signer before accepting a receipt.</li>
            <li>It can anchor the receipt and asset digests to Flare when configured.</li>
          </ul>
        </article>

        <article className="glass-panel panel-surface mini-panel">
          <p className="section-kicker">Verifier</p>
          <h3>The browser hashes locally and checks signer plus tx</h3>
          <p>
            The web app hashes the chosen video in-browser, verifies the signed receipt locally,
            and compares transaction data against the backend record and local file hash.
          </p>
        </article>
      </section>

      <section className="dual-panel-grid">
        <article className="glass-panel panel-surface">
          <div className="panel-heading">
            <p className="section-kicker">Current context</p>
            <h3>Demo snapshot</h3>
          </div>

          <dl className="info-list">
            <div>
              <dt>Backend URL</dt>
              <dd>{backendUrl}</dd>
            </div>
            <div>
              <dt>Receipt ID</dt>
              <dd>{clipMiddle(receiptId || record?.receipt_id, 14)}</dd>
            </div>
            <div>
              <dt>Recovered signer</dt>
              <dd>{clipMiddle(verification?.recoveredAddress, 14)}</dd>
            </div>
            <div>
              <dt>Transaction / Explorer</dt>
              <dd>{clipMiddle(transactionProof?.explorer_url ?? record?.anchor_tx_url, 14)}</dd>
            </div>
          </dl>
        </article>

        <article className="glass-panel panel-surface">
          <div className="panel-heading">
            <p className="section-kicker">Operator notes</p>
            <h3>What to say in the demo</h3>
          </div>

          <ul className="clean-list">
            <li>The station signs the receipt after capture, not the browser.</li>
            <li>The backend is the receipt authority and optional anchoring service.</li>
            <li>The verifier never uploads the local video just to compare hashes.</li>
            <li>A decoded tx is only trusted once it links back to a consistent backend record.</li>
          </ul>

          <button type="button" className="secondary-button" onClick={onOpenProofCard}>
            Open proof card
          </button>
        </article>
      </section>
    </div>
  );
}
