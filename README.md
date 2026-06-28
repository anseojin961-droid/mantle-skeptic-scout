# Skeptic Scout

Mantle 위의 토큰화 주식이 진짜로 유통되고 있는지 확인하는 온체인 리서치 에이전트입니다.

첫 사례는 `SPCXx`입니다. 헤드라인은 "SpaceX 주식이 토큰화됐다"였지만, 온체인으로 보면 발행량 30,000개 중 실제 시장에 풀린 물량은 1% 미만입니다. Skeptic Scout는 이런 식으로 좋은 소식 뒤에 가려진 반대 신호를 찾습니다.

한 줄 요약:

> 발행은 끝났고, 유통은 시작도 안 했다.

## 준비물

- Python 3.10 이상 (개발/테스트는 3.11에서 했습니다)
- 인터넷 연결 (Mantle 공개 RPC `rpc.mantle.xyz`에서 데이터를 읽습니다)
- API 키는 필요 없습니다. 핵심 기능은 Python 표준 라이브러리만 씁니다. (증명 검증 단계에서만 패키지 하나를 설치합니다.)

## 단계별 실행

따라 하면 그대로 재현됩니다. (명령은 Windows PowerShell 기준이고, mac/Linux는 경로 `\`를 `/`로 바꾸면 됩니다.)

### 1. 내려받기

```powershell
git clone https://github.com/anseojin961-droid/mantle-skeptic-scout.git
cd mantle-skeptic-scout
```

### 2. 메모 생성

```powershell
python scout\agent.py --force
```

처음 실행하면 Mantle RPC에서 Transfer 히스토리를 읽어 `data/` 캐시를 만듭니다(몇십 초 걸릴 수 있고, `스캔 N/M 청크` 진행 표시가 뜹니다). 끝나면 이런 요약이 나오고, 전체 메모가 `data/skeptic_scout_SPCXx_<블록번호>.md`로 저장됩니다.

```text
SPCXx(SpaceX xStock): 발행 30,000 / 실유통 1% 미만 / 홀더 20여 명 / wash의심 ...
```

### 3. 증명 검증

```powershell
pip install -r requirements-proof.txt
python scout\proof.py --verify examples\SPCXx_demo_proof.json
```

세 줄이 모두 `PASS`로 나오면 정상입니다.

```text
[PASS] 해시 재계산
[PASS] 서명자 복원
[PASS] 온체인 calldata 대조
```

### 4. 예시 메모 열어보기

```powershell
type examples\SPCXx_demo_memo.md
```

(VS Code에서는 파일을 우클릭 → Open Preview로 보면 더 깔끔합니다.)

### 빠르게 다시 돌리기

한 번 캐시를 만든 뒤에는 `--recent`로 네트워크 없이 캐시만 재사용합니다.

```powershell
python scout\agent.py --force --recent
```

## 검증이 하는 일

메모가 나중에 바뀌지 않았는지, 그리고 이 에이전트가 만든 게 맞는지 확인할 수 있게 proof bundle을 같이 제공합니다. 검증은 세 가지를 봅니다.

- 메모 내용을 다시 해시해서 저장된 해시와 같은지 확인합니다.
- 서명에서 에이전트 주소를 복원해 작성자가 맞는지 확인합니다.
- Mantle Sepolia에 기록된 tx calldata가 메모 해시와 같은지 확인합니다.

## 왜 만들었나

대부분의 온체인 봇은 좋은 소식을 더 크게 말합니다. TVL이 올랐다, 거래량이 늘었다, bullish하다는 식입니다.

하지만 리서처에게 더 필요한 건 반대 질문입니다.

- 이 자산이 실패한다면 이유가 뭘까?
- 거래량은 진짜 자연 거래일까?
- 이 내러티브가 이기면 누가 돈을 벌까?
- 시장이 지금 놓치고 있는 반대 신호는 뭘까?

Skeptic Scout는 모든 메모에 이 네 질문을 강제로 넣습니다.

## 어떻게 읽나

핵심은 `발행량`과 `실제 유통량`을 분리하는 것입니다.

SPCXx의 경우 top1 지갑이 공급의 99% 이상을 들고 있습니다. 이걸 단순히 "고래가 매집했다"라고 보면 틀립니다. Transfer 히스토리를 처음부터 재구성하고, 민팅을 받은 주소인지 확인한 뒤, 그 주소를 발행사 재고 지갑으로 분리합니다. 그 다음 남은 물량만 실제 float으로 보고 분석합니다.

현재 메모는 다음 지표를 봅니다.

- ERC-20 metadata
- mint / burn 이벤트
- 전체 Transfer 히스토리
- 주소별 잔액
- 발행사 재고와 실제 float
- top holder 집중도
- 왕복 거래, 주소 다양성, 상위 주소 접점 집중도

## 결과 예시

저장소에 예시 메모(`examples/SPCXx_demo_memo.md`)와 그 증명(`examples/SPCXx_demo_proof.json`)이 들어 있습니다. SPCXx 실행에서 나온 핵심은 이렇습니다.

- 공급량: 30,000 SPCXx
- 실제 유통: 1% 미만
- 홀더: 20여 명 수준
- wash 의심 점수: 높음

숫자는 라이브 체인을 읽기 때문에 실행 시점마다 조금 달라질 수 있습니다. 그래서 모든 메모는 block number를 같이 남깁니다.

## 다른 토큰도 가능한가

기본 사례는 SPCXx입니다. 데모나 심사는 이걸로 보는 게 가장 안정적입니다. 같은 엔진으로 Mantle xStocks 라인업도 볼 수 있습니다.

```powershell
python scout\agent.py --asset NVDAx --force
python scout\agent.py --asset TSLAx --force
python scout\agent.py --token 0x... --force
```

등록된 이름: `SPCXx, TSLAx, NVDAx, AAPLx, METAx, GOOGLx, MSTRx, HOODx, SPYx, QQQx, CRCLx`

단, SPCXx가 아닌 자산은 첫 실행 때 전체 Transfer 히스토리 캐시를 새로 만들기 때문에 시간이 걸릴 수 있습니다. 이 프로젝트의 주장은 "모든 토큰이 즉시 분석된다"가 아니라, "SPCXx를 깊게 증명했고 같은 방식이 xStocks로 확장된다"입니다.

## LLM 사용 (선택)

기본 메모는 LLM 없이 만들어집니다. 숫자는 모두 코드가 온체인에서 읽습니다. 원하면 LLM 서술 레이어를 추가할 수 있습니다.

```powershell
$env:ANTHROPIC_API_KEY="..."   # 또는 $env:OPENAI_API_KEY="..."
python scout\agent.py --force --llm
```

LLM에는 이미 계산된 근거만 넘깁니다. 숫자를 새로 만들지 못하게 하기 위해서입니다. 키가 없거나 호출이 실패하면 그냥 결정론 메모만 생성됩니다. 사용할 모델은 `.env` 또는 환경변수에서 지정합니다.

## Mantle 관련 구성

이 repo는 Mantle Research Challenge 트랙2를 염두에 두고 구성했습니다.

- `skills/skeptic-scout/` — `mantle-xyz/mantle-skills` 규약에 맞춘 스킬 패키지입니다. `SKILL.md`, `agents/openai.yaml`, `references/`, `assets/`를 포함합니다.
- `.well-known/skeptic-scout.agent.json` — 에이전트 신원, 검증 방식, x402 paywall hook을 선언한 agent card입니다.
- `evals/specs/skeptic-scout.yaml` — 스킬이 어떤 행동을 유도해야 하는지 적은 eval spec입니다. benchmark를 돌렸다는 뜻은 아니고, 평가 가능한 형태로 정리한 것입니다.
- `scout/proof.py` — 메모 해시, EIP-191 서명, Mantle Sepolia calldata 검증을 담당합니다.

x402는 실제 결제까지 구현하지 않았습니다. 전체 evidence를 유료 영역으로 둘 수 있다는 설계 hook만 넣었습니다.

## 파일 구조

```text
scout/
  agent.py      실행 진입점
  onchain.py    Mantle RPC read, Transfer scan, holder 분석
  skeptic.py    4개 skeptic 섹션 생성
  proof.py      해시, 서명, 온체인 검증
  llm.py        선택적 LLM 서술
  config.py     RPC 주소, 자산 registry, 임계치

skills/skeptic-scout/
  SKILL.md
  agents/openai.yaml
  references/methodology.md
  assets/xstocks.json

examples/
  SPCXx_demo_memo.md
  SPCXx_demo_proof.json

evals/specs/
  skeptic-scout.yaml
```

## 제출용 한 문장

Skeptic Scout는 Mantle의 토큰화 주식에서 발행과 실제 유통을 분리해 읽고, hype가 아니라 의심을 기본값으로 삼는 Proof-of-Analysis 리서치 에이전트입니다.
