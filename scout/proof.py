"""
proof.py — Proof-of-Analysis 레이어

리서처의 고질병: "내가 먼저 분석했는데 남이 베껴감."
Scout는 메모를 생성할 때 증명을 함께 만든다.

  T1 (서명, 의존성: eth-account):
    - 메모를 정규화(canonical) → keccak256 해시
    - 에이전트 키로 서명 → "이 분석은 0x…의 것" (ERC-8004식 신원)
    - 지갑/가스 불필요. 항상 작동.

  T2 (온체인 기록, 추가로 테스트넷 가스 필요):
    - 해시를 Mantle Sepolia 테스트넷에 tx로 기록 → "Onchain proof: 0xTX"
    - 잔액 0이면 faucet 안내 후 graceful degrade. 메인넷 키는 절대 안 씀.
"""
import json
import time
import urllib.request

import config

try:
    from eth_account import Account
    from eth_account.messages import encode_defunct
    from eth_utils import keccak, to_hex
    _HAS_ETH = True
except ImportError:
    _HAS_ETH = False


# ── 메모 정규화 + 해시 ────────────────────────────────────
def canonical_bytes(memo):
    """서명 대상이 되는 결정론적 바이트열. 같은 메모 → 같은 해시."""
    payload = {
        "symbol": memo["symbol"],
        "block": memo["block"],
        "headline": memo["headline"],
        "thesis": memo["thesis"],
        "sections": [
            {"title": s["title"], "verdict": s["verdict"],
             "evidence": list(s["evidence"])}
            for s in memo["sections"]
        ],
    }
    return json.dumps(payload, ensure_ascii=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_str(memo):
    return canonical_bytes(memo).decode("utf-8")


def memo_hash(memo):
    return to_hex(keccak(canonical_bytes(memo)))


def hash_of_canonical(canonical):
    """저장된 canonical 문자열로부터 해시 재계산 (검증용)."""
    return to_hex(keccak(canonical.encode("utf-8")))


# ── 테스트넷 지갑 (버린셈) ────────────────────────────────
def load_or_create_wallet():
    if config.WALLET_FILE.exists():
        d = json.loads(config.WALLET_FILE.read_text(encoding="utf-8"))
        return Account.from_key(d["private_key"])
    acct = Account.create()
    config.WALLET_FILE.write_text(json.dumps({
        "address": acct.address,
        "private_key": acct.key.hex(),
        "network": "mantle-sepolia-testnet",
        "chain_id": config.TESTNET["chain_id"],
        "warning": "TESTNET ONLY. Never fund with real assets. Gitignored.",
    }, indent=2), encoding="utf-8")
    return acct


# ── 테스트넷 RPC ──────────────────────────────────────────
def _rpc(method, params):
    payload = json.dumps({"jsonrpc": "2.0", "method": method,
                          "params": params, "id": 1}).encode()
    req = urllib.request.Request(
        config.TESTNET["rpc"], data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=config.TIMEOUT) as r:
        d = json.loads(r.read())
    if "error" in d:
        raise RuntimeError(f"testnet RPC error: {d['error']}")
    return d["result"]


def balance_wei(addr):
    return int(_rpc("eth_getBalance", [addr, "latest"]), 16)


def onchain_calldata(txhash):
    """테스트넷에 기록된 tx의 calldata(input) 반환 — 온체인 대조 검증용."""
    tx = _rpc("eth_getTransactionByHash", [txhash])
    return tx["input"] if tx else None


# ── T1: 서명 ──────────────────────────────────────────────
def sign_memo(memo, acct):
    h = memo_hash(memo)
    sig = acct.sign_message(encode_defunct(hexstr=h))
    return {
        "tier": "T1-signed",
        "memo_hash": h,
        "signer": acct.address,
        "signature": to_hex(sig.signature),
        "scheme": "EIP-191 personal_sign + keccak256(canonical memo)",
    }


# ── 검증: 누구나 서명↔신원 일치 확인 가능 ────────────────
def verify_memo(memo, proof):
    """메모를 다시 해시하고 서명에서 서명자를 복원해 신원과 대조."""
    expected_hash = memo_hash(memo)
    if expected_hash.lower() != proof["memo_hash"].lower():
        return {"ok": False, "reason": "해시 불일치(메모가 변조됨)"}
    recovered = Account.recover_message(
        encode_defunct(hexstr=proof["memo_hash"]),
        signature=proof["signature"])
    ok = recovered.lower() == proof["signer"].lower()
    return {"ok": ok, "recovered": recovered, "claimed": proof["signer"],
            "reason": "서명자 일치" if ok else "서명자 불일치"}


# ── T2: 온체인 기록 ───────────────────────────────────────
def anchor_onchain(proof, acct):
    """해시를 self-send tx의 calldata로 Mantle 테스트넷에 영구 기록."""
    net = config.TESTNET
    bal = balance_wei(acct.address)
    if bal == 0:
        return {
            "tier": "T2-skipped",
            "reason": "테스트넷 잔액 0 — 지갑 충전 필요",
            "fund_address": acct.address,
            "faucet": net["faucet"],
        }
    nonce = int(_rpc("eth_getTransactionCount", [acct.address, "pending"]), 16)
    gas_price = int(_rpc("eth_gasPrice", []), 16)
    tx = {
        "to": acct.address,           # self-send 0원
        "value": 0,
        "nonce": nonce,
        "gas": 100000,
        "gasPrice": gas_price,
        "data": proof["memo_hash"],   # 32바이트 해시를 calldata로
        "chainId": net["chain_id"],
    }
    signed = acct.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    txhash = _rpc("eth_sendRawTransaction", [to_hex(raw)])
    return {
        "tier": "T2-onchain",
        "tx": txhash,
        "explorer": f"{net['explorer']}/tx/{txhash}",
        "chain_id": net["chain_id"],
        "network": "mantle-sepolia-testnet",
    }


def wait_receipt(txhash, timeout=90):
    """tx 채굴 대기 (선택적). 영수증 or None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        rcpt = _rpc("eth_getTransactionReceipt", [txhash])
        if rcpt:
            return rcpt
        time.sleep(3)
    return None


# ── 검증 번들 저장/검증 (심사위원 UX) ───────────────────
def save_bundle(memo, proof, path):
    """검증에 필요한 모든 것을 한 파일에 저장.
    핵심: 해시 대상인 'canonical payload'를 그대로 보관 →
    누구나 재해시해서 메모 변조 여부를 확인할 수 있다."""
    bundle = {
        "canonical": canonical_str(memo),   # 해시된 정확한 바이트열(=메모 본문, 마크다운 아님)
        "memo_hash": proof["memo_hash"],
        "signer": proof["signer"],
        "signature": proof["signature"],
        "scheme": proof["scheme"],
        "onchain": proof.get("onchain"),
    }
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def verify_bundle(bundle, check_onchain=True):
    """3단 검증: (1) 해시 재계산, (2) 서명자 복원, (3) 온체인 calldata 대조."""
    results = []

    # (1) canonical을 재해시해서 memo_hash와 일치하는가 (메모 변조 탐지)
    recomputed = hash_of_canonical(bundle["canonical"])
    h_ok = recomputed.lower() == bundle["memo_hash"].lower()
    results.append(("해시 재계산", h_ok,
                    f"{recomputed[:18]}… == 기록 {bundle['memo_hash'][:18]}…"))

    # (2) 서명에서 서명자 복원 → 신원 일치 (작성자 귀속)
    recovered = Account.recover_message(
        encode_defunct(hexstr=bundle["memo_hash"]),
        signature=bundle["signature"])
    s_ok = recovered.lower() == bundle["signer"].lower()
    results.append(("서명자 복원", s_ok,
                    f"{recovered} == 신원 {bundle['signer']}"))

    # (3) 온체인 tx의 calldata가 memo_hash와 일치 (영구 기록 대조)
    on = bundle.get("onchain") or {}
    if check_onchain and on.get("tier") == "T2-onchain":
        cd = onchain_calldata(on["tx"])
        c_ok = cd is not None and cd.lower() == bundle["memo_hash"].lower()
        results.append(("온체인 calldata 대조", c_ok,
                        f"tx {on['tx'][:18]}… calldata == memo_hash"))

    ok = all(r[1] for r in results)
    return {"ok": ok, "checks": results}


# ── 통합: 메모 → 증명 ─────────────────────────────────────
def prove(memo, anchor=False, wait=False):
    if not _HAS_ETH:
        return {"tier": "unavailable",
                "reason": "eth-account 미설치 (pip install eth-account)"}
    acct = load_or_create_wallet()
    proof = sign_memo(memo, acct)
    if anchor:
        on = anchor_onchain(proof, acct)
        proof.update({"onchain": on})
        if wait and on.get("tier") == "T2-onchain":
            rcpt = wait_receipt(on["tx"])
            proof["onchain"]["mined"] = bool(rcpt)
            if rcpt:
                proof["onchain"]["block"] = int(rcpt["blockNumber"], 16)
    return proof


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scout Proof-of-Analysis")
    parser.add_argument("--anchor", action="store_true",
                        help="해시를 Mantle 테스트넷에 실제 기록")
    parser.add_argument("--wait", action="store_true", help="tx 채굴 대기")
    parser.add_argument("--verify", metavar="BUNDLE.json",
                        help="저장된 proof 번들을 검증 (해시·서명·온체인)")
    args = parser.parse_args()

    if not _HAS_ETH:
        print("eth-account 필요: pip install eth-account")
        raise SystemExit(1)

    # 검증 모드: 심사위원이 번들 하나로 모든 주장을 확인
    if args.verify:
        from pathlib import Path
        bundle = json.loads(Path(args.verify).read_text(encoding="utf-8"))
        res = verify_bundle(bundle)
        print(f"=== Proof 검증: {args.verify} ===")
        for name, ok, detail in res["checks"]:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name} — {detail}")
        print(f"\n결과: {'✅ 모든 검증 통과' if res['ok'] else '❌ 검증 실패'}")
        raise SystemExit(0 if res["ok"] else 1)

    acct = load_or_create_wallet()
    bal = balance_wei(acct.address)
    print(f"에이전트 지갑(테스트넷 전용): {acct.address}")
    print(f"테스트넷 잔액: {bal/1e18:.6f} MNT")
    if bal == 0:
        print(f"충전 필요 → faucet: {config.TESTNET['faucet']}")
        print(f"  이 주소로 받기: {acct.address}")

    import onchain, skeptic
    snap = onchain.snapshot(refresh=False, verbose=False)
    memo = skeptic.build_memo(snap)
    proof = prove(memo, anchor=args.anchor, wait=args.wait)
    print("\n=== Proof ===")
    print(json.dumps(proof, ensure_ascii=False, indent=2))
