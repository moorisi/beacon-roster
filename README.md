# BeaconRoster

BeaconRoster assigns one reviewer to each task, respects declared eligibility, and uses every reviewer exactly once. It samples from the full set of eligible assignments. The choice of reviewer for one task accounts for the completions it leaves for every other task.

Deploy with a single string consisting of `br1:` followed by a JSON object with `tasks`, `reviewers`, and `eligible`. There must be 2–10 distinct tasks and an equal number of distinct reviewers. Each eligibility list names the reviewers allowed to handle that task. The constructor rejects rosters with no complete assignment. It sorts the lists, seals the roster, and selects the first drand quicknet round scheduled at least 180 seconds after the GenLayer transaction timestamp. The caller cannot provide a round or edit the roster.

Anyone can call `draw()` after the round is due. The leader and each validator fetch that exact round from the drand API and Cloudflare relay. Both relay responses must agree on the round, signature bytes, and randomness, and the randomness must equal SHA-256 of the signature. Validators compare the independently observed record against the leader's record. Relay unavailability or disagreement leaves the draw pending on the same round. The contract relies on relay agreement and checks the signature digest. BLS signature verification is outside the onchain trust model.

Subset dynamic programming counts feasible completions. The contract hashes the agreed beacon with the canonical roster digest and round, then uses rejection sampling to remove modulo bias. It un-ranks the selected value in lexicographic order, giving each feasible assignment one rank. The contract treats the hash output as uniform. The resulting assignment, rank, and beacon record are stored together. Future calls cannot redraw. Consumers should commit to an instance before its round to avoid selection across multiple instances.

| Method | Behavior |
| --- | --- |
| `get_state()` | Returns the sealed roster, match count, scheduled round, and eventual draw result. |
| `assignment_at(rank)` | Enumerates the assignment for a valid rank before or after the draw. |
| `draw()` | Finalizes the assignment using the sealed beacon round. |

[drand quicknet and public relays](https://docs.drand.love/developer/) · [GenLayer transaction context](https://docs.genlayer.com/developers/intelligent-contracts/features/transaction-context) · [GenLayer web access](https://docs.genlayer.com/developers/intelligent-contracts/features/web-access)

## Verification

```sh
pip install -r requirements-dev.txt
genvm-lint download --version v0.2.16
genvm-lint check contracts/beacon_roster.py
python -m pytest tests/direct -q
npm ci
node --test tests/rpc-preflight.test.cjs
```

The hosted proof deploys a four-task example on StudioNet. A second signer attempts an early call and later settles after the scheduled round. An independent enumerator checks every feasible assignment, verifies the live beacon from both relays, and derives the expected rank and final assignment. The proof also checks the exact revert on redraw and the fresh deployed source bytes. Generic CLI transport is reused under MIT.
