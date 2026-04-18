from eth_account import Account
from web3 import Web3

from ..config import Settings
from ..models import AnchorResult, ReceiptRecord

ANCHOR_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "receiptIdHash", "type": "bytes32"},
            {"internalType": "bytes32", "name": "receiptDigest", "type": "bytes32"},
            {"internalType": "bytes32", "name": "assetDigest", "type": "bytes32"},
            {"internalType": "string", "name": "storageUri", "type": "string"},
        ],
        "name": "anchorReceipt",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


class FlareAnchorService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_enabled(self) -> bool:
        return bool(self.settings.anchor_contract_address and self.settings.anchor_private_key)

    def anchor(self, record: ReceiptRecord) -> AnchorResult:
        if record.anchored and record.anchor_tx_hash and record.anchor_tx_url:
            return AnchorResult(
                receipt_id=record.receipt_id,
                anchored=True,
                tx_hash=record.anchor_tx_hash,
                tx_url=record.anchor_tx_url,
                chain_id=record.anchor_chain_id or self.settings.flare_chain_id,
            )

        if not self.is_enabled():
            raise RuntimeError(
                "Anchoring is disabled. Configure BACKEND_ANCHOR_CONTRACT_ADDRESS and BACKEND_ANCHOR_PRIVATE_KEY."
            )

        w3 = Web3(Web3.HTTPProvider(self.settings.flare_rpc_url))
        account = Account.from_key(self.settings.anchor_private_key)
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(self.settings.anchor_contract_address),
            abi=ANCHOR_ABI,
        )

        tx = contract.functions.anchorReceipt(
            w3.keccak(text=record.receipt_id),
            bytes.fromhex(record.receipt_hash),
            bytes.fromhex(record.receipt.payload.asset_hash),
            record.receipt.payload.storage_uri,
        ).build_transaction(
            {
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "chainId": self.settings.flare_chain_id,
                "gas": self.settings.anchor_gas_limit,
                "gasPrice": w3.eth.gas_price,
            }
        )
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=self.settings.anchor_private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_receipt = w3.eth.wait_for_transaction_receipt(
            tx_hash,
            timeout=self.settings.anchor_timeout_seconds,
        )
        if tx_receipt.status != 1:
            raise RuntimeError("Anchor transaction reverted on chain.")

        tx_hex = tx_hash.hex()
        return AnchorResult(
            receipt_id=record.receipt_id,
            anchored=True,
            tx_hash=tx_hex,
            tx_url=f"{self.settings.flare_explorer_base_url.rstrip('/')}/tx/{tx_hex}",
            chain_id=self.settings.flare_chain_id,
        )
