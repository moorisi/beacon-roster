# BeaconRoster — Future-beacon reviewer assignment

**Category** Builder → Intelligent Contracts

BeaconRoster uses a future public drand round to assign reviewers to tasks with declared eligibility constraints. Deployment freezes the roster and fixes a round at least 180 seconds ahead. The leader and validators independently fetch that exact round through two relays and require identical round, signature and randomness data. The contract checks the signature digest and relies on relay agreement for authenticity. Subset dynamic programming counts all complete assignments. Rejection sampling and rank selection assign one eligible reviewer to each task, with no repeats. The StudioNet proof independently enumerated 4 feasible alternatives, reproduced the selected rank, and verified early-draw and redraw rejections. All four receipts finalized with MAJORITY_AGREE.

- [GenLayer contract](contracts/beacon_roster.py)
- [StudioNet deployment](https://explorer-studio.genlayer.com/tx/0x06d5a6573d9f6fc73f6b2e1c639a195bf40dd22657fb9aa28707d0d555d0e647)
- [Assignment transaction](https://explorer-studio.genlayer.com/tx/0xd0a2eb66cc47a6c1368e05018b9bbbff922b1f53102b8cbff64983f61267c008)
- [Transaction receipts and state checks](proofs/README.md)
