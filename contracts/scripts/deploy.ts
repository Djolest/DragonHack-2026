import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import hre from "hardhat";

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  if (!deployer) {
    throw new Error("No deployer account configured. Set DEPLOYER_PRIVATE_KEY in contracts/.env.");
  }

  const factory = await hre.ethers.getContractFactory("OAKProofAnchor");
  const contract = await factory.deploy();
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  const network = await hre.ethers.provider.getNetwork();
  const output = {
    network: hre.network.name,
    chainId: Number(network.chainId),
    address,
    deployer: deployer.address,
    deployedAt: new Date().toISOString()
  };

  const deploymentsDir = join(process.cwd(), "deployments");
  mkdirSync(deploymentsDir, { recursive: true });
  writeFileSync(
    join(deploymentsDir, `${hre.network.name}.json`),
    JSON.stringify(output, null, 2),
    "utf-8"
  );

  console.log(`OAKProofAnchor deployed to ${address} on ${hre.network.name}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
