import hashlib
import json
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct

from .models import ReceiptPayload, ReceiptSignature


def canonical_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def payload_message(payload: ReceiptPayload) -> str:
    return canonical_json(payload.model_dump(mode="json"))


def payload_digest_hex(payload: ReceiptPayload) -> str:
    return hashlib.sha256(payload_message(payload).encode("utf-8")).hexdigest()


def sign_payload(payload: ReceiptPayload, private_key: str) -> ReceiptSignature:
    message = encode_defunct(text=payload_message(payload))
    account = Account.from_key(private_key)
    signed = account.sign_message(message)
    return ReceiptSignature(
        scheme="eip191",
        signer_address=account.address,
        signature=signed.signature.hex(),
    )
