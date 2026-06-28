"""
onchain.py — 맨틀 온체인 read 모듈 (표준 라이브러리만)

하는 일:
  1) ERC-20 메타데이터 read (name/symbol/decimals/totalSupply)
  2) Transfer 이벤트 전체 히스토리 수집 (10k 블록 청크) — 캐시 지원
  3) Transfer로부터 잔액 재구성 → 홀더 분산 지표
  4) wash trade 의심 지표 (왕복 거래·소수 참여자·LP 집중) 추정

설계 원칙: 단정하지 않는다. 점수와 '근거(evidence)'를 함께 내보낸다.
"""
import json
import http.client
import time
import urllib.error
import urllib.request
from collections import defaultdict

import config


# ── 저수준 RPC (일시적 오류 재시도) ───────────────────────
def rpc(method, params, retries=4):
    payload = json.dumps({"jsonrpc": "2.0", "method": method,
                          "params": params, "id": 1}).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                config.RPC_URL, data=payload,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=config.TIMEOUT) as r:
                d = json.loads(r.read())
            if "error" in d:
                raise RuntimeError(f"RPC error: {d['error']}")
            return d["result"]
        except (urllib.error.HTTPError, urllib.error.URLError,
                http.client.RemoteDisconnected, TimeoutError) as e:
            last = e  # 503/429/타임아웃 등 일시적 오류 → backoff 후 재시도
            time.sleep(0.5 * (2 ** attempt))
    raise last


def _int(hexstr):
    return int(hexstr, 16)


def _decode_string(hexdata):
    """ABI 인코딩된 string 반환값을 디코드 (offset+length+bytes)"""
    raw = bytes.fromhex(hexdata[2:])
    if len(raw) < 64:
        return raw.decode("utf-8", "ignore").strip("\x00")
    length = int.from_bytes(raw[32:64], "big")
    return raw[64:64 + length].decode("utf-8", "ignore")


def latest_block():
    return _int(rpc("eth_blockNumber", []))


def has_code_at(addr, block):
    return len(rpc("eth_getCode", [addr, hex(block)])) > 4


def find_deploy_block(addr, verbose=True):
    """배포 블록 자동 탐지 — eth_getCode 이진탐색. 컨트랙트 아니면 None."""
    tip = latest_block()
    # rate-limit 글리치로 빈 응답이 올 수 있어 tip 코드 존재는 여러 번 확인
    code_at_tip = False
    for _ in range(3):
        if has_code_at(addr, tip):
            code_at_tip = True
            break
        time.sleep(0.4)
    if not code_at_tip:
        return None
    lo, hi = 0, tip
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if has_code_at(addr, mid):
            hi = mid
        else:
            lo = mid
        time.sleep(0.2)   # rate-limit 회피 (연속 getCode)
    if verbose:
        print(f"  [배포블록 자동탐지] {addr[:12]}… → {hi}")
    return hi


def resolve_target(asset=None, address=None, verbose=True):
    """이름(--asset) 또는 주소(--token)를 분석 대상 딕셔너리로 변환."""
    # 1) 이름으로 (registry 조회, 대소문자 무시)
    if asset:
        for key, t in config.ASSETS.items():
            if key.lower() == asset.lower():
                tgt = dict(t)
                if "deploy_block" not in tgt:
                    tgt["deploy_block"] = find_deploy_block(tgt["address"], verbose)
                return tgt
        raise SystemExit(
            f"등록되지 않은 자산: {asset}\n"
            f"  등록됨: {list(config.ASSETS)}\n"
            f"  또는 --token 0x주소 로 직접 지정")
    # 2) 주소로 (메타데이터·배포블록 자동 조회)
    if address:
        addr = address.lower()
        if not addr.startswith("0x") or len(addr) != 42:
            raise SystemExit(f"잘못된 주소 형식: {address}")
        dep = find_deploy_block(addr, verbose)
        if dep is None:
            raise SystemExit(f"{addr}: 컨트랙트 코드 없음 (토큰 주소가 맞는지 확인)")
        meta = token_metadata(addr)
        return {"symbol": meta["symbol"], "name": meta["name"],
                "address": addr, "deploy_block": dep}
    # 3) 기본
    return config.TARGET


def call(to, selector):
    return rpc("eth_call", [{"to": to, "data": selector}, "latest"])


# ── 1) 토큰 메타데이터 ────────────────────────────────────
def token_metadata(addr):
    decimals = _int(call(addr, config.SEL_DECIMALS))
    supply = _int(call(addr, config.SEL_TOTALSUPPLY))
    return {
        "name": _decode_string(call(addr, config.SEL_NAME)),
        "symbol": _decode_string(call(addr, config.SEL_SYMBOL)),
        "decimals": decimals,
        "total_supply_raw": supply,
        "total_supply": supply / (10 ** decimals),
    }


# ── 2) Transfer 히스토리 수집 (청크 + 증분 캐시) ──────────
def _scan_logs(addr, from_block, to_block, base_count=0, verbose=True):
    """from_block~to_block 구간 Transfer 로그를 10k 청크로 긁는다."""
    out = []
    b = from_block
    chunk = config.LOG_CHUNK
    total = (to_block - from_block) // chunk + 1
    i = 0
    while b <= to_block:
        end = min(b + chunk - 1, to_block)
        i += 1
        logs = rpc("eth_getLogs", [{
            "address": addr,
            "topics": [config.TRANSFER_TOPIC],
            "fromBlock": hex(b), "toBlock": hex(end),
        }])
        for lg in logs:
            t = lg["topics"]
            out.append({
                "from": "0x" + t[1][-40:],
                "to": "0x" + t[2][-40:],
                "value": _int(lg["data"]),
                "block": _int(lg["blockNumber"]),
                "tx": lg["transactionHash"],
                "log_index": _int(lg["logIndex"]),
            })
        if verbose and (i % 10 == 0 or i == total):
            print(f"  스캔 {i}/{total} 청크 · 누적 {base_count + len(out)}건")
        b = end + 1
        time.sleep(config.SLEEP)
    return out


def fetch_transfers(addr, from_block, to_block, refresh=True, verbose=True):
    """
    증분 캐시: 분포 정확성을 위해 항상 from_block(=배포블록)부터의 '전체'를 반환한다.
    캐시가 last_block까지 있으면 그 다음부터만 새로 긁어 이어붙임(속도).
      refresh=False → Transfer 로그는 캐시만 사용(빠른 데모).
                      캐시가 없으면 부정확한 빈 분석 대신 실패한다.
    """
    cache = config.DATA / f"transfers_{addr.lower()}.json"
    cached, cached_from, cached_to = [], None, from_block - 1
    if cache.exists():
        meta = json.loads(cache.read_text(encoding="utf-8"))
        cached_from = meta.get("from_block")
        if cached_from is not None and cached_from <= from_block:
            cached = meta["transfers"]
            cached_to = meta.get("to_block", from_block - 1)

    if not refresh:
        if not cached:
            raise RuntimeError(
                "Transfer cache is empty for this token. "
                "Run without --recent once to build the full-history cache."
            )
        if verbose:
            print(f"  [캐시 전용] {len(cached)}건 (≤블록 {cached_to})")
        return cached

    if cached_to >= to_block:
        if verbose:
            print(f"  [캐시 최신] {len(cached)}건")
        return cached

    start = max(from_block, cached_to + 1)
    if cached and verbose:
        print(f"  [증분] 캐시 {len(cached)}건 + 블록 {start}~{to_block} 추가 스캔")
    new = _scan_logs(addr, start, to_block, base_count=len(cached), verbose=verbose)
    transfers = cached + new

    cache.write_text(json.dumps(
        {"address": addr, "from_block": from_block, "to_block": to_block,
         "transfers": transfers}, ensure_ascii=False), encoding="utf-8")
    return transfers


# ── 3) 잔액 재구성 + 공급/트레저리 식별 ───────────────────
def balances(transfers):
    """Transfer 누적으로 주소별 잔액 재구성"""
    bal = defaultdict(int)
    for t in transfers:
        bal[t["from"]] -= t["value"]
        bal[t["to"]] += t["value"]
    return bal


def supply_events(transfers, decimals):
    """민팅(0x0→)·소각(→0x0) 집계 — 순발행이 totalSupply와 맞는지 검증용"""
    mints = [t for t in transfers if t["from"] == config.ZERO_ADDR]
    burns = [t for t in transfers if t["to"] == config.ZERO_ADDR]
    mv = sum(t["value"] for t in mints) / (10 ** decimals)
    bv = sum(t["value"] for t in burns) / (10 ** decimals)
    return {
        "mint_count": len(mints), "burn_count": len(burns),
        "minted": mv, "burned": bv, "net_issued": mv - bv,
        "mint_recipients": sorted(set(t["to"] for t in mints)),
    }


def get_code_kind(addr):
    """주소가 컨트랙트인지 EOA(지갑)인지 — bytecode 유무로 판정"""
    code = rpc("eth_getCode", [addr, "latest"])
    if len(code) > 4:
        return "contract", (len(code) - 2) // 2  # 바이트 수
    return "eoa", 0


def identify_treasury(transfers, bal, decimals):
    """
    발행사/트레저리 식별: '민팅으로 받았고 + 현재 보유가 지배적인' 주소.
    이걸 분리해야 '발행 재고'와 '실제 유통(float)'을 구분할 수 있다.
    """
    sup = supply_events(transfers, decimals)
    mint_set = set(sup["mint_recipients"])
    holders = {a: v for a, v in bal.items()
               if v > 0 and a != config.ZERO_ADDR}
    total = sum(holders.values()) or 1
    treasuries = []
    for a in mint_set:
        v = holders.get(a, 0)
        if v / total >= 0.20:   # 발행 재고를 20% 이상 깔고 앉은 민팅 수령자
            treasuries.append(a)
    return treasuries, sup


def label_addresses(addrs, treasuries, transfers):
    """상위 주소들에 정체 라벨 부여: 트레저리 / 컨트랙트(풀 추정) / 일반지갑"""
    mint_recipients = set(t["to"] for t in transfers
                          if t["from"] == config.ZERO_ADDR)
    out = {}
    for a in addrs:
        kind, size = get_code_kind(a)
        if a in treasuries:
            label = "발행사/트레저리(민팅 수령·지배적 보유)"
        elif a in mint_recipients and kind == "eoa":
            label = "민팅 수령 지갑"
        elif kind == "contract":
            label = f"컨트랙트(LP풀/라우터 추정, {size}B)"
        else:
            label = "일반 지갑(EOA)"
        out[a] = {"kind": kind, "code_bytes": size, "label": label}
        time.sleep(config.SLEEP)
    return out


def distribution(bal, decimals, exclude=None):
    """홀더 분산 지표. exclude에 트레저리를 넣으면 'float 기준'으로 계산."""
    exclude = set(exclude or [])
    holders = {a: v for a, v in bal.items()
               if v > 0 and a != config.ZERO_ADDR and a not in exclude}
    ranked = sorted(holders.values(), reverse=True)
    circ = sum(ranked)
    n = len(ranked)

    def share(k):
        return sum(ranked[:k]) / circ if circ else 0.0

    hhi = sum((v / circ) ** 2 for v in ranked) if circ else 0.0
    return {
        "holder_count": n,
        "circulating": circ / (10 ** decimals),
        "top1_share": share(1),
        "top5_share": share(5),
        "top10_share": share(10),
        "hhi": hhi,
        "top_addresses": [a for a, _ in
                          sorted(holders.items(), key=lambda x: -x[1])[:10]],
    }


# ── 4) wash trade 의심 지표 (휴리스틱, 단정 아님) ─────────
def wash_indicators(transfers):
    n = len(transfers)
    if n == 0:
        return {"transfer_count": 0, "wash_score": 0, "evidence": ["거래 없음"]}

    senders = set(t["from"] for t in transfers)
    receivers = set(t["to"] for t in transfers)
    addrs = senders | receivers
    addrs.discard(config.ZERO_ADDR)

    # (a) 왕복 거래: A→B 직후 B→A 동일 규모 쌍
    pairs = defaultdict(int)
    for t in transfers:
        pairs[(t["from"], t["to"], t["value"])] += 1
    roundtrips = sum(
        min(c, pairs.get((b, a, v), 0))
        for (a, b, v), c in pairs.items() if a != b)
    roundtrip_ratio = roundtrips / n

    # (b) 참여 주소 다양성: 거래 수 대비 고유 주소가 적으면 의심
    diversity = len(addrs) / n  # 1에 가까울수록 건강, 0에 가까울수록 집중

    # (c) 거래량 집중: 상위 5개 주소가 관여한 거래 비중
    touch = defaultdict(int)
    for t in transfers:
        touch[t["from"]] += 1
        touch[t["to"]] += 1
    top5_touch = sum(sorted(touch.values(), reverse=True)[:5])
    touch_concentration = top5_touch / (2 * n)  # 각 거래는 2개 주소를 건드림

    # 의심 점수 0~100 (구성요소 투명 공개)
    score = round(100 * (
        0.45 * min(roundtrip_ratio * 3, 1) +
        0.30 * (1 - min(diversity * 5, 1)) +
        0.25 * touch_concentration))

    evidence = [
        f"고유 참여 주소 {len(addrs)}개 / 거래 {n}건 (다양성 {diversity:.2f})",
        f"왕복(round-trip) 의심 거래 {roundtrips}건 (비중 {roundtrip_ratio:.1%})",
        f"상위 5개 주소가 전체 거래 접점의 {touch_concentration:.1%} 차지",
    ]
    return {
        "transfer_count": n,
        "unique_addresses": len(addrs),
        "roundtrip_ratio": roundtrip_ratio,
        "address_diversity": diversity,
        "touch_concentration": touch_concentration,
        "wash_score": score,
        "evidence": evidence,
    }


# ── 통합 스냅샷 ───────────────────────────────────────────
def snapshot(target=None, refresh=True, verbose=True):
    # 홀더 잔액·트레저리·float은 전체 히스토리가 있어야 정확하므로
    # 분포는 '항상' 배포블록부터 본다. 속도는 증분 캐시가 해결.
    target = target or config.TARGET
    addr = target["address"]
    tip = latest_block()
    start = target["deploy_block"]
    if verbose:
        print(f"[onchain] {target['symbol']} @ {addr}")
        print(f"  블록 {start} ~ {tip} (증분 캐시)")

    meta = token_metadata(addr)
    transfers = fetch_transfers(addr, start, tip, refresh=refresh, verbose=verbose)
    bal = balances(transfers)

    # 발행사/트레저리 분리 → '발행 재고' vs '실제 유통(float)' 구분
    treasuries, supply = identify_treasury(transfers, bal, meta["decimals"])
    dist_full = distribution(bal, meta["decimals"])
    dist_float = distribution(bal, meta["decimals"], exclude=treasuries)
    wash = wash_indicators(transfers)

    # 트레저리가 실제로 시장을 만드는지 (거래 관여 비중)
    if treasuries:
        tset = set(treasuries)
        touch = sum(1 for t in transfers
                    if t["from"] in tset or t["to"] in tset)
        wash["treasury_touch_ratio"] = touch / len(transfers) if transfers else 0

    # 상위 주소 라벨링 (full top5 + float top5 + 트레저리)
    to_label = (set(dist_full["top_addresses"][:5])
                | set(dist_float["top_addresses"][:5]) | set(treasuries))
    labels = label_addresses(to_label, treasuries, transfers)

    return {
        "target": target, "block": tip,
        "metadata": meta, "supply": supply,
        "treasuries": treasuries,
        "distribution_full": dist_full,
        "distribution_float": dist_float,
        "labels": labels, "wash": wash,
    }


if __name__ == "__main__":
    snap = snapshot()
    m, s = snap["metadata"], snap["supply"]
    df, fl = snap["distribution_full"], snap["distribution_float"]
    w = snap["wash"]

    print(f"\n=== {m['symbol']} ({m['name']}) ===")
    print(f"발행량(supply): {m['total_supply']:,.0f}  "
          f"| 민팅 {s['minted']:,.0f} − 소각 {s['burned']:,.0f} "
          f"= 순발행 {s['net_issued']:,.0f}")

    print(f"\n--- 전체 분포 ---")
    print(f"홀더 {df['holder_count']}명 | top1 {df['top1_share']:.1%} | "
          f"HHI {df['hhi']:.3f}")

    print(f"\n--- 발행사/트레저리 분리 후 '실제 유통(float)' ---")
    print(f"float {fl['circulating']:,.2f} {m['symbol']} "
          f"({fl['circulating']/m['total_supply']:.2%} of supply) | "
          f"홀더 {fl['holder_count']}명 | float내 top5 {fl['top5_share']:.1%}")

    print(f"\n--- 상위 주소 정체 ---")
    for a, info in snap["labels"].items():
        print(f"  {a[:12]}… → {info['label']}")

    print(f"\n--- wash 의심 ({w['wash_score']}/100) ---")
    if "treasury_touch_ratio" in w:
        print(f"  (트레저리는 전체 거래의 {w['treasury_touch_ratio']:.1%}만 관여 "
              f"→ 거래는 float에서 발생)")
    for e in w["evidence"]:
        print(f"  · {e}")
