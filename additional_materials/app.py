import json

from flask import Flask, request, jsonify, render_template
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct

app = Flask(__name__)

RPC_URL = "https://coston2-api.flare.network/ext/C/rpc"
CHAIN_ID = 114

w3 = Web3(Web3.HTTPProvider(RPC_URL))

PRIVATE_KEY = "0xf2e045aa3307bec9596753e4cafd6ec01c153ad7904a1bed653a61b6943570b0"
account = Account.from_key(PRIVATE_KEY)
PUBLIC_KEY = account._key_obj.public_key.to_hex()


def public_key_to_address(public_key_hex):
    normalized = public_key_hex[2:] if public_key_hex.startswith("0x") else public_key_hex
    public_key_bytes = bytes.fromhex(normalized)

    if len(public_key_bytes) == 65 and public_key_bytes[0] == 4:
        public_key_bytes = public_key_bytes[1:]

    if len(public_key_bytes) != 64:
        raise ValueError("Public key must be 64 bytes")

    address_bytes = Web3.keccak(public_key_bytes)[-20:]
    return Web3.to_checksum_address("0x" + address_bytes.hex())


def build_signed_proof(video_hash):
    message = encode_defunct(text=video_hash)
    signature = Web3.to_hex(account.sign_message(message).signature)
    address = public_key_to_address(PUBLIC_KEY)

    return {
        "hash": video_hash,
        "signature": signature,
        "public_key": PUBLIC_KEY,
        "address": address,
    }


def encode_proof_payload(video_hash):
    proof = build_signed_proof(video_hash)
    return f"proof:{json.dumps(proof, separators=(',', ':'))}"


def decode_proof_payload(raw_payload):
    if not raw_payload.startswith("proof:"):
        raise ValueError("Transaction does not contain a signed proof payload")

    proof = json.loads(raw_payload.split("proof:", 1)[1])
    required_fields = {"hash", "signature", "public_key", "address"}

    if not required_fields.issubset(proof):
        raise ValueError("Proof payload is missing required fields")

    message = encode_defunct(text=proof["hash"])
    recovered_address = Account.recover_message(message, signature=proof["signature"])
    derived_address = public_key_to_address(proof["public_key"])

    proof["recovered_address"] = recovered_address
    proof["derived_address"] = derived_address
    proof["signature_valid"] = recovered_address.lower() == proof["address"].lower()
    proof["public_key_matches"] = derived_address.lower() == proof["address"].lower()
    proof["proof_valid"] = proof["signature_valid"] and proof["public_key_matches"]
    return proof


# -----------------------------
# SEND TX (signed proof)
# -----------------------------
def send_tx(video_hash):
    nonce = w3.eth.get_transaction_count(account.address)
    payload = encode_proof_payload(video_hash)

    tx = {
        "to": account.address,
        "value": 0,
        "gas": 200000,
        "gasPrice": w3.to_wei("30", "gwei"),
        "nonce": nonce,
        "chainId": CHAIN_ID,
        "data": Web3.to_hex(text=payload)
    }

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash.hex()


# -----------------------------
# READ TX
# -----------------------------
def get_tx_data(tx_hash):
    tx = w3.eth.get_transaction(tx_hash)
    raw = tx["input"]

    if hasattr(raw, "hex"):
        raw = raw.hex()

    if not raw or raw == "0x":
        raise ValueError("Transaction input is empty")

    hex_data = raw[2:] if isinstance(raw, str) and raw.startswith("0x") else raw
    return bytes.fromhex(hex_data).decode("utf-8")


# -----------------------------
# ROUTES
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/record", methods=["POST"])
def record():
    payload = request.get_json(silent=True) or {}
    video_hash = payload.get("hash")

    if not video_hash:
        return jsonify({"error": "Missing hash"}), 400

    try:
        tx = send_tx(video_hash)
        return jsonify({
            "tx": tx,
            "public_key": PUBLIC_KEY,
            "address": public_key_to_address(PUBLIC_KEY),
        })
    except Exception as exc:
        return jsonify({"error": f"Failed to submit transaction: {exc}"}), 502


@app.route("/tx/<tx_hash>")
def tx(tx_hash):
    normalized_hash = tx_hash if tx_hash.startswith("0x") else f"0x{tx_hash}"

    try:
        if not normalized_hash.startswith("0x") or len(normalized_hash) != 66:
            return jsonify({"error": "Transaction hash must be a 64-character hex string"}), 400

        int(normalized_hash[2:], 16)
    except ValueError:
        return jsonify({"error": "Transaction hash must be a valid hex string"}), 400

    try:
        data = get_tx_data(normalized_hash)
    except Exception as exc:
        return jsonify({"error": f"Failed to read transaction: {exc}"}), 502

    try:
        proof = decode_proof_payload(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": f"Failed to decode proof payload: {exc}"}), 422

    return jsonify(proof)


if __name__ == "__main__":
    app.run(debug=True)
