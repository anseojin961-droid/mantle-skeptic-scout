"""
skeptic.py — 의심 메모 생성기 (Skeptic Layer)

모든 메모에 강제로 4섹션을 넣는다. 다른 봇은 응원단이지만 Scout는 의심한다.
  📉 Bear case        — 6개월 내 실패 시나리오
  🔍 Wash trade check — organic 비중 추정 (단정 X, 근거 O)
  💰 Who benefits     — 이 내러티브가 이기면 누가 이득보나
  ⚡ Counter-narrative — 시장이 무시하는 반대 신호

설계 원칙:
  - 모든 문장은 onchain 스냅샷의 '실측치'에 묶인다. 환각 금지.
  - 기본은 결정론(rule-based) → API키 없이 재현 가능.
  - to_prompt()는 같은 근거로 Claude 서술을 옵션 생성할 때 쓴다.
"""
import config


def _pct(x):
    return f"{x:.1%}"


# ── 📉 Bear case ──────────────────────────────────────────
def bear_case(snap):
    m = snap["metadata"]
    fl = snap["distribution_float"]
    df = snap["distribution_full"]
    sup = snap["supply"]
    sym = m["symbol"]
    float_pct = fl["circulating"] / m["total_supply"] if m["total_supply"] else 0

    points = []
    # 1) 유통 자체가 안 일어남
    points.append(
        f"실유통 float이 공급의 {_pct(float_pct)}({fl['circulating']:,.0f} {sym})에 불과. "
        f"발행은 됐지만 시장에 도달한 물량이 거의 없음 → 가격 발견이 불가능한 수준.")
    # 2) 발행사 의존
    if snap["treasuries"]:
        points.append(
            f"공급의 {_pct(df['top1_share'])}가 발행사/트레저리 단일 지갑에 묶여 있음. "
            f"발행사가 재고를 풀거나(매도압) 소각 정책을 바꾸면 float 가격이 즉시 무너짐. "
            f"실제로 이미 {sup['burned']:,.0f} {sym}를 소각한 이력 있음(공급 정책 재량이 큼).")
    # 3) 유동성 깊이
    points.append(
        f"float 내에서도 상위 5개 지갑이 {_pct(fl['top5_share'])} 보유 → 소수가 던지면 "
        f"받아줄 깊이가 없음. 홀더 {fl['holder_count']}명으로는 분산 매수벽이 형성 안 됨.")
    # 4) 구조적 리스크
    points.append(
        "토큰화 주식은 발행사 커스터디·법적 정산에 의존 → 스마트컨트랙트가 멀쩡해도 "
        "오프체인 상환(redemption)이 막히면 1:1 페그가 깨질 수 있음.")

    verdict = (f"6개월 내 실패 시나리오의 핵심은 '가격'이 아니라 '유통 부재'. "
               f"공급의 {_pct(float_pct)}만 풀린 상태가 지속되면 {sym}는 "
               f"거래 가능한 자산이라기보다 발행사 장부상 토큰에 가깝다.")
    return {"title": "📉 Bear case — 6개월 내 실패한다면?",
            "verdict": verdict, "evidence": points}


# ── 🔍 Wash trade check ───────────────────────────────────
def wash_check(snap):
    w = snap["wash"]
    score = w["wash_score"]
    organic = max(0, 100 - score)
    points = list(w["evidence"])
    if "treasury_touch_ratio" in w:
        points.append(
            f"단, 발행사 트레저리는 전체 거래의 {_pct(w['treasury_touch_ratio'])}만 관여 "
            f"→ 이 거래량은 발행사가 아니라 얇은 float 안에서 발생.")

    if score >= config.THRESHOLDS["wash_suspicion"]:
        verdict = (f"organic(자연) 거래 비중 추정 ~{organic}%. 왕복 거래와 소수 주소 집중이 높아 "
                   f"'활발한 거래량'의 상당 부분이 마켓메이커 churn 또는 wash일 가능성. "
                   f"단정이 아니라 의심 — 거래량 지표를 그대로 믿지 말 것.")
    else:
        verdict = (f"organic 거래 비중 추정 ~{organic}%. 뚜렷한 wash 패턴은 약함. "
                   f"다만 표본이 얇아 결론은 잠정적.")
    return {"title": f"🔍 Wash trade check — organic ~{organic}% (의심점수 {score}/100)",
            "verdict": verdict, "evidence": points}


# ── 💰 Who benefits ───────────────────────────────────────
def who_benefits(snap):
    sym = snap["metadata"]["symbol"]
    labels = snap["labels"]
    pools = [a for a, i in labels.items() if i["kind"] == "contract"]
    points = [
        f"발행사/플랫폼(xStocks·Mantle): '역사상 최대 IPO 토큰화'라는 내러티브 자체가 "
        f"브랜드·TVL·신규 유입의 마케팅 자산. 실제 유통 깊이와 무관하게 헤드라인이 이득.",
        f"마켓메이커/LP: 얇은 float({snap['distribution_float']['circulating']:,.0f} {sym})에서 "
        f"스프레드를 먹는 소수 주소. 거래접점 상위 5개가 {_pct(snap['wash']['touch_concentration'])} 차지.",
    ]
    if pools:
        points.append(
            f"컨트랙트(LP풀/라우터 추정) {len(pools)}개가 거래 인프라를 장악 → "
            f"유동성 경로를 쥔 쪽이 수수료 수취.")
    points.append(
        "초기 float 보유 지갑: '곧 분배가 온다'는 기대가 이기면 선점 프리미엄을 누림. "
        "분배가 안 오면 출구가 없는 쪽도 이들.")
    verdict = ("이 내러티브가 이기면 가장 확실한 수혜자는 '실유통'이 아니라 "
               "'발행 헤드라인'과 '얇은 시장의 스프레드'를 가진 쪽. 일반 매수자의 자리는 아직 없음.")
    return {"title": "💰 Who benefits — 내러티브가 이기면?",
            "verdict": verdict, "evidence": points}


# ── ⚡ Counter-narrative ──────────────────────────────────
def counter_narrative(snap):
    m = snap["metadata"]
    fl = snap["distribution_float"]
    float_pct = fl["circulating"] / m["total_supply"] if m["total_supply"] else 0
    points = [
        f"시장 헤드라인: 'SpaceX 온체인! 24/7 거래! 역사상 최대 IPO!' — "
        f"그러나 온체인 실측 float은 공급의 {_pct(float_pct)}뿐.",
        f"'토큰화 = 글로벌 유통'이라는 가정이 여기선 아직 거짓. 발행(issuance)과 "
        f"유통(distribution)은 별개 문제이고, {m['symbol']}는 유통 단계에 진입하지 못함.",
        "무시되는 신호: 홀더 수·float 비중·홀더 분산은 가격 차트에 안 잡힘. "
        "거래량은 커 보여도 참여 주소는 수십 개 단위.",
        "반대 관점의 기회: 만약 발행사가 의도적으로 float을 풀고 분배 인센티브를 켜는 "
        "순간이 온다면, 그게 진짜 변곡점. 지금은 그 전야.",
    ]
    verdict = ("시장은 '발행 성공'을 '유통 성공'으로 착각하고 있음. "
               "진짜 추적해야 할 지표는 가격이 아니라 float 비중과 홀더 분산의 변화율.")
    return {"title": "⚡ Counter-narrative — 시장이 무시하는 신호",
            "verdict": verdict, "evidence": points}


# ── 메모 조립 ─────────────────────────────────────────────
def build_memo(snap):
    m = snap["metadata"]
    fl = snap["distribution_float"]
    float_pct = fl["circulating"] / m["total_supply"] if m["total_supply"] else 0
    headline = (
        f"{m['symbol']}({m['name']}): 발행 {m['total_supply']:,.0f} / "
        f"실유통 {_pct(float_pct)} / 홀더 {snap['distribution_full']['holder_count']}명 / "
        f"wash의심 {snap['wash']['wash_score']}/100")
    thesis = (
        "한 줄 명제 — '발행은 끝났고 유통은 시작도 안 했다.' "
        f"공급의 {_pct(1 - float_pct)}가 발행사 재고에 묶여 있고, 시장에 도달한 건 "
        f"{_pct(float_pct)}. 토큰화 자산의 다음 움직임은 '발행'이 아니라 '국경 없는 유통'에서 갈린다.")
    sections = [bear_case(snap), wash_check(snap),
                who_benefits(snap), counter_narrative(snap)]
    return {
        "symbol": m["symbol"], "block": snap["block"],
        "headline": headline, "thesis": thesis, "sections": sections,
    }


# ── 옵션: Claude 서술용 프롬프트 (같은 근거에 묶임) ───────
def to_prompt(memo):
    lines = [
        "너는 온체인 금융 리서처다. 아래 '온체인 실측 근거'만 사용해서 "
        "회의적이고 균형 잡힌 리서치 메모를 써라. 근거에 없는 수치를 지어내지 마라.",
        f"\n# 대상: {memo['headline']}", f"# 명제: {memo['thesis']}\n"]
    for s in memo["sections"]:
        lines.append(f"## {s['title']}\n결론: {s['verdict']}")
        for e in s["evidence"]:
            lines.append(f"- {e}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import onchain
    snap = onchain.snapshot(verbose=False)
    memo = build_memo(snap)
    print("=" * 64)
    print(memo["headline"])
    print(memo["thesis"])
    print("=" * 64)
    for s in memo["sections"]:
        print(f"\n{s['title']}")
        print(f"  → {s['verdict']}")
        for e in s["evidence"]:
            print(f"  · {e}")
