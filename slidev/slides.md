---
theme: default
title: open-attendee 기획
colorSchema: dark
info: |
  open-attendee 기획 발표 초안. 출처 문서는 docs/open-attendee-planning.md (초안, 승인 전).
---

# open-attendee

행사 참석자의 메모를 블로그와 링크드인 초안으로 바꾸는 에이전트

<!-- TODO: 발표자 이름과 소속 -->
<!-- TODO: 발표 시간 (결선 피칭 5분인지, 다른 자리인지) -->

---
layout: section
---

# 모델 소개

프로젝트가 무엇을 하는지

---

# 목적

- 행사에서 남긴 필기, 메모, 사진을 글 초안으로 바꿉니다.
- 전사 이후 형식별 산출물 만들기가 목표입니다.
- 결과물은 사람이 검토한 뒤에만 내보냅니다.

---

# 범위 (MVP)

- **입력**: 직접 쓴 필기, 텍스트 메모, 음성 메모, 사전 동의된 녹음
- **출력**: 블로그 초안, 링크드인 글 초안
- **출처**: 문장마다 녹음 시각, 메모 줄, 사진 파일 이름을 붙입니다.

<!-- TODO: MVP 첫 산출물을 블로그와 링크드인 중 무엇으로 할지 -->

---

# 하지 않을 것

- 회의에 봇으로 참석하기
- 링크드인 자동 게시
- 동의 없이 녹음 파일 저장과 처리
- 처음부터 만드는 다중 사용자 SaaS

---
layout: section
---

# 구조

처리 흐름과 인프라

---

# 처리 흐름

1. 업로드 (녹음은 동의 기록 확인 후에만)
2. 전사 (AWS 등 GPU 작업자)
3. 화자 분리
4. 사진 정리 (EXIF 위치 제거, 얼굴 흐림)
5. 사실 추출 (문장마다 출처 번호)
6. 형식별 초안 작성
7. 사실 검증 (출처 없는 주장 제거 또는 표시)
8. 사람 검토 후 내보내기

---

# 인프라 전략

| 역할 | 자원 | 비고 |
|---|---|---|
| 저장, 큐, 게이트웨이, 화면 | 온프레미스 클러스터 | 노드 사양 미확인 |
| 무거운 연산, 객체 저장소 | AWS | 필요할 때만 사용 |
| LLM 호출 | API 또는 구독 | 구독 약관 확인 필요 |

<!-- TODO: GPU 노드 보유 여부, AWS 계정과 리전 -->

---
layout: section
---

# 사례

선행 서비스와 빈 자리

---

# 선행 사례

- **회의 메모 도구**: Granola, Otter, Fireflies, tl;dv, Fathom, Plaud
- **강연을 블로그로**: Voibe, Snapsight, Unifire
- **링크드인 글 생성**: Supergrow, Syncronator, Linkeddraft
- **오픈소스 로컬 파이프라인**: fltman/transcriber, ownscribe, nimblehq/audio-transcriber

<!-- 출처 링크는 마지막 부록 슬라이드 참고 -->

---

# 차별점 (가설)

전사 이후 형식별 산출물을 만들고, 각 문장을 출처에 묶는 흐름.

이 가설은 아직 검증하지 않았습니다. 선행 사례에서 같은 흐름을 찾지 못했다는 조사 결과만 있습니다.

---
layout: section
---

# 교훈

위험과 검증

---

# 위험과 대응

| 위험 | 대응 |
|---|---|
| 원본에 없는 내용 (환각) | 출처 연결, 사실 검증, 사람 검토 |
| 한국어 전사 정확도 | 직접 만든 테스트 음성으로 WER 측정 |
| 무단 녹음 | 녹음은 동의 확인 후에만 처리, 서버에서도 강제 |
| 구독 약관 위반 | 구독은 실험용만, 본 처리는 API나 AWS |
| 비용 초과 | 예산 알림, 작업마다 비용 기록 |

---

# 검증 계획

1. 단위 테스트: 가짜 LLM과 가짜 전사 결과로 흐름 확인
2. 환경 점검: AWS 접근과 LLM 호출 확인
3. 벤치마크: WER, 처리 시간, 시간당 비용, 놓친 주장 수
4. 적대적 시험: 프롬프트 주입과 개인정보 추출 시도

"구독보다 싸다"는 주장은 측정 전에는 하지 않습니다.

---
layout: section
---

# 향후 방향

결정 항목과 다음 단계

---

# 결정이 필요한 항목

1. 사용 대상: 본인만인지, 참석자 여럿인지
2. AWS 계정과 리전, GPU 인스턴스 사용 여부
3. 온프레미스 노드 사양
4. 보유 AI 구독 종류와 약관
5. 녹음 업로드를 MVP에 넣을지
6. 첫 산출물 형식

<!-- TODO: 위 여섯 항목 답변 -->

---

# 다음 단계

1. 결정 항목에 답하기
2. 답변을 반영해 기획 문서 확정하기
3. 전사 정확도와 비용 짧은 실험하기
4. 설계가 확정되면 프로덕션 저장소로 옮기기

---
layout: section
---

# 부록

법률 검토, 정책, 출처

---

# 법률 검토 항목

- 통신비밀보호법: 제3자 대화 녹음 제한. 강연 녹음이 여기에 해당하는지 불분명.
- 개인정보 보호법: 녹음과 사진 개인정보의 처리 근거 확인 전.
- 행사 행동강령: 녹음과 촬영 규칙을 주최 측에 확인.
- 학업 규정: 과제용 산출물에는 학습용 표시.

<!-- TODO: 법률 자문 결과 -->

---

# 2026 AI 정책과 대응

- AI 기본법 (2026-01-22 시행): AI 생성 여부 표시
- AI 보안 레드팀 가이드 (2026-07-08 발표): 출시 전 적대적 시험
- 국가 AI 윤리 원칙 (2026-08-24 발표, 권고안): 7대 원칙별 대응 표를 기획 문서에 정리
- AI 보안 가이드라인 2.0 (KISA, 미발표): 발표되면 재검토

---

# 출처

- [South Korea's AI Basic Act overview (Cooley)](https://www.cooley.com/news/insight/2026/2026-01-27-south-koreas-ai-basic-act-overview-and-key-takeaways)
- [South Korea enacts world's 1st comprehensive AI safety law (Anadolu)](https://www.aa.com.tr/en/science-technology/south-korea-enacts-world-s-1st-comprehensive-ai-safety-law/3807419)
- [South Korea Codifies AI Red Teaming (TechTimes)](https://www.techtimes.com/articles/319978/20260709/south-korea-codifies-ai-red-teaming-ending-era-unverifiable-security-claims.htm)
- [COVER STORY: Korea's AI ethics principles (Korea Times)](https://www.koreatimes.co.kr/business/tech-science/20260824/cover-story-koreas-ai-ethics-principles-lack-binding-force-specificity)
- [Korea to Draw Red Lines for Autonomous AI (Seoul Economic Daily)](https://en.sedaily.com/technology/2026/09/14/korea-sets-security-red-lines-for-autonomous-ai)

<!-- 선행 사례 출처는 기획 문서 4절과 참고 절에 있음 -->

---
layout: end
---

# 감사합니다

질문 받겠습니다.
