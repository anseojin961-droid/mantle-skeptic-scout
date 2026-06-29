# Skeptic Scout — Methodology (reference)

Supporting notes the skill leans on when reasoning. Keep claims bound to these.

## The four commandments

1. **Skeptic, not Hype** — surface the signals a bull narrative hides.
2. **Narrow, not Broad** — go deep on one asset (SPCXx) so the analysis is concrete.
3. **Event-driven, not Polling** — act only when a trigger crosses threshold.
4. **Full-stack Mantle standards** — SKILL.md skill, on-chain anchor, ERC-8004-style identity, x402 hook.

## Issuer treasury vs. real float (the core correction)

Raw "top-1 holds 99%+" is *not* automatically a manipulation flag. Procedure:
1. Reconstruct balances from the full Transfer history (mint `0x0→`, burn `→0x0`).
2. Find the dominant **mint-recipient** wallet and label it via `eth_getCode` (EOA vs contract).
3. If that wallet holds the bulk and barely trades, treat it as **issuer treasury (un-distributed inventory)** — separate it out.
4. Report concentration/HHI on the remaining **float**, and state float as a share of supply.

Result for SPCXx: ~99%+ sits in the issuer EOA → real float < 1% of supply. "Issuance done; distribution not started."

## Wash-trade suspicion (heuristic, not proof)

Score 0–100 from transparent components, always shown as evidence, never as a verdict:
- **round-trip ratio** — A→B then B→A at the same size,
- **address diversity** — unique addresses ÷ transfer count (low = concentrated),
- **touch concentration** — share of transfers involving the top-5 addresses.

Contextualize: note how little the treasury participates, so the churn is read against the *thin float*, not the locked inventory.

## Proof-of-Analysis

- Hash the **canonical memo payload** (structured body, not rendered markdown) with keccak256.
- Sign with the agent's stable Ethereum identity (EIP-191).
- With `--anchor`, write the hash to Mantle Sepolia as tx calldata (the example bundle is pre-anchored).
- Anyone verifies with `proof.py --verify`: hash re-computation, signer recovery, on-chain calldata match.
