import { verifyMessage } from "ethers";

import type { SignedReceiptEnvelope, VerifiedReceipt } from "../types";

function normalizeValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((entry) => normalizeValue(entry));
  }

  if (value && typeof value === "object") {
    return Object.keys(value as Record<string, unknown>)
      .sort()
      .reduce<Record<string, unknown>>((accumulator, key) => {
        accumulator[key] = normalizeValue((value as Record<string, unknown>)[key]);
        return accumulator;
      }, {});
  }

  return value;
}

export function stableStringify(value: unknown): string {
  return JSON.stringify(normalizeValue(value));
}

export function parseReceiptEnvelope(raw: string): SignedReceiptEnvelope {
  const parsed = JSON.parse(raw) as SignedReceiptEnvelope;
  if (!parsed.payload || !parsed.signature) {
    throw new Error("Receipt JSON must include payload and signature objects.");
  }
  return parsed;
}

function toHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

export async function sha256Hex(input: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
  return toHex(digest);
}

export async function sha256FileHex(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return toHex(digest);
}

export async function verifyReceiptEnvelope(
  receipt: SignedReceiptEnvelope
): Promise<VerifiedReceipt> {
  const canonicalMessage = stableStringify(receipt.payload);
  const recoveredAddress = verifyMessage(canonicalMessage, receipt.signature.signature);
  const payloadHash = await sha256Hex(canonicalMessage);

  return {
    canonicalMessage,
    recoveredAddress,
    payloadHash,
    signatureValid:
      recoveredAddress.toLowerCase() === receipt.signature.signer_address.toLowerCase()
  };
}
