# IBM Bob Task Runs & Governance Evidence

This directory contains verifiable task execution artifacts from **IBM Bob** (watsonx Code Assistant), utilized under governed development for the **Agentic Cinema Blockbuster Hackathon (IBM Track)**.

## Structure & Provenance

Each governed execution is preserved as a prompt/result pair along with the task ledger:

- `*.prompt.txt`: The specification provided to the IBM Bob shell.
- `*.result.json`: The machine-readable execution result returned by IBM Bob, containing the unique `task_id`, execution status, tool calls, and metadata.
- [`coins-ledger.md`](./coins-ledger.md): The chronological accounting ledger of all task runs, tracking date, `task_id`, Bobcoins spent, and purpose.

## Audit Correlation

The ledger maps directly to the result files via `task_id`:

- `af0f3e75280acaa31eb8668d2f29be79` ↔ `20260907-031405.result.json` (Headless verification)
- `e1935a4d4dfe486aa3290acaa2f66f57` ↔ `20260907-043704.result.json` (Core schemas & test foundation)
- `0e429ba7be89964cc933decda59ed8c9` ↔ `20260907-194740.result.json` (Contract-Intake test corpus)
- `97bf505e1b45efb2534c0c3ad64effbc` ↔ `20260907-195344.result.json` (Cryptographic audit-chain hardening)
- `9887e3d449c51020280c8b914a602fcd` ↔ `20260907-200924.result.json` (Multi-title clause test corpus)

## Summary

- **Total Governed Runs:** 5
- **Total Bobcoin Spend:** 5.803 Coins (Trial Budget: 50.0)
- **Runtime Verification:** Exposed in-app via the **IBM Bob Governance** modal and the `/api/bob-audit` endpoint.
