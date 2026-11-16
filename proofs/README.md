# StudioNet proofs

Contract address 0x56B6Af18CB55a758EF64C638093f3b0D7c97fDd3

Deployment sealed 4 eligible assignments and scheduled drand round 34011984. The draw selected zero-based rank 2. Separate signing wallets deployed and resolved the roster.

[Workflow](https://github.com/moorisi/beacon-roster/actions/runs/43885175710) · [Verified reads](verified.json) · [Relay 1](https://api.drand.sh/52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971/public/34011984) · [Relay 2](https://drand.cloudflare.com/52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971/public/34011984)

| Outcome | Explorer | Receipt | Agree / disagree / idle |
| --- | --- | --- | --- |
| Immutable eligibility roster sealed to a future round | [Transaction](https://explorer-studio.genlayer.com/tx/0x06d5a6573d9f6fc73f6b2e1c639a195bf40dd22657fb9aa28707d0d555d0e647) | [JSON](deploy-receipt.json) | 3 / 0 / 2 |
| Draw before the scheduled round rejected | [Transaction](https://explorer-studio.genlayer.com/tx/0xafc0ed8a4b490cbc7ba34b1e6478fe9b6780eac0a841c1a5d86edeca82ab2709) | [JSON](early-receipt.json) | 3 / 0 / 2 |
| Exact drand round used to store a complete assignment | [Transaction](https://explorer-studio.genlayer.com/tx/0xd0a2eb66cc47a6c1368e05018b9bbbff922b1f53102b8cbff64983f61267c008) | [JSON](settle-receipt.json) | 3 / 0 / 2 |
| Second draw rejected | [Transaction](https://explorer-studio.genlayer.com/tx/0xd0e0aa8abf73c8503c9f8579b315cb4a4b79d5234420da41b2e26c920158537d) | [JSON](redraw-receipt.json) | 3 / 0 / 2 |

All four receipts finalized with MAJORITY_AGREE. The independent enumerator checked each rank, and every selected reviewer was eligible and appeared exactly once.

| Task | Reviewer |
| --- | --- |
| abstract | dev |
| benchmark | amy |
| data | ben |
| methods | cam |

Source revision 9defbff488c63479e801c9d71cc247b77dae2d90

Contract SHA-256 414ca5a738941c64ca45481f29d10a81226e93fbf78059fe5d351fa2a9301ff7
