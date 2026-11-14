# BUILD REPORT

<!-- Kiro를 개발 과정의 어느 단계에서, 어떤 기능으로, 무엇을 했는지 기록해 주세요.
     1차 AI 심사는 이 문서와 .kiro/ 폴더를 보고 Kiro 활용을 평가해요. -->

## Kiro 활용 내역

| 단계 | 사용한 Kiro 기능 | 무엇을 했는지 | 결과물 위치 |
|---|---|---|---|
| 기획 | <!-- 예: Spec (requirements) --> | <!-- 예: 사용자 스토리 4개와 인수 조건 작성 --> | <!-- 예: .kiro/specs/xxx/requirements.md --> |
| 설계 | | | |
| 구현 | | | |
| 검증 | | | |
| 기타 | <!-- Steering, Hooks, MCP 등 --> | | |

## AI 에이전트 역할과 성과

기록일: 2026-11-14

| 에이전트 | 역할 | 한 일 | 결과물 위치 |
|---|---|---|---|
| Claude (Claude Code) | 문서 담당 | 평가, 거버넌스, 보안 유의사항, 제출 전 체크리스트 정리. 참고한 [Kirothon 규칙 페이지](https://awscommunity.pk/kirothon/#rules)는 파키스탄 행사 기준이라, 서울 AWS 주최 행사에는 거버넌스 4항목(원본 작업, 지식재산, 행동 강령, 실격)만 가져옴 | `docs/EVALUATION_GOVERNANCE_SECURITY.md` |
| Claude (Claude Code) | 문서 담당 | 이 저장소의 `AGENTS.md`, `SUBMISSION_GUIDE.md`를 평가와 거버넌스의 기준으로 연결. 서울 주최측 점수표는 아직 못 구해서 빈칸으로 둠. 참여 확정 안내(AUSG x ASBG x AWSKRUG, AWS Korea, 2026.11.14)를 이름과 소속을 가리고 행사 정보로 추가. 공식 사이트([kirothon.ausg.me](https://kirothon.ausg.me))의 당일 타임테이블, 팀 구성(1~4인), 주제 당일 공개도 반영 | `docs/EVALUATION_GOVERNANCE_SECURITY.md` |
| AI마니아 (Kiro Crew) | 프로바이더 관리자. Bedrock, Codex, OpenAI 키와 추론 환경 담당 | [template-pilot-ai-python](https://github.com/jyje/template-pilot-ai-python)을 참고해 초기 구성. Bedrock API 키(`AWS_BEARER_TOKEN_BEDROCK`)와 OpenAI API 키 지원 | `provider-manager/` |
| AI마니아 (Kiro Crew) | 프로바이더 관리자 | 공급자 시험 코드 작성. Bedrock 시험 6개 추가 (가짜 응답 사용) | `provider-manager/src/tests/test_providers.py` |
| AI마니아 (Kiro Crew) | 프로바이더 관리자 | LangChain 대신 Strands SDK로 전환. `PROVIDER`(`bedrock`, `openai`, `codex`)만 바꾸면 같은 에이전트 코드로 동작. `.env.example`에 공급자별 환경변수 정리 | `provider-manager/src/provider_manager/factory.py`, `.env.example` |
| AI마니아 (Kiro Crew) | 프로바이더 관리자 | Codex 구독용 Strands 모델 `CodexModel` 작성 (`codex exec` 호출, 토큰은 Codex가 보관). LangChain 커뮤니티 구현 비교 후 토큰을 직접 쓰는 방식은 약관 위험으로 따르지 않음 | `provider-manager/src/provider_manager/codex.py` |
| AI마니아 (Kiro Crew) | 프로바이더 관리자 | `CODEX_ENABLED=true`일 때만 Codex 설치와 사용. 컨테이너용 Dockerfile과 기기 로그인(`codex login --device-auth`) 절차 문서화. 옛 `src/build/` 정리 | `provider-manager/` |
| 디자이니 (Kiro Crew) | 디자인 담당 | 참고 사이트([kirothon-timer](https://kirothon-timer.vercel.app/))의 CSS를 읽고 디자인 시스템 추출. 색, 글꼴, 간격, 둥글기, 그림자, 움직임 값과 사용 규칙 정리. 화면은 직접 띄워 보지 않음 | `design-system/tokens.css`, `design-system/DESIGN.md` |
| 디자이니 (Kiro Crew) | 디자인 담당 | 디자인 시스템을 에이전트 스킬로 만듦 | `.agents/skills/kirothon-design-system/SKILL.md` |
| 디자이니 (Kiro Crew) | 디자인 담당 | 디자인 스토리보드 작성: 화면 영역 8개, 상태 S1~S8, 상태 흐름도, 단축키, 움직임, 만들 템플릿 목록. CSS와 힌트 문구로 추정한 내용이라 스크린샷 확인은 못 함 | `design-system/STORYBOARD.md` |
| 디자이니 (Kiro Crew) | 디자인 담당 | AWS 공개 디자인 시스템 Cloudscape(Apache-2.0)의 토큰 571개를 CSS 변수로 변환. 출처, 버전, 라이선스를 남기고 `LICENSE`, `NOTICE`를 함께 둠. React 컴포넌트는 스택 미정이라 가져오지 않음. Kiro 쪽 공개 디자인 시스템은 못 찾음 | `docs/references/cloudscape/` |
| 디자이니 (Kiro Crew) | 디자인 담당 | 별도 워크트리와 브랜치로 커밋하고 [PR #2](https://github.com/jyje/kirothon-team-032/pull/2) 작성. 사람이 병합함 (병합 커밋 `0fb8305`). 커밋 서명 키를 쓸 수 없어 서명 없이 커밋했고 PR 본문에 적음 | PR #2 |
| 문서기 (Kiro Crew) | slidev, 문서, 발표 자료 담당 | 기획 문서를 읽고 slidev 발표 초안 작성. 섹션 7개(표지, 모델 소개, 구조, 사례, 교훈, 향후 방향, 부록). `npm install`과 `npm run build` 종료 코드 0 | `slidev/` |
| 문서기 (Kiro Crew) | 문서 담당 | `jyje/skills`에서 `centered-readme`와 `git-commit-helper` 스킬을 가져옴 (원본과 바이트 단위로 같음) | `.agents/skills/` |
| 문서기 (Kiro Crew) | 문서 담당 | 변경점을 10개 묶음으로 나눠 커밋 메시지를 제안하고, 승인받아 서명 없이 커밋 10개 작성 | [PR #1](https://github.com/jyje/kirothon-team-032/pull/1) |
| 문서기 (Kiro Crew) | 문서 담당 | `AGENTS.md`에 Bot별 PR 표시, 한글 커밋 허용, 서명 없는 커밋과 PR로만 올리는 규칙 작성. `git-commit-helper`의 스킬 문서와 검증 스크립트가 한글 제목을 받도록 고치고 테스트 6개 통과 | `AGENTS.md`, `.agents/skills/git-commit-helper/` |

| 배포기 (Kiro Crew) | 배포 담당. `docker/`와 `helm/` 담당 | 개인 클러스터 `jyje/cluster`와 `jyje/pifanctl` 구조를 참고해 간단한 Helm 차트 작성 (Deployment, Service, Ingress). 앱 코드가 아직 없어서 임시 nginx 이미지를 씀 | `helm/` |
| 배포기 (Kiro Crew) | 배포 담당 | 임시 Dockerfile과 안내 페이지 작성. 이미지 `kirothon:0.1.0`을 로컬에서 빌드함 | `docker/Dockerfile`, `docker/html/index.html` |
| 배포기 (Kiro Crew) | 배포 담당 | 임시 폴더에서 팀 저장소로 두 폴더를 옮기고 `helm lint`를 다시 통과시킴. 저장소의 다른 변경은 건드리지 않음 | `docker/`, `helm/` |

### 배포기 현황 (갱신: 2026-11-14)

| 확인 | 결과 |
|---|---|
| `helm lint` | 통과 |
| `helm template` | 통과 |
| `docker build` | 성공 (`kirothon:0.1.0`) |
| 이미지 안 nginx 설정 검사 | 통과 |
| 컨테이너 실행과 HTTP 응답 | 못 함 (실행 도구가 막음) |
| 클러스터 설치 | 안 함 (요청 없음) |

- 아직 안 함: 컨테이너 실행 확인, 레지스트리 정하기, 실제 앱 이미지로 교체.
- 확인 못 한 것: ingress의 cert issuer `nginx-letsencrypt-prod`는 `jyje/cluster` 기준 추측이에요.
- 커밋과 push는 안 했어요. 클러스터에도 설치하지 않았어요.

### 디자이니 현황 (갱신: 2026-11-14)

- 끝남: 디자인 시스템, 스킬, 스토리보드, Cloudscape 참고 자료. 모두 병합됨.
- 아직 안 함: 스토리보드대로 타이머 컴포넌트와 템플릿 구현.
- 확인 못 한 것: 원본 JS(한마디 문구, 프리셋 시간, 마감 저장 방식), S7·S8 화면 모습.
- 에이전트는 `main`에 직접 push하지 않았어요. 다른 팀원의 변경은 PR에 넣지 않았어요.

### 문서기 현황 (갱신: 2026-11-14)

- 끝남: slidev 초안과 빌드, 스킬 2개 가져오기, 커밋 10개와 [PR #1](https://github.com/jyje/kirothon-team-032/pull/1), `AGENTS.md` 규칙.
- 아직 안 함: `npm run dev` 확인, 영문 덱, 화면 확인. 발표자 이름, 발표 시간, MVP 첫 산출물 같은 빈칸도 남아 있어요.
- 일부러 보류: `README.md`(템플릿 섹션이 지워진 상태), `docs/team.md`(Bot 담당이 추정), `records/`(`docs/`와 겹치는지 미확인).
- 알려진 문제: 검증 스크립트가 `skills/<이름>` 스코프를 막아요. 그래서 스킬 커밋 4개가 검증에 실패해요. 이미 올린 기록은 두고, 고치는 후속 커밋이 필요해요.
- 팀 활동이 곧 끝나서 새 작업은 시작하지 않아요. 문서 다듬기는 프로젝트 중반으로 미뤘어요.
- 에이전트는 `main`에 직접 push하지 않았어요.

### AI마니아 검증 현황 (갱신: 2026-11-14)

| 공급자 | 실제 호출 | 비고 |
|---|---|---|
| OpenAI | 성공 | `gpt-4o-mini` |
| Codex | 성공 | 로컬 로그인 사용, Strands 경유 `codex exec` |
| Bedrock | 아직 못 함 | `.env`에 키 없음. 시험은 가짜 응답으로 통과 |

- 단위 시험 21개 통과.
- 아직 안 한 것: Docker 빌드 실행(메모리 부족으로 보류), Bedrock 실제 호출, 커밋.
- Codex는 글만 만들어요. 도구 호출과 스트리밍은 안 돼요.

- 사람이 검토하고 병합해요. 에이전트는 `main`에 직접 push하지 않아요.
- 코드는 바꾸지 않았어요. 문서만 추가했어요.
- 확인한 것: `.env`는 `.gitignore`로 막혀 있고 추적되지 않아요.
- 아직 안 한 것: 커밋 이력 전체의 비밀 정보 검사, 의존성 취약점 점검. 제출 전 체크리스트에 넣었어요.

## 개발 과정에서 바뀐 점

<!-- Kiro와 작업하면서 처음 계획에서 바뀐 부분, 그 이유 -->

- 작업 위치를 임시 폴더에서 `/Users/jyje/repo/jyje/kirothon-team-032/provider-manager/`로 옮겼어요. 이전 폴더는 지웠어요.
- LangChain에서 Strands SDK로 바꿨어요. 공급자만 갈아 끼우고 에이전트는 한 곳에서만 만들어요.
- Codex는 항상 설치하지 않고 `CODEX_ENABLED=true`일 때만 설치해요.
- 문서기: 커밋 메시지를 영문에서 한글 허용으로 바꿨어요. 스킬 문서와 검증 스크립트도 같이 고쳤어요.
- 처음엔 파키스탄 대회 페이지의 점수표와 참가 자격까지 문서에 넣었어요. 이 행사는 서울 AWS KRUG, AWS 대학생 커뮤니티 모임 중심이라는 말을 듣고, 거버넌스 4항목만 남기고 나머지는 뺐어요. 기준은 `SUBMISSION_GUIDE.md`예요.

## 어려웠던 점과 해결 방법

<!-- 막혔던 부분과 어떻게 풀었는지 -->

- 대회 페이지 본문이 CSS에 묻혀 있어서, `style`과 `script`를 지운 뒤 텍스트만 뽑아 읽었어요.
- Codex는 글을 만드는 공개 호출 방법이 없었어요. `codex exec`를 감싸는 Strands 모델을 직접 만들어 풀었어요.
- 컨테이너에서 Codex 로그인이 걱정이었어요. 기기 로그인을 쓰고 `~/.codex`를 볼륨으로 남기는 방식으로 정했어요. 끝까지 실행해 보진 못했어요.
- 에이전트 실행 환경의 샌드박스가 켜지지 않아 첫 명령이 실패했어요. 샌드박스 없이 읽기 명령만 다시 실행했어요.
- 디자이니: 작업 폴더가 비어 있어서 구현을 멈추고 물었어요. 팀 폴더 `kirothon-team-032`가 기준이라는 답을 받고 거기로 맞췄어요.
- 디자이니: 일꾼 세션이 열리지 않아 직접 작업했어요.
- 디자이니: GPG 서명이 막혀 커밋이 실패했어요. 설정을 바꾸지 않고 멈춰서 물었고, 승인을 받아 서명 없이 커밋했어요.
- 문서기: Kiro Crew 프로세스가 `~/.gnupg`를 읽지 못해 서명 커밋이 계속 실패했어요. 전체 디스크 접근 권한을 주고 재시작해도 풀리지 않았어요. 서명 없는 커밋을 승인받아 진행했고, 이제 Bot 커밋은 서명 없이 만들어 PR로만 올려요.
- 문서기: 커밋 전 검증에서 셸의 `&&` 때문에 실패를 놓치고 커밋까지 진행됐어요. 원인은 검증 스크립트가 스킬 문서가 쓰라고 한 `skills/<이름>` 스코프를 막은 것이에요. 사실대로 보고했고 후속 커밋으로 고칠 계획이에요.
- 문서기: 처음에 빈 `event-kirothon2026` 경로에서 작업을 찾다가 헤맸어요. `/Users/jyje/repo/jyje/kirothon-team-032`가 기준이라는 답을 받고 맞췄어요.
- 배포기: 처음엔 Docker 소켓 접근이 막혀 빌드를 못 했어요. 나중에 데몬에 연결돼 빌드는 성공했어요.
- 배포기: `docker run -d`는 실행 도구가 막았어요. 우회하지 않고, 터미널에서 직접 돌릴 명령을 남겼어요.
- 배포기: 이 갱신 때도 샌드박스 오류로 `Bash`가 안 돼서 파일 읽기와 편집만 했어요.
- 디자이니: 이 갱신 때도 샌드박스 오류(`sandbox_apply: Operation not permitted`)로 `git status`는 못 돌렸어요. 파일 읽기와 편집만 했어요. 이 변경은 커밋하지 않았어요.
