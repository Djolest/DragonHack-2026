from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from ..config import Settings
from ..models import ReceiptRecord, TransactionProofResult
from ..repository import ReceiptRepository
from .flare_anchor import ANCHOR_ABI


def normalize_transaction_hash(tx_hash: str) -> str:
    normalized = tx_hash if tx_hash.startswith("0x") else f"0x{tx_hash}"
    if len(normalized) != 66:
        raise ValueError("Transaction hash must be a 64-character hex string.")
    int(normalized[2:], 16)
    return normalized


def normalize_digest(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized.startswith("0x"):
        normalized = normalized[2:]
    return normalized or None


def hex_value(value: Any) -> str:
    if isinstance(value, bytes):
        return value.hex()
    if hasattr(value, "hex"):
        text = value.hex()
        return text[2:] if text.startswith("0x") else text
    return normalize_digest(str(value)) or ""


def normalize_input_data(raw_input: Any) -> str:
    if hasattr(raw_input, "hex"):
        raw_input = raw_input.hex()
    if isinstance(raw_input, bytes):
        raw_input = raw_input.hex()
    if not isinstance(raw_input, str):
        raise ValueError("Transaction input could not be decoded.")
    if not raw_input:
        raise ValueError("Transaction input is empty.")
    return raw_input if raw_input.startswith("0x") else f"0x{raw_input}"


def public_key_to_address(public_key_hex: str) -> str:
    normalized = public_key_hex[2:] if public_key_hex.startswith("0x") else public_key_hex
    public_key_bytes = bytes.fromhex(normalized)
    if len(public_key_bytes) == 65 and public_key_bytes[0] == 4:
        public_key_bytes = public_key_bytes[1:]
    if len(public_key_bytes) != 64:
        raise ValueError("Public key must be 64 bytes.")
    address_bytes = Web3.keccak(public_key_bytes)[-20:]
    return Web3.to_checksum_address(f"0x{address_bytes.hex()}")


def decode_legacy_proof_payload(raw_payload: str) -> dict[str, Any]:
    if not raw_payload.startswith("proof:"):
        raise ValueError("Transaction does not contain a signed proof payload.")

    proof = json.loads(raw_payload.split("proof:", 1)[1])
    required_fields = {"hash", "signature", "public_key", "address"}
    if not required_fields.issubset(proof):
        raise ValueError("Proof payload is missing required fields.")

    message = encode_defunct(text=proof["hash"])
    recovered_address = Account.recover_message(message, signature=proof["signature"])
    derived_address = public_key_to_address(proof["public_key"])
    proof["recovered_address"] = recovered_address
    proof["derived_address"] = derived_address
    proof["signature_valid"] = recovered_address.lower() == proof["address"].lower()
    proof["public_key_matches"] = derived_address.lower() == proof["address"].lower()
    proof["proof_valid"] = proof["signature_valid"] and proof["public_key_matches"]
    return proof


class FlareTransactionProofService:
    def __init__(
        self,
        settings: Settings,
        repository: ReceiptRepository,
        *,
        web3_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.web3_factory = web3_factory or (lambda rpc_url: Web3(Web3.HTTPProvider(rpc_url)))
        self.decoder_contract = Web3().eth.contract(abi=ANCHOR_ABI)

    def get_transaction_proof(
        self,
        tx_hash: str,
        *,
        provided_asset_hash: str | None = None,
    ) -> TransactionProofResult:
        normalized_tx_hash = normalize_transaction_hash(tx_hash)
        w3 = self.web3_factory(self.settings.flare_rpc_url)
        tx = w3.eth.get_transaction(normalized_tx_hash)
        raw_input = normalize_input_data(tx["input"])
        if raw_input == "0x":
            raise ValueError("Transaction input is empty.")

        record = self.repository.find_by_anchor_tx_hash(normalized_tx_hash)

        try:
            return self._decode_anchor_transaction(
                tx=tx,
                normalized_tx_hash=normalized_tx_hash,
                raw_input=raw_input,
                record=record,
                provided_asset_hash=provided_asset_hash,
            )
        except ValueError:
            return self._decode_legacy_transaction(
                tx=tx,
                normalized_tx_hash=normalized_tx_hash,
                raw_input=raw_input,
                provided_asset_hash=provided_asset_hash,
            )

    def _decode_anchor_transaction(
        self,
        *,
        tx: Any,
        normalized_tx_hash: str,
        raw_input: str,
        record: ReceiptRecord | None,
        provided_asset_hash: str | None,
    ) -> TransactionProofResult:
        function, params = self.decoder_contract.decode_function_input(raw_input)
        if function.fn_name != "anchorReceipt":
            raise ValueError("Transaction is not an OAKProof anchor call.")

        receipt_id_hash = hex_value(params["receiptIdHash"])
        receipt_digest = hex_value(params["receiptDigest"])
        asset_digest = hex_value(params["assetDigest"])
        normalized_provided_hash = normalize_digest(provided_asset_hash)
        record_consistent = None
        if record is not None:
            record_consistent = (
                normalize_digest(record.receipt_hash) == receipt_digest
                and normalize_digest(record.receipt.payload.asset_hash) == asset_digest
            )

        return TransactionProofResult(
            tx_hash=normalized_tx_hash,
            proof_type="anchor_contract",
            decoded=True,
            proof_valid=record is not None and record_consistent is True,
            chain_id=tx.get("chainId"),
            block_number=tx.get("blockNumber"),
            from_address=str(tx.get("from")) if tx.get("from") else None,
            to_address=str(tx.get("to")) if tx.get("to") else None,
            explorer_url=f"{self.settings.flare_explorer_base_url.rstrip('/')}/tx/{normalized_tx_hash}",
            receipt_id=record.receipt_id if record is not None else None,
            receipt_id_hash=receipt_id_hash,
            receipt_hash=receipt_digest,
            asset_hash=asset_digest,
            storage_uri=str(params["storageUri"]),
            signer_address=record.signer_address if record is not None else None,
            submitter_address=str(tx.get("from")) if tx.get("from") else None,
            record_found=record is not None,
            record_consistent=record_consistent,
            provided_asset_hash=normalized_provided_hash,
            asset_hash_matches=(
                normalized_provided_hash == asset_digest
                if normalized_provided_hash is not None
                else None
            ),
        )

    def _decode_legacy_transaction(
        self,
        *,
        tx: Any,
        normalized_tx_hash: str,
        raw_input: str,
        provided_asset_hash: str | None,
    ) -> TransactionProofResult:
        raw_payload = bytes.fromhex(raw_input[2:]).decode("utf-8")
        proof = decode_legacy_proof_payload(raw_payload)
        normalized_provided_hash = normalize_digest(provided_asset_hash)
        normalized_proof_hash = normalize_digest(str(proof["hash"]))
        return TransactionProofResult(
            tx_hash=normalized_tx_hash,
            proof_type="legacy_signed_payload",
            decoded=True,
            proof_valid=bool(proof["proof_valid"]),
            chain_id=tx.get("chainId"),
            block_number=tx.get("blockNumber"),
            from_address=str(tx.get("from")) if tx.get("from") else None,
            to_address=str(tx.get("to")) if tx.get("to") else None,
            explorer_url=f"{self.settings.flare_explorer_base_url.rstrip('/')}/tx/{normalized_tx_hash}",
            asset_hash=normalized_proof_hash,
            signer_address=str(proof["address"]),
            submitter_address=str(tx.get("from")) if tx.get("from") else None,
            signature=str(proof["signature"]),
            public_key=str(proof["public_key"]),
            signature_valid=bool(proof["signature_valid"]),
            public_key_matches=bool(proof["public_key_matches"]),
            provided_asset_hash=normalized_provided_hash,
            asset_hash_matches=(
                normalized_provided_hash == normalized_proof_hash
                if normalized_provided_hash is not None
                else None
            ),
        )
