"""
config.py — Skeptic Scout 전역 설정
외부 라이브러리 없이 표준 라이브러리(urllib, json)만으로 맨틀 온체인을 read 한다.
(심사위원이 pip install 없이 그대로 재현 가능하게)
"""
import os
import sys
from pathlib import Path


# ── .env 자동 로드 (키 입력칸 역할) — 의존성 없이 직접 파싱 ──
def _load_dotenv():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        # 이미 환경변수로 설정돼 있으면 그쪽 우선
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv()

# ── 한글 콘솔 출력 깨짐 방지 (Windows cp949) ──────────────
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── 맨틀 메인넷 ───────────────────────────────────────────
RPC_URL = "https://rpc.mantle.xyz"   # 무료 공개 RPC, 키 불필요
CHAIN_ID = 5000
EXPLORER = "https://mantlescan.xyz"

# ── 추적 대상 자산 ────────────────────────────────────────
# 자산 registry (이름 -> 주소). 등록된 자산은 --asset 이름으로,
# 등록 안 된 건 --token 주소로 분석한다.
# Mantle xStocks 토큰화 주식 라인업(RWA). 주소는 CoinGecko에서 가져와
# 맨틀 RPC로 코드/symbol을 확인했다. Backed가 체인마다 같은 주소로 배포해서
# 이더리움 주소와 맨틀 주소가 같다.
# deploy_block이 없으면 첫 분석 때 이진탐색으로 찾는다.
ASSETS = {
    # 대표 심층 사례 — 토큰화 SpaceX 주식
    "SPCXx":  {"symbol": "SPCXx",  "name": "SpaceX xStock",
               "address": "0x68fa48b1c2fe52b3d776e1953e0e782b5044ce28",
               "deploy_block": 96096100},
    # 2026-04 맨틀 상장 xStocks 라인업 10종 (TSLAx·NVDAx·AAPLx·METAx·GOOGLx
    #  ·MSTRx·HOODx·SPYx·QQQx·CRCLx) — Fluxion/Bybit
    #  deploy_block은 미리 계산해 둠 → 첫 실행 자동탐지 생략(안정성)
    "TSLAx":  {"symbol": "TSLAx",  "name": "Tesla xStock",
               "address": "0x8ad3c73f833d3f9a523ab01476625f269aeb7cf0",
               "deploy_block": 88102283},
    "NVDAx":  {"symbol": "NVDAx",  "name": "NVIDIA xStock",
               "address": "0xc845b2894dbddd03858fd2d643b4ef725fe0849d",
               "deploy_block": 88102138},
    "AAPLx":  {"symbol": "AAPLx",  "name": "Apple xStock",
               "address": "0x9d275685dc284c8eb1c79f6aba7a63dc75ec890a",
               "deploy_block": 88102033},
    "METAx":  {"symbol": "METAx",  "name": "Meta xStock",
               "address": "0x96702be57cd9777f835117a809c7124fe4ec989a",
               "deploy_block": 88102209},
    "GOOGLx": {"symbol": "GOOGLx", "name": "Alphabet xStock",
               "address": "0xe92f673ca36c5e2efd2de7628f815f84807e803f",
               "deploy_block": 88102231},
    "MSTRx":  {"symbol": "MSTRx",  "name": "MicroStrategy xStock",
               "address": "0xae2f842ef90c0d5213259ab82639d5bbf649b08e",
               "deploy_block": 88103555},
    "HOODx":  {"symbol": "HOODx",  "name": "Robinhood xStock",
               "address": "0xe1385fdd5ffb10081cd52c56584f25efa9084015",
               "deploy_block": 88103624},
    "SPYx":   {"symbol": "SPYx",   "name": "SP500 xStock (ETF)",
               "address": "0x90a2a4c76b5d8c0bc892a69ea28aa775a8f2dd48",
               "deploy_block": 88104054},
    "QQQx":   {"symbol": "QQQx",   "name": "Nasdaq xStock (ETF)",
               "address": "0xa753a7395cae905cd615da0b82a53e0560f250af",
               "deploy_block": 88104079},
    "CRCLx":  {"symbol": "CRCLx",  "name": "Circle xStock",
               "address": "0xfebded1b0986a8ee107f5ab1a1c5a813491deceb",
               "deploy_block": 88103980},
}

TARGET = ASSETS["SPCXx"]   # 기본 자산

# ── ERC-20 함수 셀렉터 (4바이트) ──────────────────────────
SEL_NAME = "0x06fdde03"
SEL_SYMBOL = "0x95d89b41"
SEL_DECIMALS = "0x313ce567"
SEL_TOTALSUPPLY = "0x18160ddd"
SEL_BALANCEOF = "0x70a08231"   # balanceOf(address)

# Transfer(address,address,uint256) 이벤트 topic0
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ZERO_ADDR = "0x0000000000000000000000000000000000000000"

# ── RPC 요청 옵션 ─────────────────────────────────────────
LOG_CHUNK = 10000      # eth_getLogs 한 번에 조회할 블록 수 (맨틀 RPC 상한)
TIMEOUT = 20           # 응답 타임아웃(초)
SLEEP = 0.05           # 호출 간 간격 — 레이트리밋 회피

# ── 트리거 임계치 (좁은 트리거) ───────────────────────────
# "신호 있을 때만 행동한다" — 이 선을 넘으면 메모 생성을 발사
THRESHOLDS = {
    "min_transfers": 50,          # 최근 구간 Transfer 건수가 이 이상이면 활동 발생
    "wash_suspicion": 60,         # wash 의심 점수가 이 이상이면 경고
    "concentration_top1": 0.50,   # 단일 주소가 유통량 50% 이상 보유 시 집중 경고
}

# ── 옵션 LLM 서술 레이어 (키 넣으면 그 LLM이 서술) ────────
# 키 감지: ANTHROPIC_API_KEY → Claude, OPENAI_API_KEY → GPT, 없으면 결정론.
# 핵심: LLM은 onchain 근거 안에서만 서술 → 환각 불가. 키 없어도 메모는 나온다.
LLM = {
    "anthropic_model": "",   # ANTHROPIC_MODEL로 지정. 비우면 친절히 안내하고 fallback.
    "openai_model": "gpt-4o",
    "max_tokens": 1500,
    "timeout": 60,
}

# ── Proof-of-Analysis: Mantle 테스트넷 (T2 온체인 기록용) ──
# 메인넷이 아니라 테스트넷에만 쓴다. 실제 자금 위험 0.
TESTNET = {
    "rpc": "https://rpc.sepolia.mantle.xyz",
    "chain_id": 5003,                       # Mantle Sepolia
    "explorer": "https://sepolia.mantlescan.xyz",
    "faucet": "https://faucet.sepolia.mantle.xyz",
}

# ── 파일 경로 ─────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(parents=True, exist_ok=True)

# 버린셈 치는 테스트넷 지갑 (절대 커밋 금지 — .gitignore 처리됨)
WALLET_FILE = DATA / "testnet_wallet.json"
