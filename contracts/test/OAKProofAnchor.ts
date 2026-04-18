import { expect } from "chai";
import { anyValue } from "@nomicfoundation/hardhat-chai-matchers/withArgs";
import { ethers } from "hardhat";

describe("OAKProofAnchor", function () {
  it("stores a new anchor record", async function () {
    const factory = await ethers.getContractFactory("OAKProofAnchor");
    const contract = await factory.deploy();
    await contract.waitForDeployment();

    const receiptIdHash = ethers.keccak256(ethers.toUtf8Bytes("oakproof-receipt-1"));
    const receiptDigest = ethers.sha256(ethers.toUtf8Bytes("payload"));
    const assetDigest = ethers.sha256(ethers.toUtf8Bytes("asset"));
    const storageUri = "http://127.0.0.1:8100/assets/captures/20260418/demo.svg";

    await expect(contract.anchorReceipt(receiptIdHash, receiptDigest, assetDigest, storageUri))
      .to.emit(contract, "ReceiptAnchored")
      .withArgs(receiptIdHash, receiptDigest, assetDigest, storageUri, anyValue);

    const stored = await contract.getAnchor(receiptIdHash);
    expect(stored.exists).to.equal(true);
    expect(stored.receiptDigest).to.equal(receiptDigest);
    expect(stored.assetDigest).to.equal(assetDigest);
    expect(stored.storageUri).to.equal(storageUri);
  });

  it("rejects duplicate anchors", async function () {
    const factory = await ethers.getContractFactory("OAKProofAnchor");
    const contract = await factory.deploy();
    await contract.waitForDeployment();

    const receiptIdHash = ethers.keccak256(ethers.toUtf8Bytes("oakproof-receipt-2"));
    const receiptDigest = ethers.sha256(ethers.toUtf8Bytes("payload"));
    const assetDigest = ethers.sha256(ethers.toUtf8Bytes("asset"));
    const storageUri = "http://127.0.0.1:8100/assets/captures/20260418/demo.svg";

    await contract.anchorReceipt(receiptIdHash, receiptDigest, assetDigest, storageUri);

    await expect(
      contract.anchorReceipt(receiptIdHash, receiptDigest, assetDigest, storageUri)
    ).to.be.revertedWithCustomError(contract, "ReceiptAlreadyAnchored");
  });
});
