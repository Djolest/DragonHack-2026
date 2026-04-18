import type { ReceiptRecord, VerificationResult } from "../types";

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, "");
}

async function requestJson<T>(input: string): Promise<T> {
  const response = await fetch(input);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchReceipt(baseUrl: string, receiptId: string): Promise<ReceiptRecord> {
  return requestJson<ReceiptRecord>(
    `${normalizeBaseUrl(baseUrl)}/api/v1/receipts/${encodeURIComponent(receiptId)}`
  );
}

export async function fetchVerification(
  baseUrl: string,
  receiptId: string
): Promise<VerificationResult> {
  return requestJson<VerificationResult>(
    `${normalizeBaseUrl(baseUrl)}/api/v1/receipts/${encodeURIComponent(receiptId)}/verify`
  );
}
