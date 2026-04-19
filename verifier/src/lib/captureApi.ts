import type {
  CaptureSessionStatus,
  StartCaptureSessionRequest,
  StopCaptureSessionResponse
} from "../types";

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, "");
}

async function requestJson<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

function encodeAssetPath(relativePath: string): string {
  return relativePath
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

export function isCaptureSessionTerminal(status: CaptureSessionStatus | null): boolean {
  if (!status) {
    return false;
  }
  return status.state === "stopped" || status.state === "failed";
}

export async function startCaptureSession(
  baseUrl: string,
  payload: StartCaptureSessionRequest
): Promise<CaptureSessionStatus> {
  return requestJson<CaptureSessionStatus>(`${normalizeBaseUrl(baseUrl)}/api/v1/capture/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function fetchCaptureSession(
  baseUrl: string,
  sessionId: string
): Promise<CaptureSessionStatus> {
  return requestJson<CaptureSessionStatus>(
    `${normalizeBaseUrl(baseUrl)}/api/v1/capture/sessions/${encodeURIComponent(sessionId)}`
  );
}

export async function stopCaptureSession(
  baseUrl: string,
  sessionId: string
): Promise<CaptureSessionStatus> {
  const payload = await requestJson<StopCaptureSessionResponse>(
    `${normalizeBaseUrl(baseUrl)}/api/v1/capture/sessions/${encodeURIComponent(sessionId)}/stop`,
    {
      method: "POST"
    }
  );
  return payload.session;
}

export function buildCapturePreviewUrl(
  baseUrl: string,
  sessionId: string,
  kind: "rgb" | "depth",
  cacheBust?: number
): string {
  const url = new URL(
    `${normalizeBaseUrl(baseUrl)}/api/v1/capture/sessions/${encodeURIComponent(sessionId)}/preview/${kind}.jpg`
  );
  if (cacheBust) {
    url.searchParams.set("t", String(cacheBust));
  }
  return url.toString();
}

export function resolveCaptureAssetUrl(
  baseUrl: string,
  directUrl?: string | null,
  relativePath?: string | null
): string | null {
  if (directUrl) {
    return directUrl;
  }
  if (!relativePath) {
    return null;
  }
  return `${normalizeBaseUrl(baseUrl)}/assets/${encodeAssetPath(relativePath)}`;
}
