// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract OAKProofAnchor {
    struct AnchorRecord {
        bytes32 receiptDigest;
        bytes32 assetDigest;
        string storageUri;
        address submitter;
        uint64 anchoredAt;
        bool exists;
    }

    mapping(bytes32 => AnchorRecord) private anchors;

    event ReceiptAnchored(
        bytes32 indexed receiptIdHash,
        bytes32 indexed receiptDigest,
        bytes32 indexed assetDigest,
        string storageUri,
        address submitter
    );

    error EmptyStorageUri();
    error InvalidDigest();
    error ReceiptAlreadyAnchored(bytes32 receiptIdHash);

    function anchorReceipt(
        bytes32 receiptIdHash,
        bytes32 receiptDigest,
        bytes32 assetDigest,
        string calldata storageUri
    ) external {
        if (receiptIdHash == bytes32(0) || receiptDigest == bytes32(0) || assetDigest == bytes32(0)) {
            revert InvalidDigest();
        }
        if (bytes(storageUri).length == 0) {
            revert EmptyStorageUri();
        }
        if (anchors[receiptIdHash].exists) {
            revert ReceiptAlreadyAnchored(receiptIdHash);
        }

        anchors[receiptIdHash] = AnchorRecord({
            receiptDigest: receiptDigest,
            assetDigest: assetDigest,
            storageUri: storageUri,
            submitter: msg.sender,
            anchoredAt: uint64(block.timestamp),
            exists: true
        });

        emit ReceiptAnchored(
            receiptIdHash,
            receiptDigest,
            assetDigest,
            storageUri,
            msg.sender
        );
    }

    function getAnchor(bytes32 receiptIdHash) external view returns (AnchorRecord memory) {
        return anchors[receiptIdHash];
    }
}
