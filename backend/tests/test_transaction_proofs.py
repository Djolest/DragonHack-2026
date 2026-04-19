from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient
from web3 import Web3

import app.main as main_module
from app.config import Settings
from app.models import ReceiptPayload, ReceiptRecord, ReceiptSignature, SignedReceiptEnvelope
from app.repository import ReceiptRepository
from app.services.flare_anchor import ANCHOR_ABI, FlareAnchorService
from app.services.receipts import ReceiptService
from app.services.transaction_proofs import (
    FlareTransactionProofService,
    public_key_to_address,
)


TEST_PRIVATE_KEY = "0x" + ("22" * 32)


def make_workspace_temp_path() -> Path:
    base_dir = Path.cwd() / ".test-artifacts"
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / str(uuid4())
    path.mkdir(parents=True, exist_ok=True)
    return path


class FakeEth:
    def __init__(self, tx: dict[str, object]) -> None:
        self.tx = tx

    def get_transaction(self, _: str) -> dict[str, object]:
        return self.tx


class FakeWeb3:
    def __init__(self, tx: dict[str, object]) -> None:
        self.eth = FakeEth(tx)


def build_anchor_input(
    *,
    receipt_id_hash: str,
    receipt_hash: str,
    asset_hash: str,
    storage_uri: str,
) -> str:
    contract = Web3().eth.contract(abi=ANCHOR_ABI)
    return contract.functions.anchorReceipt(
        bytes.fromhex(receipt_id_hash),
        bytes.fromhex(receipt_hash),
        bytes.fromhex(asset_hash),
        storage_uri,
    )._encode_transaction_data()


def test_transaction_proof_service_decodes_anchor_contract_calls() -> None:
    tmp_path = make_workspace_temp_path()
    repository = ReceiptRepository(tmp_path)
    settings = Settings(storage_root=tmp_path)
    receipt_id = "oakproof-session-1"
    receipt_hash = "ab" * 32
    asset_hash = "cd" * 32
    tx_hash = "0x" + ("12" * 32)

    record = ReceiptRecord(
        receipt_id=receipt_id,
        receipt=SignedReceiptEnvelope(
            payload=ReceiptPayload(
                receipt_id=receipt_id,
                capture_id="session-1",
                station_id="station-1",
                asset_id="asset-1",
                captured_at=datetime.now(timezone.utc),
                asset_hash=asset_hash,
                storage_uri="http://127.0.0.1:8100/assets/captures/demo/rgb.mp4",
                media_type="video/mp4",
                metadata={},
            ),
            signature=ReceiptSignature(
                signer_address="0x0000000000000000000000000000000000000001",
                signature="0xdeadbeef",
            ),
        ),
        receipt_hash=receipt_hash,
        signature_valid=True,
        signer_address="0x0000000000000000000000000000000000000001",
        anchored=True,
        anchor_tx_hash=tx_hash,
        anchor_tx_url=f"https://coston2-explorer.flare.network/tx/{tx_hash}",
        anchor_chain_id=114,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        stored_at="",
    )
    repository.save(record)

    receipt_id_hash = Web3.keccak(text=receipt_id).hex()
    tx = {
        "input": build_anchor_input(
            receipt_id_hash=receipt_id_hash,
            receipt_hash=receipt_hash,
            asset_hash=asset_hash,
            storage_uri=record.receipt.payload.storage_uri,
        ),
        "chainId": 114,
        "blockNumber": 321,
        "from": "0x0000000000000000000000000000000000000002",
        "to": "0x0000000000000000000000000000000000000003",
    }
    service = FlareTransactionProofService(
        settings,
        repository,
        web3_factory=lambda _rpc_url: FakeWeb3(tx),
    )

    result = service.get_transaction_proof(tx_hash, provided_asset_hash=asset_hash)

    assert result.proof_type == "anchor_contract"
    assert result.decoded is True
    assert result.proof_valid is True
    assert result.record_found is True
    assert result.record_consistent is True
    assert result.receipt_id == receipt_id
    assert result.asset_hash == asset_hash
    assert result.asset_hash_matches is True


def test_transaction_proof_service_marks_unlinked_anchor_calls_as_decoded_but_not_trusted() -> None:
    tmp_path = make_workspace_temp_path()
    repository = ReceiptRepository(tmp_path)
    settings = Settings(storage_root=tmp_path)
    tx_hash = "0x" + ("56" * 32)
    receipt_id_hash = Web3.keccak(text="missing-receipt").hex()
    receipt_hash = "ab" * 32
    asset_hash = "cd" * 32
    tx = {
        "input": build_anchor_input(
            receipt_id_hash=receipt_id_hash,
            receipt_hash=receipt_hash,
            asset_hash=asset_hash,
            storage_uri="http://127.0.0.1:8100/assets/captures/demo/rgb.mp4",
        ),
        "chainId": 114,
        "blockNumber": 654,
        "from": "0x0000000000000000000000000000000000000002",
        "to": "0x0000000000000000000000000000000000000003",
    }
    service = FlareTransactionProofService(
        settings,
        repository,
        web3_factory=lambda _rpc_url: FakeWeb3(tx),
    )

    result = service.get_transaction_proof(tx_hash, provided_asset_hash=asset_hash)

    assert result.proof_type == "anchor_contract"
    assert result.decoded is True
    assert result.proof_valid is False
    assert result.record_found is False
    assert result.record_consistent is None
    assert result.asset_hash_matches is True


def test_transaction_proof_service_decodes_legacy_signed_payload_transactions() -> None:
    tmp_path = make_workspace_temp_path()
    repository = ReceiptRepository(tmp_path)
    settings = Settings(storage_root=tmp_path)
    tx_hash = "0x" + ("34" * 32)
    account = Account.from_key(TEST_PRIVATE_KEY)
    public_key = account._key_obj.public_key.to_hex()
    video_hash = "ef" * 32
    payload = {
        "hash": video_hash,
        "signature": Web3.to_hex(account.sign_message(encode_defunct(text=video_hash)).signature),
        "public_key": public_key,
        "address": public_key_to_address(public_key),
    }
    tx = {
        "input": Web3.to_hex(text=f"proof:{json.dumps(payload, separators=(',', ':'))}"),
        "chainId": 114,
        "blockNumber": 654,
        "from": account.address,
        "to": account.address,
    }
    service = FlareTransactionProofService(
        settings,
        repository,
        web3_factory=lambda _rpc_url: FakeWeb3(tx),
    )

    result = service.get_transaction_proof(tx_hash, provided_asset_hash=video_hash)

    assert result.proof_type == "legacy_signed_payload"
    assert result.decoded is True
    assert result.proof_valid is True
    assert result.signature_valid is True
    assert result.public_key_matches is True
    assert result.signer_address == payload["address"]
    assert result.asset_hash == video_hash
    assert result.asset_hash_matches is True


def test_health_exposes_manual_anchoring_mode(monkeypatch) -> None:
    tmp_path = make_workspace_temp_path()
    settings = Settings(
        storage_root=tmp_path,
        anchor_on_ingest=False,
        anchor_contract_address="0x0000000000000000000000000000000000000001",
        anchor_private_key=TEST_PRIVATE_KEY,
    )
    repository = ReceiptRepository(tmp_path)

    monkeypatch.setattr(main_module, "settings", settings)
    monkeypatch.setattr(main_module, "repository", repository)
    monkeypatch.setattr(main_module, "receipt_service", ReceiptService(settings, repository))
    monkeypatch.setattr(main_module, "anchor_service", FlareAnchorService(settings))
    monkeypatch.setattr(
        main_module,
        "transaction_proof_service",
        FlareTransactionProofService(settings, repository),
    )

    client = TestClient(main_module.app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["anchoringMode"] == "manual"
    assert response.json()["anchorOnIngest"] is False
    assert response.json()["anchoringEnabled"] is True
    assert response.json()["manualAnchorAvailable"] is True
