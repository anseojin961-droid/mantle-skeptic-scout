"""
llm.py — 옵션 LLM 서술 레이어 (Claude / GPT)

설계 원칙:
  - 결정론 코어(skeptic.py)가 만든 '온체인 근거'를 LLM에 넘겨 서술만 시킨다.
  - LLM은 근거 안에서만 쓰므로 숫자를 지어낼 수 없다 (환각 방지).
  - 키가 없거나 호출이 실패하면 None을 반환 → agent는 결정론 메모로 진행 (graceful degrade).
  - 표준 라이브러리(urllib)만 사용 → SDK 의존성 0. 공급자는 키로 자동 분기.

환경변수:
  ANTHROPIC_API_KEY → Claude (ANTHROPIC_MODEL도 함께 지정 권장)
  OPENAI_API_KEY    → GPT    (기본 모델 gpt-4o,          OPENAI_MODEL로 변경)
  SCOUT_LLM_PROVIDER → "anthropic"/"openai"로 강제 지정 (선택)
"""
import json
import os
import urllib.error
import urllib.request

import config

SYSTEM = (
    "너는 냉정한 온체인 금융 리서처다. 반드시 아래에 주어진 '온체인 실측 근거'만 사용해 "
    "회의적이고 균형 잡힌 한국어 리서치 메모를 작성한다. 근거에 없는 수치나 사실을 절대 지어내지 마라. "
    "4개 섹션(📉Bear case / 🔍Wash trade / 💰Who benefits / ⚡Counter-narrative)을 유지하고, "
    "단정 대신 '의심·추정·잠정적' 같은 표현을 쓴다. 응원단이 아니라 의심하는 도구로서 쓴다."
)


def detect_provider():
    forced = os.getenv("SCOUT_LLM_PROVIDER")
    if forced:
        return forced
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return None


def _post(url, headers, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"content-type": "application/json", **headers},
        method="POST")
    with urllib.request.urlopen(req, timeout=config.LLM["timeout"]) as r:
        return json.loads(r.read())


def _call_anthropic(prompt):
    model = os.getenv("ANTHROPIC_MODEL", config.LLM["anthropic_model"])
    if not model:
        raise RuntimeError("ANTHROPIC_MODEL을 지정하세요 (예: .env 또는 환경변수)")
    res = _post(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": os.environ["ANTHROPIC_API_KEY"],
         "anthropic-version": "2023-06-01"},
        {"model": model, "max_tokens": config.LLM["max_tokens"],
         "system": SYSTEM,
         "messages": [{"role": "user", "content": prompt}]})
    # content는 블록 배열 — text 타입만 모은다
    text = "".join(b.get("text", "") for b in res.get("content", [])
                   if b.get("type") == "text")
    return text, model


def _call_openai(prompt):
    model = os.getenv("OPENAI_MODEL", config.LLM["openai_model"])
    res = _post(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        {"model": model, "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt}]})
    return res["choices"][0]["message"]["content"], model


def narrate(memo):
    """근거에 묶인 LLM 서술 생성. 키 없으면 None, 실패하면 error 딕셔너리."""
    import skeptic
    provider = detect_provider()
    if not provider:
        return None
    prompt = skeptic.to_prompt(memo)
    try:
        if provider == "anthropic":
            text, model = _call_anthropic(prompt)
        elif provider == "openai":
            text, model = _call_openai(prompt)
        else:
            return {"provider": provider, "error": f"알 수 없는 공급자: {provider}"}
        return {"provider": provider, "model": model, "text": text.strip()}
    except urllib.error.HTTPError as e:
        return {"provider": provider, "error": f"HTTP {e.code} {e.reason}"}
    except Exception as e:
        return {"provider": provider, "error": str(e)}


if __name__ == "__main__":
    import onchain, skeptic
    p = detect_provider()
    print(f"감지된 공급자: {p or '없음 (결정론 모드)'}")
    if not p:
        print("키 설정: $env:ANTHROPIC_API_KEY 또는 $env:OPENAI_API_KEY")
        raise SystemExit(0)
    snap = onchain.snapshot(refresh=False, verbose=False)
    memo = skeptic.build_memo(snap)
    out = narrate(memo)
    if out and "text" in out:
        print(f"\n=== {out['provider']}/{out['model']} 서술 ===\n")
        print(out["text"])
    else:
        print("실패:", out)
