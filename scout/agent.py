"""
agent.py - event-driven runner for Skeptic Scout.

Default behavior:
  1) read Mantle SPCXx on-chain state
  2) detect narrow triggers
  3) build a skeptic memo
  4) write local markdown artifact(s) — deterministic core, plus an LLM version with --llm

No third-party packages are required for the core (eth-account only for --anchor).
"""
import argparse
import json
from datetime import datetime, timezone

import config
import onchain
import skeptic
import proof as proof_layer
import llm as llm_layer


STATE_FILE = config.DATA / "scout_state.json"


def load_state():
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def detect_triggers(snap, previous):
    """Return the event reasons that justify publishing a memo."""
    reasons = []
    symbol = snap["metadata"]["symbol"]
    transfer_count = snap["wash"]["transfer_count"]
    prev_count = previous.get("transfer_count")
    first_seen = previous.get("symbol") != symbol
    new_transfers = max(0, transfer_count - prev_count) if prev_count is not None else transfer_count

    if first_seen:
        reasons.append(f"신규 추적 자산 감지: {symbol}")
    if new_transfers >= config.THRESHOLDS["min_transfers"]:
        reasons.append(
            f"Transfer 활동 임계치 돌파: +{new_transfers:,}건 "
            f"(threshold {config.THRESHOLDS['min_transfers']:,})"
        )

    wash_score = snap["wash"]["wash_score"]
    prev_wash_score = previous.get("wash_score")
    wash_crossed = (
        first_seen or
        (prev_wash_score is not None and
         prev_wash_score < config.THRESHOLDS["wash_suspicion"] <= wash_score)
    )
    if wash_crossed:
        reasons.append(
            f"wash 의심 점수 {wash_score}/100 "
            f"(threshold {config.THRESHOLDS['wash_suspicion']})"
        )

    top1_share = snap["distribution_full"]["top1_share"]
    prev_top1_share = previous.get("top1_share")
    concentration_crossed = (
        first_seen or
        (prev_top1_share is not None and
         prev_top1_share < config.THRESHOLDS["concentration_top1"] <= top1_share)
    )
    if concentration_crossed:
        reasons.append(
            f"top1 집중도 {top1_share:.1%} "
            f"(threshold {config.THRESHOLDS['concentration_top1']:.0%})"
        )
    return reasons


def render_proof(proof):
    """Proof-of-Analysis 섹션 (T1 서명 + T2 온체인)"""
    if not proof or proof.get("tier") == "unavailable":
        return ["## Proof-of-Analysis",
                "- (비활성) eth-account 미설치 → `pip install eth-account`", ""]
    lines = [
        "## Proof-of-Analysis (온체인 귀속 증명)",
        f"- Agent identity (ERC-8004식): `{proof['signer']}`",
        f"- Memo hash (keccak256): `{proof['memo_hash']}`",
        f"- Signature: `{proof['signature'][:34]}…`",
        f"- Scheme: {proof['scheme']}",
    ]
    on = proof.get("onchain")
    if on and on.get("tier") == "T2-onchain":
        lines.append(f"- **Onchain proof:** [{on['tx']}]({on['explorer']}) "
                     f"(Mantle Sepolia, chain {on['chain_id']})")
        if on.get("mined"):
            lines.append(f"  - mined at block {on.get('block')}")
    elif on and on.get("tier") == "T2-skipped":
        lines.append(f"- Onchain 기록 대기: 테스트넷 지갑 `{on['fund_address']}` "
                     f"충전 필요 (faucet: {on['faucet']})")
    lines.append("")
    return lines


def render_llm(narration):
    """LLM 서술 섹션 (옵션). 결정론 4섹션은 그대로 두고 위에 얹는다."""
    if not narration:
        return []
    if "text" in narration:
        return [
            f"## AI 리서치 서술 (evidence-bound · {narration['provider']}/{narration['model']})",
            "_아래 결정론 섹션의 온체인 근거에만 묶여 생성됨 — 숫자는 코어가 산출._",
            "",
            narration["text"], "",
        ]
    return [f"## AI 서술 (비활성)", f"- {narration.get('error', '키 없음')}", ""]


def render_markdown(memo, triggers, snap, proof=None, narration=None,
                    include_sections=True):
    lines = [
        f"# Skeptic Scout: {memo['symbol']}",
        "",
        f"> {memo['headline']}",
        "",
        memo["thesis"],
        "",
        "## Trigger",
    ]
    for reason in triggers:
        lines.append(f"- {reason}")

    lines.extend([
        "",
        "## Mantle Proof",
        f"- Chain ID: {config.CHAIN_ID}",
        f"- Block: {memo['block']:,}",
        f"- Token: {snap['target']['address']}",
        f"- Explorer: {config.EXPLORER}/token/{snap['target']['address']}",
        "",
    ])

    lines.extend(render_llm(narration))

    # 결정론(코어) 4섹션 — LLM 전용 파일에선 생략 (Claude 서술이 대체)
    if include_sections:
        for section in memo["sections"]:
            lines.extend([f"## {section['title']}", section["verdict"], ""])
            for item in section["evidence"]:
                lines.append(f"- {item}")
            lines.append("")

    lines.extend(render_proof(proof))

    lines.extend([
        "## x402 (설계)",
        "- 위 headline/thesis는 무료 프리뷰, 전체 evidence는 HTTP 402 뒤에 둘 수 있음.",
        "- 페이월 명세: `.well-known/skeptic-scout.agent.json`의 `payments` 참고.",
        "",
        "_Generated by Skeptic Scout, a proof-of-analysis research agent for Mantle RWA._",
    ])
    return "\n".join(lines)


def write_artifact(memo, markdown):
    out = config.DATA / f"skeptic_scout_{memo['symbol']}_{memo['block']}.md"
    out.write_text(markdown, encoding="utf-8")
    return out


def print_summary(memo, triggers, artifact, proof=None):
    print("\n=== Skeptic Scout ===")
    print(memo["headline"])
    print("\nTriggers:")
    for reason in triggers:
        print(f"  - {reason}")
    print(f"\nArtifact: {artifact}")
    if proof and proof.get("tier") != "unavailable":
        print(f"Proof: {proof['tier']} | signer {proof['signer']} | "
              f"hash {proof['memo_hash'][:18]}…")
        on = proof.get("onchain", {})
        if on.get("tier") == "T2-onchain":
            print(f"  Onchain: {on['explorer']}")
        elif on.get("tier") == "T2-skipped":
            print(f"  Onchain skipped: {on['reason']} → fund {on['fund_address']}")


def main():
    parser = argparse.ArgumentParser(description="Run Skeptic Scout once.")
    parser.add_argument("--force", action="store_true", help="publish even if no trigger fired")
    parser.add_argument("--anchor", action="store_true",
                        help="기록: 메모 해시를 Mantle 테스트넷에 온체인 기록(T2)")
    parser.add_argument("--llm", action="store_true",
                        help="LLM(Claude/GPT) 서술 추가 — 키 감지, 없으면 결정론 유지")
    parser.add_argument(
        "--recent",
        action="store_true",
        help="use cached Transfer logs only; run without this once per token first",
    )
    parser.add_argument("--asset", help="등록된 자산 이름 (예: SPCXx)")
    parser.add_argument("--token", help="아무 맨틀 ERC-20 주소 (0x…) — 배포블록 자동탐지")
    args = parser.parse_args()

    target = onchain.resolve_target(asset=args.asset, address=args.token)
    snap = onchain.snapshot(target=target, refresh=not args.recent, verbose=True)
    previous = load_state()
    triggers = detect_triggers(snap, previous)
    if args.force and not triggers:
        triggers = ["강제 실행: demo/manual review"]

    if not triggers:
        print("No trigger fired. Scout stays quiet.")
        return 0

    memo = skeptic.build_memo(snap)
    proof = proof_layer.prove(memo, anchor=args.anchor, wait=args.anchor)
    narration = llm_layer.narrate(memo) if args.llm else None

    # 결과물 1: 파이썬 결정론 코어 버전 (항상 생성, 검증 백본)
    markdown = render_markdown(memo, triggers, snap, proof=proof)
    artifact = write_artifact(memo, markdown)

    # 결과물 2: Claude/GPT 버전 (--llm 성공 시 별도 파일로)
    llm_artifact = None
    if narration and "text" in narration:
        llm_md = render_markdown(memo, triggers, snap, proof=proof,
                                 narration=narration, include_sections=False)
        llm_artifact = config.DATA / \
            f"skeptic_scout_{memo['symbol']}_{memo['block']}_llm.md"
        llm_artifact.write_text(llm_md, encoding="utf-8")

    # 검증 번들 저장 (심사위원이 python scout/proof.py --verify 로 확인)
    if proof and proof.get("tier") != "unavailable":
        bundle_path = config.DATA / f"proof_{memo['symbol']}_{memo['block']}.json"
        proof_layer.save_bundle(memo, proof, bundle_path)

    save_state({
        "symbol": memo["symbol"],
        "block": memo["block"],
        "transfer_count": snap["wash"]["transfer_count"],
        "wash_score": snap["wash"]["wash_score"],
        "top1_share": snap["distribution_full"]["top1_share"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "last_artifact": str(artifact),
    })
    print_summary(memo, triggers, artifact, proof)

    if args.llm:
        if llm_artifact:
            print(f"\n결과물 2 (LLM {narration['provider']}/{narration['model']}): "
                  f"{llm_artifact}")
        elif narration:
            print(f"\nLLM 실패 ({narration.get('error')}) → 결과물 2 생략, 결정론만")
        else:
            print("\nLLM 키 없음 → 결과물 2 생략, 결정론만")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
