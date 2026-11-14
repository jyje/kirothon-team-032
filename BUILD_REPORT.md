# BUILD REPORT

## Kiro 활용 내역

### 스펙 주도 개발 (Kiro Spec)

Kiro의 Spec 흐름(요구사항 → 설계 → 작업 목록 → 작업별 구현)을 따라 웹앱 `open-attendee-webapp`을 만들었어요. 각 단계는 앞 단계의 파일을 입력으로 삼아요.

| 단계 | 사용한 Kiro 기능 | 무엇을 했는지 | 기반 파일 (입력) | 결과물 위치 |
|---|---|---|---|---|
| 기획 | Spec: requirements | 설계 초안에서 요구사항 28개를 뽑아 EARS 문장으로 정리. 0단계(해커톤 데모)와 1단계(MVP)로 나누고, 사용자가 정하지 않은 항목은 가정(A1~)으로 표시 | `docs/readme-interview.md`(1순위), `records/docs/open-attendee-planning.md`, `records/docs/privacy-policy.md`, `README.md` | `.kiro/specs/open-attendee-webapp/requirements.md` (539줄) |
| 설계 | Spec: design | 구조, 주요 흐름, 컴포넌트와 인터페이스, 데이터 모델, 정확성 속성(Correctness Properties), 오류 처리, 테스트 전략, 보안, 배포를 한 문서로 설계. 열린 결정은 마지막 절에 모음 | 위 입력 문서와 재사용할 기존 자산 `provider-manager/`, `docker/`, `helm/`, `design-system/` | `.kiro/specs/open-attendee-webapp/design.md` (1399줄) |
| 작업 계획 | Spec: tasks | 설계를 구현 작업 21개로 쪼갬. 0단계 1~14번, 1단계 15~21번. 공통 약속(라우터 자동 등록, 작업 핸들러 데코레이터, 테스트용 가짜 공급자) 명시 | `design.md`, `requirements.md`, `AGENTS.md` | `.kiro/specs/open-attendee-webapp/tasks.md` (498줄) |
| 구현 | Kiro IDE 에이전트 세션 (작업 실행) | 작업 번호별로 구현하고 커밋. 뼈대·설정·DB, 로그인·CSRF, 세션과 메모, 저장소, 녹음 동의 게이트, 사진 EXIF 제거까지 진행 | `tasks.md`의 작업 번호, `provider-manager/`(LLM 공급자 재사용) | `webapp/src/open_attendee/` |
| 검증 | Spec의 정확성 속성 + 속성 기반 테스트 | 설계의 속성을 Hypothesis 테스트로 옮김 (예: 소유자 격리 Property 18, 동의 범위, EXIF 제거 Property 5) | `design.md`의 Correctness Properties | `webapp/src/tests/` |
| 기록 | 작업 실행 이력 | 어떤 작업을 어느 세션에서 실행했는지 Kiro가 남김 | | `.kiro/specs/open-attendee-webapp/tasks.meta.json` |
| 기타 | 작업 규칙(Steering 역할), 에이전트 스킬, Kiro Crew 멀티 에이전트 | Bot이 작업 전에 `AGENTS.md`를 읽고, 스킬 3개를 씀. Bot 5개가 역할을 나눠 병렬로 일함 | `AGENTS.md`, `.agents/skills/` | 아래 "Bot별 성격과 성과" |

- 웹앱 구현은 [PR #5](https://github.com/jyje/kirothon-team-032/pull/5)로 `main`에 들어갔어요. 이후 [PR #7](https://github.com/jyje/kirothon-team-032/pull/7)(화면 다듬기), [PR #9](https://github.com/jyje/kirothon-team-032/pull/9)(출처가 붙는 AI 요약), [PR #10](https://github.com/jyje/kirothon-team-032/pull/10)(초안, 승인, 마크다운 내보내기)이 병합됐어요.
- 스펙 3개 파일(`requirements.md`, `design.md`, `tasks.md`)의 `main` 반영 여부는 제출 전에 다시 확인해야 해요.
- 갱신: 작업 목록의 모든 체크박스를 실제 구현과 맞춘 변경이 [PR #12](https://github.com/jyje/kirothon-team-032/pull/12)로 `main`에 병합됐어요.
- 같은 브랜치에 Kiro steering 문서, 비밀 파일 읽기 차단, 저장 시 린트, 작업 뒤 테스트 훅(`b5d8777`)과 "매 PR마다 `.kiro` 변경 확인" 규칙(`00a26bc`)도 PR #12로 병합됐어요.
- 중간 개발 스크린샷과 기능별 증거는 [`docs/KIRO_USAGE.md`](docs/KIRO_USAGE.md)에 있어요.

### 가드레일 (Kiro의 보안 규칙)

Kiro는 보안 회색지대를 규칙으로 막아 두었고, 개발자가 우회하라고 해도 따르지 않았어요. 개발자는 이 규칙에 맞춰 설계를 바꿨어요.

| 막힌 일 | Kiro의 반응 | 개발자가 바꾼 설계 |
|---|---|---|
| GPG 서명 우회 (서명 키를 쓸 수 없을 때) | 설정을 바꾸거나 서명을 끄지 않고 멈춰서 물음 | Bot 커밋은 서명 없이 만들고, PR로만 올려요. 사람이 검토하고 병합해요. 이유는 `AGENTS.md`에 있어요 |
| `main`에 직접 push | 막힘 | 기능 브랜치와 PR만 써요 |
| 샌드박스나 실행 도구가 막은 명령 (`docker run -d` 등) | 우회하지 않고 사람이 직접 돌릴 명령을 남김 | 막힌 일은 사람이 실행해요 |
| 시크릿 파일 읽기 | 읽지 않음 (`.env`, Codex 로그인 파일) | 키는 `.env`에만 두고 `.gitignore`로 막아요 |

규칙이 개발 속도를 늦추기도 했지만, 우회 대신 사람의 승인으로 풀었어요. 막힌 사례는 아래 "어려웠던 점과 해결 방법"에 있어요.

### Bot별 성격과 성과

Kiro Crew에서 Bot 5개가 역할을 나눠 일했어요. 모두 사람이 검토하고 병합했고, `main`에 직접 push하지 않았어요.

| Bot | 성격 | 성과 | 결과물 |
|---|---|---|---|
| 기획 (Kiro Crew) | 계획 담당. 커밋과 파일에서 확인한 것만 근거로 삼음 | 커밋 목록을 읽고 구현 단계와 마일스톤 기준으로 기획 추가안 제안. 이 `BUILD_REPORT.md`를 새 커밋에 맞춰 갱신 | 아래 "기획 현황", `BUILD_REPORT.md` |
| 정책이 (Claude Code) | 규칙을 꼼꼼히 읽고 근거를 붙이는 문서 담당. 확인 못 한 점은 빈칸으로 둠 | 평가 기준, 거버넌스, 보안 유의사항, 제출 전 체크리스트를 한 문서로 정리. 서울 행사 기준으로 거버넌스 4항목만 남김 | `docs/EVALUATION_GOVERNANCE_SECURITY.md` |
| 문서기 | 정리와 기록에 강한 문서 담당. 막히면 사실대로 보고함 | slidev 발표 초안(섹션 7개, 빌드 성공), 스킬 2개 가져오기, 커밋 10개와 병합된 PR #1, `AGENTS.md` 규칙 작성. 발표 초안은 이후 PR #11에서 구현에 맞게 다시 쓰여 병합됨 | `slidev/`, `AGENTS.md`, `.agents/skills/` |
| AI마니아 | 모델 공급자 관리자. 키와 약관 위험을 신중히 따짐 | Strands SDK로 Bedrock·OpenAI·Codex를 공급자 설정만으로 전환. OpenAI와 Codex 실제 호출 성공, 시험 21개 통과 | `provider-manager/` |
| 디자이니 | 디자인 담당. 근거 없는 추측은 적어 둠 | 디자인 토큰과 규칙, 스토리보드, Cloudscape 토큰 571개 변환, 디자인 스킬. PR #2 병합 | `design-system/`, `docs/references/cloudscape/`, `.agents/skills/kirothon-design-system/` |
| 배포기 | 배포 담당. 막힌 도구는 우회하지 않고 명령을 남김 | 임시 Helm 차트와 Dockerfile로 시작해 `helm lint`, `docker build` 성공. 이후 `jyje/cluster`의 mungchilog 방식(환경별 브랜치, Argo CD, Image Updater)으로 dev·stg·prd 배포 구성. 도메인 CNAME 3개 생성. 영어로만 쓰는 규칙은 `jyje/cluster` 전용으로 기억함 | `docker/`, `helm/`, `.github/workflows/build.yml`, `jyje/cluster` |

웹앱 스펙 자체는 Kiro IDE 에이전트 세션이 만들었고, 위 Bot들의 `provider-manager/`, `docker/`, `helm/`, `design-system/`을 설계가 재사용해요.

## AI 에이전트 역할과 성과

기록일: 2026-11-14

| 에이전트 | 역할 | 한 일 | 결과물 위치 |
|---|---|---|---|
| 정책이 (Claude Code) | 문서 담당 | 평가, 거버넌스, 보안 유의사항, 제출 전 체크리스트 정리. 참고한 [Kirothon 규칙 페이지](https://awscommunity.pk/kirothon/#rules)는 파키스탄 행사 기준이라, 서울 AWS 주최 행사에는 거버넌스 4항목(원본 작업, 지식재산, 행동 강령, 실격)만 가져옴 | `docs/EVALUATION_GOVERNANCE_SECURITY.md` |
| 정책이 (Claude Code) | 문서 담당 | 이 저장소의 `AGENTS.md`, `SUBMISSION_GUIDE.md`를 평가와 거버넌스의 기준으로 연결. 서울 주최측 점수표는 아직 못 구해서 빈칸으로 둠. 참여 확정 안내(AUSG x ASBG x AWSKRUG, AWS Korea, 2026.11.14)를 이름과 소속을 가리고 행사 정보로 추가. 공식 사이트([kirothon.ausg.me](https://kirothon.ausg.me))의 당일 타임테이블, 팀 구성(1~4인), 주제 당일 공개도 반영 | `docs/EVALUATION_GOVERNANCE_SECURITY.md` |
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
| 디자이니 (Kiro Crew) | 디자인 담당 | `BUILD_REPORT.md`에 디자이니 역할과 성과를 처음 적음 | `BUILD_REPORT.md` |
| 디자이니 (Kiro Crew) | 디자인 담당 | Vue 프런트(`.worktrees/webapp/webapp/frontend`)를 읽기만 하고 가볍게 검토. 디자인 토큰(`@design/tokens.css`)과 폰트를 그대로 쓰는 점, `api.ts`가 CSRF와 오류를 한 곳에서 다루는 점, 라우터 가드를 확인. 고칠 점 5가지를 제안함: 지운 메모의 저장 요청 되살아남, 삭제 실패 때 알림 없음, 401에서 페이지 전체 새로고침, 불러오기 실패 표시 없음, 떠날 때 저장 안 된 메모 유실. 코드는 바꾸지 않았고 빌드와 타입 검사도 안 돌림 | 대화 기록 (파일 변경 없음) |
| 문서기 (Kiro Crew) | slidev, 문서, 발표 자료 담당 | 기획 문서를 읽고 slidev 발표 초안 작성. 섹션 7개(표지, 모델 소개, 구조, 사례, 교훈, 향후 방향, 부록). `npm install`과 `npm run build` 종료 코드 0 | `slidev/` |
| 문서기 (Kiro Crew) | 문서 담당 | `jyje/skills`에서 `centered-readme`와 `git-commit-helper` 스킬을 가져옴 (원본과 바이트 단위로 같음) | `.agents/skills/` |
| 문서기 (Kiro Crew) | 문서 담당 | 변경점을 10개 묶음으로 나눠 커밋 메시지를 제안하고, 승인받아 서명 없이 커밋 10개 작성. 사람이 병합함 | [PR #1](https://github.com/jyje/kirothon-team-032/pull/1) |
| 문서기 (Kiro Crew) | 문서 담당 | `AGENTS.md`에 Bot별 PR 표시, 한글 커밋 허용, 서명 없는 커밋과 PR로만 올리는 규칙 작성. `git-commit-helper`의 스킬 문서와 검증 스크립트가 한글 제목을 받도록 고치고 테스트 6개 통과 | `AGENTS.md`, `.agents/skills/git-commit-helper/` |
| 배포기 (Kiro Crew) | 배포 담당. `docker/`와 `helm/` 담당 | 개인 클러스터 `jyje/cluster`와 `jyje/pifanctl` 구조를 참고해 간단한 Helm 차트 작성 (Deployment, Service, Ingress). 앱 코드가 아직 없어서 임시 nginx 이미지를 씀 | `helm/` |
| 배포기 (Kiro Crew) | 배포 담당 | 임시 Dockerfile과 안내 페이지 작성. 이미지 `kirothon:0.1.0`을 로컬에서 빌드함 | `docker/Dockerfile`, `docker/html/index.html` |
| 배포기 (Kiro Crew) | 배포 담당 | 임시 폴더에서 팀 저장소로 두 폴더를 옮기고 `helm lint`를 다시 통과시킴. 저장소의 다른 변경은 건드리지 않음 | `docker/`, `helm/` |
| 배포기 (Kiro Crew) | 배포 담당 | 범위를 웹앱 + 온프레미스 k8s + Helm 네이티브로 줄이고, 맥북·iOS·AWS EKS·ECS는 로드맵으로 넘김 | `docs/ROADMAP.md` |
| 배포기 (Kiro Crew) | 배포 담당 | `jyje/cluster`에서 mungchilog 배포 방식을 읽고 dev·stg·prd 환경 구성을 설계. 앱 팀원이 올린 차트(PR #5)를 기준으로 맞춤 | `jyje/cluster` |
| 배포기 (Kiro Crew) | 배포 담당 | 브랜치별 이미지 빌드로 `build.yml` 수정(`main`·`dev`는 `open-attendee-dev`, `stg`는 `open-attendee-stg`, `prd`는 `open-attendee`). 차트 기본 이미지도 맞춤. [PR #6](https://github.com/jyje/kirothon-team-032/pull/6) 병합 | `.github/workflows/build.yml`, `helm/values.yaml` |
| 배포기 (Kiro Crew) | 배포 담당 | `dev`, `stg`, `prd` 브랜치를 최신 `main`에서 만들어 origin에 push | 브랜치 3개 |
| 배포기 (Kiro Crew) | 배포 담당 | `jyje/cluster`에 환경별 Argo CD 앱과 Image Updater 추가. 주소는 `attendee.{dev,stg,app}.jyje.online`. 영어 PR로 올림. [PR #270](https://github.com/jyje/cluster/pull/270) 병합 | `clusters/r4spi/apps/open-attendee-*.yaml` |
| 배포기 (Kiro Crew) | 배포 담당 | Porkbun에서 도메인 기록을 확인하고 CNAME 3개(`attendee.dev`, `attendee.stg`, `attendee.app`)를 `r5iny.iptime.org.`로 생성 | Porkbun DNS |
| 배포기 (Kiro Crew) | 배포 담당 | 시크릿 `open-attendee`가 없어 Argo CD가 오류를 낸 원인을 찾음. 비밀번호는 사람이 직접 봉인하도록 명령을 남기고, 봉인 파일 3개를 영어 PR로 올림. [PR #271](https://github.com/jyje/cluster/pull/271) (병합 전) | `clusters/r4spi/apps/open-attendee-secret-*.yaml` |

Kiro 활용 증거와 중간 개발 스크린샷은 [`docs/KIRO_USAGE.md`](docs/KIRO_USAGE.md)에 모아 두었어요.

### 기획 현황 (갱신: 2026-11-14)

커밋 기준 구현 단계와 마일스톤이에요.

| 마일스톤 | 내용 | 근거 | 상태 |
|---|---|---|---|
| M0 준비 | 저장소 시작, 스킬 3개, slidev 뼈대, 디자인 토큰, Docker, Helm, provider-manager, 라이선스 | `a1800de`~`92a8019` | 끝남 |
| M1 기반 문서 | README, 디자인 스토리보드, 평가·거버넌스·보안 문서, Kiro 활용 증거 | PR #1~#4 | 끝남 |
| M2 웹앱 | Vue 화면, 로그인, 메모, 사진, CI, Helm 배포 | PR #5, #6 | 끝남 |
| M3 핵심 기능 | 화면 다듬기, README 현황, 출처가 붙는 AI 요약, 초안과 승인 | PR #7~#10 | 끝남 |
| M4 제출 준비 | 발표자료 PDF, steering과 훅, 출처·라이선스 표기, 제출 체크리스트 표시 | PR #11, #12 (병합) | 끝남. 남은 일은 제출 폼 입력 |

- 아직 안 함: `stg`, `prd` 이미지 빌드, 클러스터 `Healthy` 확인, Bedrock 실제 호출, 서울 주최측 점수표 반영.
- 확인 못 한 것: 기획 추가안이 사람의 승인을 받았는지. 승인 전에는 작업 목록에 넣지 않았어요.

### 배포기 현황 (갱신: 2026-11-14)

| 확인 | 결과 |
|---|---|
| `helm lint`, `helm template` (운영계 값) | 통과 |
| 임시 nginx 이미지 `docker build` | 성공. 이후 앱 팀원의 Dockerfile로 대체됨 |
| 컨테이너 실행과 HTTP 응답 (로컬) | 못 함 (실행 도구가 막음) |
| `main` 이미지 빌드 (amd64, arm64) | 성공. `open-attendee-dev` 태그 3개, 공개 |
| `open-attendee-stg` 이미지 | 없음 |
| `open-attendee` (prd) 이미지 | 옛 태그 `0.1.0`, `0.1.1`만 있음. Image Updater 규칙(`r<번호>-<sha>`)에 안 맞음 |
| 도메인 CNAME 3개 | 생성함 |
| 클러스터 앱 상태 | 직접 못 봄 (이 컴퓨터의 `kubectl`이 로컬 `orbstack`을 가리킴) |
| `attendee.dev`, `attendee.stg` 주소 | HTTP 503 |
| `attendee.app` 주소 | 응답 없음 |

- 범위 변경: 설치 환경은 웹앱으로 줄이고, 배포는 온프레미스 k8s + Helm 네이티브만 해요. 맥북, iOS, AWS EKS, ECS는 [로드맵](docs/ROADMAP.md)으로 넘겼어요.
- 끝남: [PR #6](https://github.com/jyje/kirothon-team-032/pull/6)과 [PR #270](https://github.com/jyje/cluster/pull/270) 병합, 브랜치 3개 push, CNAME 3개.
- 진행 중: [PR #271](https://github.com/jyje/cluster/pull/271)(봉인 시크릿)은 병합 전이에요. 병합돼야 파드가 떠요. OpenAI 키(`OPENAI_API_KEY`)도 `.env`에서 읽어 값을 출력하지 않고 dev·stg·prd 시크릿 3개에 봉인해 이 PR에 더했어요.
- 막힌 것: `stg`, `prd` 이미지 빌드. 새 브랜치는 바뀐 파일이 없어 빌드가 안 돌았고, 수동 실행(`gh workflow run`)은 실행 도구가 막았어요. 사람이 직접 실행해야 해요.
- 아직 안 함: GHCR 패키지 공개 설정, Homer 대시보드 표시, Bedrock·OpenAI 같은 선택 키, 클러스터에서 `Healthy` 확인.
- 확인 못 한 것: 클러스터 앱 상태. 사람이 Argo CD 화면에서 확인했어요.
- 클러스터에는 직접 적용하지 않았어요. `kubectl`과 `argocd`는 쓰지 않았어요.

### 디자이니 현황 (갱신: 2026-11-14)

- 끝남: 디자인 시스템, 스킬, 스토리보드, Cloudscape 참고 자료. 모두 병합됨.
- 새로 한 것: Vue 프런트를 가볍게 검토했어요. 웹앱이 디자인 토큰을 실제로 쓰고 있어요. 고칠 점 5가지는 제안만 했고, 사람의 선택을 기다려요.
- 아직 안 함: 스토리보드대로 타이머 컴포넌트와 템플릿 구현. 프런트 고칠 점 5가지 적용.
- 확인 못 한 것: 원본 JS(한마디 문구, 프리셋 시간, 마감 저장 방식), S7·S8 화면 모습. 프런트 `typecheck`와 `build` 결과.
- 에이전트는 `main`에 직접 push하지 않았어요. 다른 팀원의 변경은 PR에 넣지 않았어요.

### 문서기 현황 (갱신: 2026-11-14)

- 끝남: slidev 초안과 빌드, 스킬 2개 가져오기, 커밋 10개와 [PR #1](https://github.com/jyje/kirothon-team-032/pull/1), `AGENTS.md` 규칙. PR #1은 사람이 `main`에 병합했어요. `main`에 `slidev/`, `AGENTS.md`, 스킬 2개가 있어요.
- 바뀐 것: 제 slidev 초안은 기획 단계 뼈대였어요. 지금 구현에 맞춘 12쪽 발표자료와 `PRESENTATION.pdf`는 [PR #11](https://github.com/jyje/kirothon-team-032/pull/11)에서 새로 써서 `main`에 병합됐어요. 이 PR은 제가 만들지 않았어요.
- 갱신: PR #11 브랜치에 기대 효과를 확인된 것만 남기는 수정(`f370e49`)과 Pretendard·Rubik 글꼴을 PDF에 넣는 커밋(`8299d73`)이 더해졌어요.
- 갱신: README에 외부 코드와 디자인의 출처와 라이선스가 적혔고(`476d914`), 평가 문서의 제출 체크리스트에 확인한 항목이 표시됐어요(`b51c009`). 둘 다 `main`에 들어 있어요.
- 아직 안 함: 제 초안의 `npm run dev` 확인, 영문 덱, 화면 확인. 발표자 이름, 발표 시간 같은 빈칸도 남았어요. 발표자료는 PR #11이 이어받았어요.
- 일부러 보류: `README.md`(이후 [PR #3](https://github.com/jyje/kirothon-team-032/pull/3)에서 새로 작성돼 병합됨), `docs/team.md`(Bot 담당이 추정), `records/`(`docs/`와 겹치는지 미확인).
- 알려진 문제: 검증 스크립트가 `skills/<이름>` 스코프를 막아요. `main`에도 그대로예요. 그래서 스킬 커밋 4개가 검증에 실패해요. 고치는 후속 커밋이 필요해요.
- 팀 활동이 곧 끝나서 새 작업은 시작하지 않아요. 문서 다듬기는 프로젝트 중반으로 미뤘어요.
- 에이전트는 `main`에 직접 push하지 않았어요.

### 정책이 현황 (갱신: 2026-11-14)

- 사람이 검토하고 병합해요. 에이전트는 `main`에 직접 push하지 않아요.
- 코드는 바꾸지 않았어요. 문서만 추가했어요.
- 확인한 것: `.env`는 `.gitignore`로 막혀 있고 추적되지 않아요.
- 아직 안 한 것: 커밋 이력 전체의 비밀 정보 검사, 의존성 취약점 점검. 제출 전 체크리스트에 넣었어요.

### AI마니아 검증 현황 (갱신: 2026-11-14)

| 공급자 | 실제 호출 | 비고 |
|---|---|---|
| OpenAI | 성공 | `gpt-4o-mini` |
| Codex | 성공 | 로컬 로그인 사용, Strands 경유 `codex exec` |
| Bedrock | 아직 못 함 | `.env`에 키 없음. 시험은 가짜 응답으로 통과 |

- 단위 시험 21개 통과.
- 아직 안 한 것: Docker 빌드 실행(메모리 부족으로 보류), Bedrock 실제 호출, 커밋.
- Codex는 글만 만들어요. 도구 호출과 스트리밍은 안 돼요.
- 저장소 반영: Strands 전환 작업은 `crew/provider/strands-factory` 브랜치에 커밋돼 있었고, 체크아웃된 브랜치에는 옛 코드가 남아 있었어요. 그 브랜치의 `provider-manager/`를 작업 폴더로 가져왔어요. `factory.py`, `Dockerfile`, `docker-entrypoint.sh`, `.dockerignore`가 새로 생기고 `base.py`, `bedrock.py`, `openai_api.py`, `registry.py`는 없어졌어요. 커밋과 push는 안 했어요.
- 정리: 다른 곳에 남은 빈 작업 폴더 2개와 그 브랜치 2개, 빈 워크스페이스 폴더 7개, 빌드 찌꺼기(`src/build/`, `egg-info`, `__pycache__`)를 지웠어요. 지우기 전에 변경이 없고 커밋이 저장소에 있는지 확인했어요.

## 개발 과정에서 바뀐 점

- 작업 위치를 임시 폴더에서 `/Users/jyje/repo/jyje/kirothon-team-032/provider-manager/`로 옮겼어요. 이전 폴더는 지웠어요.
- LangChain에서 Strands SDK로 바꿨어요. 공급자만 갈아 끼우고 에이전트는 한 곳에서만 만들어요.
- Codex는 항상 설치하지 않고 `CODEX_ENABLED=true`일 때만 설치해요.
- AI마니아: 작업 위치를 한 번 더 바꿨어요. 임시 폴더(`~/.kiro/crew/...`)에서 만든 결과를 모두 `/Users/jyje/repo/jyje/kirothon-team-032`로 옮기고, 임시 쪽은 비웠어요. 기준 워크스페이스는 이 저장소의 `.git`이에요.
- 문서기: 커밋 메시지를 영문에서 한글 허용으로 바꿨어요. 스킬 문서와 검증 스크립트도 같이 고쳤어요.
- 배포기: 임시 nginx 차트로 시작했지만, 앱 팀원이 실제 앱 차트와 Dockerfile을 올려서(PR #5) 그 차트를 기준으로 맞췄어요.
- 배포기: 환경(dev, stg, prd)을 브랜치로 나누고 브랜치마다 이미지 이름을 다르게 했어요. `main`은 `dev`로 바뀔 때까지 `-dev` 이미지를 만들어요.
- 배포기: 설치 환경을 웹앱 + 온프레미스 k8s로 줄였어요.
- 처음엔 파키스탄 대회 페이지의 점수표와 참가 자격까지 문서에 넣었어요. 이 행사는 서울 AWS KRUG, AWS 대학생 커뮤니티 모임 중심이라는 말을 듣고, 거버넌스 4항목만 남기고 나머지는 뺐어요. 기준은 `SUBMISSION_GUIDE.md`예요.

## 어려웠던 점과 해결 방법

- 대회 페이지 본문이 CSS에 묻혀 있어서, `style`과 `script`를 지운 뒤 텍스트만 뽑아 읽었어요.
- Codex는 글을 만드는 공개 호출 방법이 없었어요. `codex exec`를 감싸는 Strands 모델을 직접 만들어 풀었어요.
- 컨테이너에서 Codex 로그인이 걱정이었어요. 기기 로그인을 쓰고 `~/.codex`를 볼륨으로 남기는 방식으로 정했어요. 끝까지 실행해 보진 못했어요.
- 에이전트 실행 환경의 샌드박스가 켜지지 않아 첫 명령이 실패했어요. 샌드박스 없이 읽기 명령만 다시 실행했어요.
- 디자이니: 작업 폴더가 비어 있어서 구현을 멈추고 물었어요. 팀 폴더 `kirothon-team-032`가 기준이라는 답을 받고 거기로 맞췄어요.
- AI마니아: 처음 두 번은 엉뚱한 위치(임시 폴더, 빈 `event-kirothon2026`)에 만들었어요. 기준 경로를 물어 `kirothon-team-032`로 다시 만들고 옛 폴더를 지웠어요.
- AI마니아: "워크스페이스를 모두 검토했나요?"라는 물음에 확인하지 않은 곳까지 다 봤다고 말할 뻔했어요. 실제로 본 곳만 말하고, 나머지는 읽기만 해서 확인한 뒤(모두 빈 폴더) 지웠어요. 이 일은 교훈으로 저장했어요.
- AI마니아: Strands 작업이 다른 브랜치에만 있어서 체크아웃된 코드와 어긋났어요. 브랜치를 바꾸거나 합치지 않고, 해당 폴더만 가져오는 방식으로 풀었어요.
- 디자이니: 일꾼 세션이 열리지 않아 직접 작업했어요.
- 디자이니: GPG 서명이 막혀 커밋이 실패했어요. 설정을 바꾸지 않고 멈춰서 물었고, 승인을 받아 서명 없이 커밋했어요.
- 문서기: Kiro Crew 프로세스가 `~/.gnupg`를 읽지 못해 서명 커밋이 계속 실패했어요. 전체 디스크 접근 권한을 주고 재시작해도 풀리지 않았어요. 서명 없는 커밋을 승인받아 진행했고, 이제 Bot 커밋은 서명 없이 만들어 PR로만 올려요.
- 문서기: 커밋 전 검증에서 셸의 `&&` 때문에 실패를 놓치고 커밋까지 진행됐어요. 원인은 검증 스크립트가 스킬 문서가 쓰라고 한 `skills/<이름>` 스코프를 막은 것이에요. 사실대로 보고했고 후속 커밋으로 고칠 계획이에요.
- 문서기: 처음에 빈 `event-kirothon2026` 경로에서 작업을 찾다가 헤맸어요. `/Users/jyje/repo/jyje/kirothon-team-032`가 기준이라는 답을 받고 맞췄어요.
- 배포기: 처음엔 Docker 소켓 접근이 막혀 빌드를 못 했어요. 나중에 데몬에 연결돼 빌드는 성공했어요.
- 배포기: `docker run -d`는 실행 도구가 막았어요. 우회하지 않고, 터미널에서 직접 돌릴 명령을 남겼어요.
- 배포기: 이 갱신 때도 샌드박스 오류로 `Bash`가 안 돼서 파일 읽기와 편집만 했어요.
- 배포기: 시크릿 `open-attendee`가 없어 Argo CD가 오류를 냈어요. 차트가 시크릿을 넣는 칸(`extraResources`)이 없어서 봉인 파일을 `apps/` 폴더에 따로 뒀어요. 비밀번호는 제가 볼 수 없어서 사람이 직접 봉인하도록 명령을 남겼어요.
- 배포기: `stg`, `prd` 브랜치를 push해도 이미지 빌드가 안 돌았어요. 빌드가 폴더 변경에만 반응하기 때문이에요. 수동 실행은 실행 도구가 막아서, 사람이 직접 실행할 명령을 남겼어요.
- 배포기: 조사 중 `jyje/cluster`의 `.gitignore`된 평문 비밀 파일을 실수로 읽어 값이 화면에 나왔어요. 파일은 Git에 올라가지 않았고, 값은 어디에도 옮기거나 기록하지 않았어요. 바로 사용자에게 알렸어요.
- 배포기: `jyje/cluster`에는 영어로만 올려야 하는데 처음 PR 본문을 한국어로 썼어요. 본문을 영어로 다시 쓰고, 이 규칙을 `jyje/cluster` 전용으로 기억해 뒀어요.
- 디자이니: 이 갱신 때도 샌드박스 오류(`sandbox_apply: Operation not permitted`)로 `git status`는 못 돌렸어요. 파일 읽기와 편집만 했어요. 이 변경은 커밋하지 않았어요.
- 디자이니: 프런트 검토 때도 `Bash`가 같은 샌드박스 오류로 실패했어요. 읽기 명령(`ls`, `find`, `cat`)만 샌드박스 없이 다시 실행했고, 쓰기 명령은 하지 않았어요.
- 디자이니: Vue 프런트가 아직 `main`이 아닌 `.worktrees/webapp`에 있어서 거기서 읽었어요. 그 워크트리에는 커밋 안 한 변경도 있었는데 건드리지 않았어요.
