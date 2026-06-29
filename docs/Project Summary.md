# Skeptic Scout — 제출 요약

Mantle Research Challenge는 토큰화 자산의 더 어려운 과제가 유통이라고 본다. Skeptic Scout는 SPCXx에서 그 지점을 온체인으로 확인한다. 발행된 30,000개 중 99% 이상이 발행사 지갑에 묶여 있고 시장에 풀린 건 1% 미만이다. 발행은 끝났는데 유통은 시작되지 않았다.

대부분의 온체인 봇이 상승 신호만 증폭할 때, 이 도구는 반대로 의심한다. 메모마다 네 섹션(bear case, wash trade 추정, who benefits, counter-narrative)을 넣고, 모든 수치는 `rpc.mantle.xyz`에서 읽은 값에 묶는다.

## 무엇을, 왜

리서처가 실수 할 때는 보통 좋은 정보,소식을 못 봐서가 아니라 헤드라인 뒤의 반대 신호를 놓쳐서다. 이 도구는 그 반대 신호를 기본값으로 보여준다.

## 어떻게

- 결정론 코어와 선택적 LLM 레이어. 메모 본문은 온체인 수치로 규칙에 따라 조립하므로(키 없이 재현 가능) 모델이 숫자를 지어낼 수 없다. 그 위에 LLM이 같은 근거로 서술만 더할 수 있다.
- 발행 재고와 실유통 분리. `eth_getCode`로 top1(공급의 99% 이상)이 발행사 EOA임을 확인해, "고래 매집"이라는 단순 해석을 교정하고 실유통이 1% 미만이라는 결론을 낸다.
- 의존성: 핵심 엔진은 Python 표준 라이브러리만 쓰고, 증명 레이어에서만 `eth-account`를 쓴다.

## 작동 사례 — SPCXx

`0x68fa48b1…ce28` (Mantle 메인넷). 발행 30,000 / 실유통 1% 미만 / 홀더 20여 명 / wash 의심 높음(약 84–93). 전체 메모는 `examples/SPCXx_demo_memo.md`.

## Proof-of-Analysis

메모를 keccak256으로 해시하고 EIP-191로 서명한다. 제출용 예시에서는 이 해시를 Mantle Sepolia 테스트넷 calldata에 기록해, 누구나 변조 여부와 온체인 기록을 검증할 수 있게 했다. 예시 tx: [`0x5cb554…be37`](https://sepolia.mantlescan.xyz/tx/0x5cb5545b2cb2620ba11f3a266ddb75913efc13c750558c25ed737af8cc97be37).

한 줄로 검증할 수 있다:
```
python scout\proof.py --verify examples\SPCXx_demo_proof.json
```
해시 재계산(변조 탐지), 서명자 복원, 온체인 calldata 대조 세 가지를 확인한다. 예시 proof는 제출용 고정 증명(데모 signer)이고, 로컬에서 직접 기록하면 각 환경의 테스트넷 지갑으로 새 proof bundle이 생성된다.

## 맨틀 참고자료 대응

공모전에 제시해준 스킬을 이렇게 썼다.
- AI Agent Skills: `mantle-xyz/mantle-skills` 디렉터리 규약대로 `skills/skeptic-scout/`로 패키징했다 (구현).
- 에이전트 스택 / 온체인: Mantle RPC로 데이터를 읽고, 제출용 예시에서 메모 해시를 Mantle Sepolia에 기록한다 (구현, 쓰기는 테스트넷).
- ERC-8004 신원: 제출용 proof는 고정된 에이전트 주소와 EIP-191 서명으로 검증되고, `.well-known` agent card로 신원과 검증 방식을 선언한다. 정식 온체인 레지스트리 등록이 아니라 그 방식을 따른 것이다 (방식 차용).
- x402 결제: full-evidence 페이월 hook 설계 (설계, 실결제는 안 함).

## 네 가지 원칙

의심하기, 좁게 파기, 신호 있을 때만 움직이기, 맨틀 표준 따르기.

---
저장소: 코드(`scout/`), 스킬(`skills/skeptic-scout/`), `.well-known/skeptic-scout.agent.json`, 작동 사례와 증명 번들(`examples/`).
