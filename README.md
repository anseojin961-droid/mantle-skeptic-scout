# Skeptic Scout

An on-chain research agent for Mantle RWA. It reads tokenized-equity state on Mantle (starting with `SPCXx`, the SpaceX xStock) and writes a skeptical memo instead of a hype summary. Every number in the memo comes from on-chain data; nothing is invented.

## Quick start (for reviewers)

```powershell
python scout\agent.py --force                                   # live Mantle read -> SPCXx memo
pip install -r requirements-proof.txt                           # dependency for proof verification
python scout\proof.py --verify examples\SPCXx_demo_proof.json   # verify the on-chain proof
type examples\SPCXx_demo_memo.md                                # the canonical example memo
```

What you should see: a skeptical SPCXx memo (`발행 30,000 / 실유통 <1% / wash 의심 …`); three PASS lines for the proof check (hash, signer, on-chain calldata); and the full four-section memo with its `Onchain proof: 0x…` link.

No API key is needed. The research engine uses only the Python standard library; `eth-account` is required only for proof verification and re-anchoring. On a fresh clone the first command builds the SPCXx Transfer cache from Mantle RPC (later runs only fetch new blocks).

## How it reads data

Each run asks Mantle for the latest block, pulls Transfer history up to that block, and computes supply, holders, float, and wash indicators from it. Every memo records the block height it was built at, so the numbers are reproducible by anyone querying the same address. Past history is cached so later runs only fetch new blocks; `--recent` reuses the cache without a network refresh (for fast demos, not an offline mode).

## Deterministic core, optional LLM

The memo body is built by rule from the on-chain numbers, so a language model can never invent a figure. An LLM layer is optional and sits on top of that evidence:

```powershell
$env:ANTHROPIC_API_KEY="sk-ant-..."   # or $env:OPENAI_API_KEY="sk-..."
python scout\agent.py --force --llm    # the model narrates, bound to the on-chain evidence
```

`scout/llm.py` picks the provider from whichever key is set (model id is configured in `.env` / `config.py`), passes it only the evidence the core produced, and writes a separate narrated memo. With no key, or on an API error, it falls back to the deterministic memo.

## Design notes

- Forces four sections on every memo: bear case, wash-trade suspicion, who benefits, counter-narrative.
- Goes deep on one asset (SPCXx) rather than shallow on many.
- Acts only when a trigger crosses threshold (new asset, transfer activity, concentration, wash score); otherwise it stays quiet.
- Packaged as a skill under the [`mantle-xyz/mantle-skills`](https://github.com/mantle-xyz/mantle-skills) directory layout (`skills/skeptic-scout/` with `SKILL.md`, `agents/openai.yaml`, `references/`, `assets/`). It also ships an ERC-8004-style identity/agent card and an x402 paywall hook (the x402 part is designed, not executed).

## Working example

[`examples/SPCXx_demo_memo.md`](examples/SPCXx_demo_memo.md) is a memo generated from a live Mantle read. That run showed 30,000 SPCXx supply, real float under 1% (after separating the issuer/treasury wallet), a couple dozen holders, and a high wash-suspicion score. The one-line read: 발행은 끝났고 유통은 시작도 안 했다 (issuance is done; distribution hasn't started). Numbers move slightly between runs because the data is live; each memo cites its block height.

## Proof-of-Analysis

Every memo is signed and anchored so authorship and timing are checkable.

- The canonical memo payload (the structured body, not the rendered markdown) is keccak256-hashed and signed (EIP-191) by the agent's Ethereum identity.
- The hash is written to Mantle Sepolia as transaction calldata, which timestamps it on a public chain.

To verify:

```powershell
python scout\proof.py --verify examples\SPCXx_demo_proof.json
```

It runs three checks: re-hash the stored canonical payload and compare to `memo_hash` (changing one character of the memo fails this); recover the signer from the signature and compare to the agent identity; fetch the Mantle Sepolia transaction and compare its calldata to `memo_hash`. The bundle carries the exact canonical payload, so the hash is reproducible offline.

## Status

- Working with no API key (stdlib only): Mantle reads, treasury/float separation, skeptic memo, local markdown output.
- Proof T1 (needs `eth-account`): keccak256 hash, EIP-191 signature, tamper-evident verification via `proof.py --verify`.
- Proof T2 (live on Mantle Sepolia): the memo hash is anchored on-chain. Example tx [`0x5cb554…be37`](https://sepolia.mantlescan.xyz/tx/0x5cb5545b2cb2620ba11f3a266ddb75913efc13c750558c25ed737af8cc97be37) (calldata equals the memo hash).
- x402 paywall: designed (see the `payments` block in the agent card), not executed.

## Running other tokens

SPCXx is the featured, cached case; run it for demos and review. The same engine works on any Mantle xStock by name, or any ERC-20 by address:

```powershell
python scout\agent.py --asset TSLAx     # registered name
python scout\agent.py --token 0x...     # any Mantle ERC-20 (deploy block auto-detected)
```

Registered names (Mantle xStocks lineup, addresses verified on-chain): `SPCXx`, `TSLAx`, `NVDAx`, `AAPLx`, `METAx`, `GOOGLx`, `MSTRx`, `HOODx`, `SPYx`, `QQQx`, `CRCLx`.

The first run on a non-SPCXx asset builds a full-history cache from its deploy block, which can take a while for older assets and depends on public-RPC responsiveness; after that it is cached. The accurate claim is that SPCXx is proven and the engine extends to the lineup, not that the whole lineup analyzes instantly.

## Files

- `scout/onchain.py` — Mantle RPC reads, Transfer log scan, holder distribution, wash heuristics.
- `scout/skeptic.py` — deterministic memo builder.
- `scout/agent.py` — trigger detection, markdown output (deterministic core plus optional LLM version).
- `scout/llm.py` — optional LLM narration bound to the evidence (Claude/GPT, stdlib HTTP).
- `scout/proof.py` — canonical hash, signing, on-chain anchor, `--verify`.
- `skills/skeptic-scout/` — the skill in `mantle-skills` layout (`SKILL.md`, `agents/openai.yaml`, `references/methodology.md`, `assets/xstocks.json`).
- `.well-known/skeptic-scout.agent.json` — ERC-8004-style discovery/validation metadata.
- `evals/specs/skeptic-scout.yaml` — eval spec in the `mantle-skills` convention (3 cases; spec only, not benchmarked).
- `examples/` — the canonical memo and its verifiable proof bundle.

## Output contract

Every memo includes the four sections (bear case, wash-trade suspicion with quantitative evidence, who benefits, counter-narrative) and cites chain id, block number, token address, and the evidence behind each numeric claim.
