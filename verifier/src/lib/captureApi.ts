import type {
  CaptureSessionStatus,
  StartCaptureSessionRequest,
  StopCaptureSessionResponse
} from "../types";

interface CapturePreviewOptions {
  cacheBust?: number;
  width?: number;
  height?: number;
  quality?: number;
  fps?: number;
}

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

function applyCapturePreviewOptions(url: URL, options: CapturePreviewOptions): void {
  if (options.cacheBust) {
    url.searchParams.set("t", String(options.cacheBust));
  }
  if (options.width) {
    url.searchParams.set("width", String(options.width));
  }
  if (options.height) {
    url.searchParams.set("height", String(options.height));
  }
  if (options.quality) {
    url.searchParams.set("quality", String(options.quality));
  }
  if (options.fps) {
    url.searchParams.set("fps", String(options.fps));
  }
}

export function buildCapturePreviewUrl(
  baseUrl: string,
  sessionId: string,
  kind: "rgb" | "depth",
  options: CapturePreviewOptions = {}
): string {
  const url = new URL(
    `${normalizeBaseUrl(baseUrl)}/api/v1/capture/sessions/${encodeURIComponent(sessionId)}/preview/${kind}.jpg`
  );
  applyCapturePreviewOptions(url, options);
  return url.toString();
}

export function buildCapturePreviewStreamUrl(
  baseUrl: string,
  sessionId: string,
  options: CapturePreviewOptions = {}
): string {
  const url = new URL(
    `${normalizeBaseUrl(baseUrl)}/api/v1/capture/sessions/${encodeURIComponent(sessionId)}/preview/rgb.mjpeg`
  );
  applyCapturePreviewOptions(url, options);
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
