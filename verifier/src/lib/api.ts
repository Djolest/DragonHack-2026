import type {
  AnchorResult,
  BackendHealth,
  ReceiptRecord,
  TransactionProofResult,
  VerificationResult
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

export async function fetchBackendHealth(baseUrl: string): Promise<BackendHealth> {
  return requestJson<BackendHealth>(`${normalizeBaseUrl(baseUrl)}/health`);
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

export async function anchorReceipt(baseUrl: string, receiptId: string): Promise<AnchorResult> {
  return requestJson<AnchorResult>(
    `${normalizeBaseUrl(baseUrl)}/api/v1/receipts/${encodeURIComponent(receiptId)}/anchor`,
    {
      method: "POST"
    }
  );
}

export async function fetchTransactionProof(
  baseUrl: string,
  txHash: string,
  assetHash?: string
): Promise<TransactionProofResult> {
  const url = new URL(
    `${normalizeBaseUrl(baseUrl)}/api/v1/transactions/${encodeURIComponent(txHash)}`
  );
  if (assetHash) {
    url.searchParams.set("asset_hash", assetHash);
  }
  return requestJson<TransactionProofResult>(url.toString());
}
