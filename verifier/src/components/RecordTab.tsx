import { FormEvent, useEffect, useState } from "react";

import {
  buildCapturePreviewStreamUrl,
  buildCapturePreviewUrl,
  fetchCaptureSession,
  isCaptureSessionTerminal,
  resolveCaptureAssetUrl,
  startCaptureSession,
  stopCaptureSession
} from "../lib/captureApi";
import type { CaptureSessionStatus } from "../types";

function clipMiddle(value: string | null | undefined, edge = 12): string {
  if (!value) {
    return "n/a";
  }
  if (value.length <= edge * 2 + 3) {
    return value;
  }
  return `${value.slice(0, edge)}...${value.slice(-edge)}`;
}

function normalizeTags(raw: string): string[] {
  return raw
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function firstDefined(...values: Array<string | null | undefined>): string | null {
  for (const value of values) {
    if (value) {
      return value;
    }
  }
  return null;
}

function statusTone(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const normalized = value.toLowerCase();
  if (normalized.includes("verified") || normalized.includes("recording") || normalized.includes("anchored")) {
    return " is-good";
  }
  if (normalized.includes("failed") || normalized.includes("paused") || normalized.includes("inconclusive")) {
    return " is-warn";
  }
  return "";
}

function sessionStateLabel(session: CaptureSessionStatus | null): string {
  if (!session) {
    return "idle";
  }
  return session.live_state?.recording_state ?? session.state;
}

interface RecordTabProps {
  captureUrl: string;
  onOpenProofCard: () => void;
  onReceiptIdReady: (receiptId: string) => void;
}

const RGB_PREVIEW_WIDTH = 960;
const RGB_PREVIEW_QUALITY = 72;
const RGB_PREVIEW_FPS = 14;
const DEPTH_PREVIEW_WIDTH = 360;
const DEPTH_PREVIEW_QUALITY = 55;

export function RecordTab({ captureUrl, onOpenProofCard, onReceiptIdReady }: RecordTabProps) {
  const [assetId, setAssetId] = useState("demo-batch-001");
  const [operatorId, setOperatorId] = useState("");
  const [notes, setNotes] = useState("Hackathon station capture");
  const [tagsText, setTagsText] = useState("oak4, demo");
  const [session, setSession] = useState<CaptureSessionStatus | null>(null);
  const [actionState, setActionState] = useState<"idle" | "starting" | "stopping">("idle");
  const [recordError, setRecordError] = useState<string | null>(null);
  const [rgbPreviewMode, setRgbPreviewMode] = useState<"stream" | "snapshot">("stream");
  const [rgbPreviewNonce, setRgbPreviewNonce] = useState(() => Date.now());
  const [depthPreviewNonce, setDepthPreviewNonce] = useState(() => Date.now());
  const [showDepthPreview, setShowDepthPreview] = useState(false);

  const sessionActive =
    session !== null &&
    !isCaptureSessionTerminal(session) &&
    ["starting", "recording", "paused", "stopping"].includes(session.state);
  const currentReceiptId = session?.proof_summary?.receipt_workflow?.receipt_id ?? null;
  const currentAnchorUrl = session?.proof_summary?.receipt_workflow?.anchor_tx_url ?? null;
  const currentAnchorTxHash = session?.proof_summary?.receipt_workflow?.anchor_tx_hash ?? null;
  const liveState = session?.live_state ?? null;
  const deviceInfo = session?.device_info ?? null;
  const rgbStreamPreviewUrl =
    session?.session_id
      ? buildCapturePreviewStreamUrl(captureUrl, session.session_id, {
        cacheBust: Date.parse(session.started_at),
        width: RGB_PREVIEW_WIDTH,
        quality: RGB_PREVIEW_QUALITY,
        fps: RGB_PREVIEW_FPS
      })
      : null;
  const rgbSnapshotPreviewUrl =
    session?.session_id
      ? buildCapturePreviewUrl(captureUrl, session.session_id, "rgb", {
        cacheBust: rgbPreviewNonce,
        width: RGB_PREVIEW_WIDTH,
        quality: RGB_PREVIEW_QUALITY
      })
      : null;
  const previewUrl = rgbPreviewMode === "snapshot" ? rgbSnapshotPreviewUrl : rgbStreamPreviewUrl;
  const depthPreviewUrl =
    showDepthPreview && session?.session_id
      ? buildCapturePreviewUrl(captureUrl, session.session_id, "depth", {
        cacheBust: depthPreviewNonce,
        width: DEPTH_PREVIEW_WIDTH,
        quality: DEPTH_PREVIEW_QUALITY
      })
      : null;

  useEffect(() => {
    if (!currentReceiptId) {
      return;
    }
    onReceiptIdReady(currentReceiptId);
  }, [currentReceiptId, onReceiptIdReady]);

  useEffect(() => {
    setRgbPreviewMode("stream");
    setRgbPreviewNonce(Date.now());
    setDepthPreviewNonce(Date.now());
    setShowDepthPreview(false);
  }, [session?.session_id]);

  useEffect(() => {
    if (!session?.session_id || !sessionActive) {
      return;
    }

    let cancelled = false;
    const intervalId = window.setInterval(async () => {
      try {
        const nextSession = await fetchCaptureSession(captureUrl, session.session_id);
        if (cancelled) {
          return;
        }
        setSession(nextSession);
        if (nextSession.proof_summary?.receipt_workflow?.receipt_id) {
          onReceiptIdReady(nextSession.proof_summary.receipt_workflow.receipt_id);
        }
      } catch (caughtError) {
        if (cancelled) {
          return;
        }
        setRecordError(
          caughtError instanceof Error
            ? caughtError.message
            : "Failed to refresh station session status."
        );
      }
    }, 1200);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [captureUrl, onReceiptIdReady, session?.session_id, sessionActive]);

  useEffect(() => {
    if (!session?.session_id || rgbPreviewMode !== "snapshot") {
      return;
    }

    const snapshotIntervalId = window.setInterval(() => {
      setRgbPreviewNonce(Date.now());
    }, sessionActive ? 160 : 1800);

    return () => {
      window.clearInterval(snapshotIntervalId);
    };
  }, [rgbPreviewMode, session?.session_id, sessionActive]);

  useEffect(() => {
    if (!session?.session_id || !showDepthPreview) {
      return;
    }

    const depthIntervalId = window.setInterval(() => {
      setDepthPreviewNonce(Date.now());
    }, sessionActive ? 1200 : 3200);

    return () => {
      window.clearInterval(depthIntervalId);
    };
  }, [session?.session_id, sessionActive, showDepthPreview]);

  async function handleStart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (actionState !== "idle" || sessionActive) {
      return;
    }

    setActionState("starting");
    setRecordError(null);

    try {
      const nextSession = await startCaptureSession(captureUrl, {
        asset_id: assetId.trim(),
        operator_id: operatorId.trim() || null,
        notes: notes.trim() || null,
        tags: normalizeTags(tagsText),
        simulate: false
      });
      setSession(nextSession);
      setDepthPreviewNonce(Date.now());
    } catch (caughtError) {
      setRecordError(
        caughtError instanceof Error ? caughtError.message : "Failed to start capture session."
      );
    } finally {
      setActionState("idle");
    }
  }

  async function handleStop() {
    if (!session?.session_id || actionState !== "idle" || !sessionActive) {
      return;
    }

    setActionState("stopping");
    setRecordError(null);

    try {
      const nextSession = await stopCaptureSession(captureUrl, session.session_id);
      setSession(nextSession);
      if (nextSession.proof_summary?.receipt_workflow?.receipt_id) {
        onReceiptIdReady(nextSession.proof_summary.receipt_workflow.receipt_id);
      }
      setDepthPreviewNonce(Date.now());
    } catch (caughtError) {
      setRecordError(
        caughtError instanceof Error ? caughtError.message : "Failed to stop capture session."
      );
    } finally {
      setActionState("idle");
    }
  }

  const proofSummary = session?.proof_summary ?? null;
  const receiptWorkflow = proofSummary?.receipt_workflow ?? null;
  const videoUrl = resolveCaptureAssetUrl(
    captureUrl,
    session?.artifacts?.rgb_video_uri,
    session?.artifacts?.rgb_video_relative_path
  );
  const proofUrl = resolveCaptureAssetUrl(
    captureUrl,
    session?.artifacts?.proof_uri,
    session?.artifacts?.proof_relative_path
  );
  const receiptUrl = resolveCaptureAssetUrl(
    captureUrl,
    session?.artifacts?.receipt_uri ?? receiptWorkflow?.receipt_uri ?? null,
    session?.artifacts?.receipt_relative_path ?? receiptWorkflow?.receipt_relative_path ?? null
  );
  const stationModeLabel = session ? (session.simulate ? "simulate" : "live") : "live";
  const stationDeviceLabel =
    firstDefined(deviceInfo?.product_name, deviceInfo?.name, deviceInfo?.platform) ?? "station offline";
  const currentPrompt =
    firstDefined(liveState?.prompt, liveState?.current_challenge?.prompt, receiptWorkflow?.reason) ?? "Ready to start a station session.";
  const currentPauseReason = firstDefined(liveState?.recording_pause_reason, liveState?.warning, session?.error);

  return (
    <div className="tab-stack">
      <form className="record-console-grid" onSubmit={handleStart}>
        <article className="glass-panel panel-surface station-preview-panel">
          <div className="preview-stage-toolbar">
            <span>OAK station preview</span>
            <div className="inline-chip-row">
              <span className={`status-pill${statusTone(sessionStateLabel(session))}`}>
                {sessionStateLabel(session)}
              </span>
              <span className="status-pill">{stationModeLabel}</span>
              <span className="status-pill">{stationDeviceLabel}</span>
            </div>
          </div>

          <div className="station-preview-shell">
            {previewUrl ? (
              <img
                className="station-preview-image"
                src={previewUrl}
                alt="Live OAK station preview"
                fetchPriority="high"
                key={previewUrl}
                onError={() => {
                  if (rgbPreviewMode === "stream") {
                    setRgbPreviewMode("snapshot");
                    setRgbPreviewNonce(Date.now());
                  }
                }}
              />
            ) : (
              <div className="station-preview-placeholder">
                <span className="preview-badge">station console</span>
                <strong>Waiting for a session to start</strong>
                <p>The browser drives the OAK station through the capture service and pulls annotated preview frames over plain HTTP.</p>
              </div>
            )}
          </div>

          <div className="station-preview-insights">
            <div className="station-instruction-card">
              <p className="section-kicker">Challenge instruction</p>
              <h3>{currentPrompt}</h3>
              <p>
                {currentPauseReason
                  ? `Pause reason: ${currentPauseReason}`
                  : "No pause reason is active right now."}
              </p>
            </div>

            {depthPreviewUrl ? (
              <div className="depth-preview-card">
                <div className="depth-preview-header">
                  <span>Aligned depth</span>
                  <button
                    type="button"
                    className="secondary-button depth-preview-toggle is-active"
                    onClick={() => setShowDepthPreview(false)}
                  >
                    Hide
                  </button>
                </div>
                <img
                  src={depthPreviewUrl}
                  alt="Latest aligned depth preview"
                  decoding="async"
                  fetchPriority="low"
                />
              </div>
            ) : (
              <div className="depth-preview-card">
                <div className="depth-preview-header">
                  <span>Aligned depth</span>
                  <button
                    type="button"
                    className="secondary-button depth-preview-toggle"
                    onClick={() => setShowDepthPreview(true)}
                    disabled={!session?.session_id}
                  >
                    Show
                  </button>
                </div>
                <div className="depth-preview-placeholder">
                  Depth stays off by default so the RGB preview can stay as responsive as possible.
                </div>
              </div>
            )}
          </div>
        </article>

        <article className="glass-panel panel-surface station-control-panel">
          <div className="panel-heading">
            <p className="section-kicker">Record</p>
            <h3>Web-controlled OAK station console</h3>
            <p>Start one live OAK4 capture session, monitor its state, and stop it from the same browser tab.</p>
          </div>

          <label className="field-shell">
            <span>Asset ID</span>
            <input
              value={assetId}
              onChange={(event) => setAssetId(event.target.value)}
              disabled={sessionActive || actionState !== "idle"}
              placeholder="batch-001"
              required
            />
          </label>

          <label className="field-shell">
            <span>Operator ID</span>
            <input
              value={operatorId}
              onChange={(event) => setOperatorId(event.target.value)}
              disabled={sessionActive || actionState !== "idle"}
              placeholder="operator-a"
            />
          </label>

          <label className="field-shell">
            <span>Notes</span>
            <textarea
              rows={3}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              disabled={sessionActive || actionState !== "idle"}
              placeholder="First intake capture"
            />
          </label>

          <label className="field-shell">
            <span>Tags</span>
            <input
              value={tagsText}
              onChange={(event) => setTagsText(event.target.value)}
              disabled={sessionActive || actionState !== "idle"}
              placeholder="intake, oak4"
            />
          </label>

          {session ? (
            <dl className="info-list compact-info-list">
              <div>
                <dt>Session ID</dt>
                <dd>{clipMiddle(session.session_id, 14)}</dd>
              </div>
              <div>
                <dt>Workflow stage</dt>
                <dd>{liveState?.workflow_stage ?? session.state}</dd>
              </div>
              <div>
                <dt>Recording state</dt>
                <dd>{sessionStateLabel(session)}</dd>
              </div>
              <div>
                <dt>Prompt</dt>
                <dd>{currentPrompt}</dd>
              </div>
            </dl>
          ) : null}

          <button
            type={sessionActive ? "button" : "submit"}
            className={`primary-button station-cta${sessionActive ? " is-stop" : ""}`}
            onClick={sessionActive ? () => void handleStop() : undefined}
            disabled={
              actionState !== "idle" ||
              (!sessionActive && assetId.trim().length === 0)
            }
          >
            {actionState === "starting"
              ? "Starting session..."
              : actionState === "stopping"
                ? "Stopping session..."
                : sessionActive
                  ? "Stop Session"
                  : "Start Session"}
          </button>

          <div className="action-row">
            <button type="button" className="secondary-button" onClick={onOpenProofCard}>
              Proof card
            </button>
            {currentAnchorUrl ? (
              <a className="secondary-link" href={currentAnchorUrl} target="_blank" rel="noreferrer">
                Anchor link
              </a>
            ) : (
              <span className="secondary-link is-disabled">Anchor pending</span>
            )}
          </div>
        </article>
      </form>

      {recordError ? <section className="error-banner">{recordError}</section> : null}

      <section className="mini-card-grid">
        <article className="glass-panel panel-surface mini-panel">
          <p className="section-kicker">Current state</p>
          <h3>{session ? sessionStateLabel(session) : "idle"}</h3>
          <p>
            {liveState?.workflow_stage
              ? `Workflow stage: ${liveState.workflow_stage}`
              : "No session is active yet."}
          </p>
        </article>

        <article className="glass-panel panel-surface mini-panel">
          <p className="section-kicker">Pause reason</p>
          <h3>{currentPauseReason ?? "none"}</h3>
          <p>
            {liveState?.warning
              ? `Warning: ${liveState.warning}`
              : "Live warnings and pause reasons from the station runtime appear here."}
          </p>
        </article>

        <article className="glass-panel panel-surface mini-panel">
          <p className="section-kicker">Device info</p>
          <h3>{stationDeviceLabel}</h3>
          <p>
            {deviceInfo
              ? `${deviceInfo.platform}${deviceInfo.usb_speed ? ` | ${deviceInfo.usb_speed}` : ""}`
              : "Device metadata will populate after the station runtime opens."}
          </p>
        </article>
      </section>

      {session ? (
        <section className="dual-panel-grid">
          <article className="glass-panel panel-surface">
            <div className="panel-heading">
              <p className="section-kicker">Proof summary</p>
              <h3>Session outcome</h3>
            </div>

            <dl className="info-list">
              <div>
                <dt>Overall status</dt>
                <dd>{String(proofSummary?.overall_status ?? session.state)}</dd>
              </div>
              <div>
                <dt>Frames processed</dt>
                <dd>{String(proofSummary?.frames_processed ?? liveState?.frame_index ?? "n/a")}</dd>
              </div>
              <div>
                <dt>Recorded frames</dt>
                <dd>{String(proofSummary?.recorded_frames ?? liveState?.recorded_frames ?? "n/a")}</dd>
              </div>
              <div>
                <dt>Passed challenges</dt>
                <dd>{String(proofSummary?.passed_challenges ?? liveState?.challenges_passed ?? "n/a")}</dd>
              </div>
            </dl>

            {proofSummary ? <pre className="record-json-panel">{JSON.stringify(proofSummary, null, 2)}</pre> : null}
          </article>

          <article className="glass-panel panel-surface">
            <div className="panel-heading">
              <p className="section-kicker">Receipt workflow</p>
              <h3>Station post-processing</h3>
            </div>

            <dl className="info-list">
              <div>
                <dt>Status</dt>
                <dd>{receiptWorkflow?.status ?? "n/a"}</dd>
              </div>
              <div>
                <dt>Reason</dt>
                <dd>{receiptWorkflow?.reason ?? "n/a"}</dd>
              </div>
              <div>
                <dt>Receipt ID</dt>
                <dd>{clipMiddle(receiptWorkflow?.receipt_id, 14)}</dd>
              </div>
              <div>
                <dt>Anchor TX</dt>
                <dd>{clipMiddle(currentAnchorTxHash, 14)}</dd>
              </div>
            </dl>

            <div className="artifact-link-grid">
              {videoUrl ? (
                <a className="artifact-link-card" href={videoUrl} target="_blank" rel="noreferrer">
                  <span>Video</span>
                  <strong>Open `rgb.mp4`</strong>
                </a>
              ) : null}
              {proofUrl ? (
                <a className="artifact-link-card" href={proofUrl} target="_blank" rel="noreferrer">
                  <span>Proof</span>
                  <strong>Open `proof.json`</strong>
                </a>
              ) : null}
              {receiptUrl ? (
                <a className="artifact-link-card" href={receiptUrl} target="_blank" rel="noreferrer">
                  <span>Receipt</span>
                  <strong>Open `receipt.json`</strong>
                </a>
              ) : null}
              {currentAnchorUrl ? (
                <a className="artifact-link-card" href={currentAnchorUrl} target="_blank" rel="noreferrer">
                  <span>Anchor</span>
                  <strong>Open explorer</strong>
                </a>
              ) : null}
            </div>
          </article>
        </section>
      ) : null}
    </div>
  );
}
