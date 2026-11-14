<div align="center">

# Open Attendee

무언갈 들으러 가는 당신을 위한 필기 도구

[![CI](https://github.com/jyje/kirothon-team-032/actions/workflows/ci.yml/badge.svg)](https://github.com/jyje/kirothon-team-032/actions/workflows/ci.yml)
[![Build image](https://github.com/jyje/kirothon-team-032/actions/workflows/build.yml/badge.svg)](https://github.com/jyje/kirothon-team-032/actions/workflows/build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

밋업, 이벤트, 학회, 미팅에서 직접 기록하고 참고자료를 받아, AI로 요약해 원하는 형태로 정리하는 필기 도구입니다. 정리된 초안에 내 인사이트를 더한 뒤 최종 검토합니다. 이 프로젝트는 AWS Kiro Crew로 구성한 AI 에이전트 팀과 함께 만들었습니다.

**Demo:** 배포 주소는 클러스터 배포를 마친 뒤 채웁니다. 컨테이너 이미지는 [`ghcr.io/jyje/kirothon-team-032`](https://github.com/jyje/kirothon-team-032/pkgs/container/kirothon-team-032)에 공개되어 있고, 아래 6절의 명령으로 직접 실행해 볼 수 있습니다.

> **지금 구현 단계:** 기록 쪽(필기, 사진, 자료 첨부, 녹음 동의 게이트, 배포)은 동작합니다. AI 요약과 초안, 검증, 승인, 내보내기는 구현 중이거나 구현 전입니다. 기능별 상태는 2절 표에 있습니다.

---

## 1. 문제 정의

### 대상 사용자
밋업, 이벤트, 학회, 미팅에 참석하는 학생과 직장인.

### 문제 상황
참석자가 발표를 들으며 메모합니다. 나중에 내용을 요약하는 데 시간이 많이 들고, 메모는 여러 서비스에 흩어져 있습니다.

### 기존 방식과 한계
메모장, 노션, 음성 녹음 앱, 클로바 노트 같은 서비스는 기능이 좋습니다. 하지만 사용량 제한이 있고, 플랫폼이 여러 곳으로 나뉘어 있습니다. 내게 필요한 세부 기능이 없는 경우도 많습니다.

### 근거
직접 경험입니다. 밋업 한 번에 녹음이 3~4시간 나오고, PDF와 PPT가 많습니다. 기록에 쓰는 서비스는 10개 이상이고, 대부분 새 구독료가 듭니다.

### 목표
행사 중 필기(20장 이상), 녹음, 사진, 발표자료, 참고자료를 한곳에 모습니다. AI가 요약해 원하는 형태로 정리하고, 사용자가 자기 인사이트를 더한 뒤 최종 검토합니다. 사용자가 선호하는 일관된 템플릿으로 구성할 수 있습니다.

---

## 2. 핵심 기능

웹에서 필기하고, 녹음은 STT 모델로 글로 바꾸고, 사진과 자료를 첨부합니다. AI 에이전트가 이 기록을 요약하고 정리해 초안을 만듭니다. 이때 초안의 모든 문장에는 출처(어느 메모, 어느 쪽, 어느 사진)를 붙이고, 출처로 확인되지 않은 문장은 "미검증"으로 표시해서 사람이 검토하기 전에는 내보내지 않습니다.

| 기능 | 해결하는 불편 | 상태 | 코드 위치 |
|---|---|---|---|
| 웹 필기 편집기 (블록 단위, 입력을 멈추면 자동 저장) | 메모가 여러 서비스에 흩어짐 | **동작** | [`SessionDetailView.vue`](webapp/frontend/src/views/SessionDetailView.vue), [`sessions.py`](webapp/src/open_attendee/sessions.py) |
| 사진 첨부 (세션당 200장까지, EXIF 위치 정보 제거, 촬영 시각이 가까운 메모에 자동 연결) | 필기와 사진이 따로 있음 | **동작** | [`AssetsPanel.vue`](webapp/frontend/src/components/AssetsPanel.vue), [`processors/photo.py`](webapp/src/open_attendee/processors/photo.py) |
| 발표자료(PDF) 첨부와 텍스트 추출 (30MB까지) | 자료를 직접 읽고 요약해야 함 | **동작** (PPTX는 구현 전) | [`processors/docs.py`](webapp/src/open_attendee/processors/docs.py), [`assets.py`](webapp/src/open_attendee/assets.py) |
| 참고자료 받기 (PDF, TXT, MD) | 흩어진 참고자료를 따로 찾아야 함 | **동작** (URL 가져오기는 구현 전) | [`assets.py`](webapp/src/open_attendee/assets.py) |
| 녹음과 STT 전사 (동의 확인 후에만 처리) | 3~4시간 녹음을 직접 정리해야 함 | **동의 게이트만 동작**, 녹음과 전사는 꺼져 있음 | [`consent.py`](webapp/src/open_attendee/consent.py) |
| AI 요약, 정리 (출처가 붙은 항목) | 요약에 시간이 많이 듦 | 구현 중 | |
| 원하는 템플릿 선택, 저장, 재사용 | 원하는 형태로 정리하는 기능이 부족함 | 구현 전 | |
| 인사이트 추가와 최종 검토 (사람만 승인, 승인한 초안만 내보내기) | AI 요약만으로는 내 생각이 빠짐 | 구현 전 | |

설치 환경은 맥북, 모바일(반응형 웹), AWS, 온프레미스입니다. 자세한 방법은 6절에 씁니다.

### 구조

```text
브라우저 (Vue 3 + Vite)
   │  /api  (JSON, 쿠키 세션, CSRF 토큰)
   ▼
FastAPI 서버 ─ SQLite (SQLModel) ─ 파일 저장소 (로컬 볼륨, S3는 구현 전)
   │
   └─ provider-manager (OpenAI / Bedrock, Strands 모델 팩토리)
```

- 이미지 하나로 나옵니다. Vue 화면을 빌드해서 FastAPI가 같이 서빙합니다.
- 서버는 `/api` 아래 JSON만 냅니다. 화면은 [`design-system/`](design-system)의 토큰과 글꼴을 그대로 씁니다.
- 컨테이너는 비루트(uid 10001)로 8080 포트에서 실행합니다. amd64와 arm64 이미지를 모두 만듭니다.

### 개인정보와 보안 기본값

- **녹음은 동의 기록이 있어야만 처리합니다.** 화면이 아니라 서버가 업로드와 작업 등록에서 두 번 막습니다. 본인 혼자 말한 음성 메모만 예외입니다. 지금 배포에서는 녹음 기능 자체가 꺼져 있습니다(`FEATURE_RECORDING=false`).
- **사진의 위치 정보(EXIF)는 저장하지 않습니다.** 촬영 시각만 남깁니다.
- 소유자 1명의 비밀번호(argon2 해시)로 로그인하고, 로그인 시도는 접속자 IP별로 분당 5회까지 받습니다. 쓰기 요청은 CSRF 토큰을 검사하고, 다른 소유자의 데이터는 "없음"으로만 응답합니다.
- 비밀 값(API 키, 비밀번호 해시, 쿠키 서명 키)은 환경 변수와 Kubernetes Secret으로만 받고, 저장소와 이미지에는 넣지 않습니다. 로그에서는 가려서 남깁니다.

---

## 3. 사용 시나리오

1. 발표를 들으며 웹에 필기하고, 사진과 발표자료를 첨부합니다. (녹음은 동의를 확인한 뒤 켤 수 있도록 준비 중입니다.)
2. AI 에이전트가 기록을 요약하고, 선택한 템플릿에 맞춰 출처가 붙은 초안을 만듭니다. (구현 중)
3. 사용자가 초안에 자기 인사이트를 더하고, 미검증 문장을 처리한 뒤 최종 검토를 마칩니다. (구현 전)

## 4. 기대 효과

- 정리 시간: 2~3시간 → 30분 이내 (목표치입니다. 아직 측정하지 않았습니다.)

## 5. 차별점

- 여러 플랫폼에 흩어진 기능을 한곳에서 씁니다.
- 새 구독료 대신 내 AWS, 온프레미스, AI 구독을 씁니다.
- 내게 필요한 세부 기능을 직접 정합니다.
- 초안의 모든 문장에 출처를 붙이고, 확인되지 않은 문장은 사람이 처리하기 전에는 내보내지 않습니다.

---

## 6. 설치와 실행

필요한 것: [uv](https://docs.astral.sh/uv/)(Python 3.13), Node.js 22, Docker(컨테이너로 실행할 때).

### 로컬 개발 (맥북)

```bash
# 1. 환경 변수 만들기 (webapp/.env는 커밋되지 않습니다)
cp webapp/.env.example webapp/.env
#    OWNER_PASSWORD_HASH: 비밀번호의 argon2 해시. 만드는 명령은 webapp/.env.example 안에 있습니다.
#    SESSION_SECRET: 아무 긴 문자열 (python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. 서버 (자동 재시작)
cd webapp/src
uv sync
uv run uvicorn open_attendee.main:app --reload --env-file ../.env --port 8080

# 3. 화면 (다른 터미널, 저장하면 바로 반영)
cd webapp/frontend
npm ci
npm run dev        # http://localhost:5173 으로 접속합니다
```

로그인 쿠키에 `Secure`가 붙어 있어서 `http://localhost`나 `https://`에서만 로그인이 유지됩니다.

### 컨테이너 (compose)

```bash
cp webapp/.env.example webapp/.env     # 값을 채웁니다
docker compose up --build              # http://localhost:8080
```

### Kubernetes (microk8s, AWS, 온프레미스)

`main`에 머지되면 GitHub Actions가 amd64와 arm64 이미지를 만들어 `ghcr.io/jyje/kirothon-team-032:r<번호>-<커밋>`으로 올립니다. 그 태그로 helm 차트를 배포합니다.

```bash
helm upgrade --install open-attendee ./helm -n open-attendee --create-namespace \
  --set image.tag=<CI가 만든 태그>
```

비밀(Secret) 만들기, 환경 변수 표, 인그레스, 되돌리기는 [`docs/deploy.md`](docs/deploy.md)에 있습니다. AI 요약을 쓰려면 `OPENAI_API_KEY` 또는 `AWS_BEARER_TOKEN_BEDROCK`을 Secret에 더합니다.

## 7. 테스트

```bash
# 서버: 린트와 테스트 (속성 기반 테스트 포함)
cd webapp/src
uv run ruff check . && uv run ruff format --check . && uv run pytest

# 화면: 타입 검사와 빌드
cd webapp/frontend && npm run build

# provider-manager
cd provider-manager/src && uv run pytest

# helm 차트
helm lint helm --set image.tag=test
```

위 검사는 PR과 `main`에서 [`ci.yml`](.github/workflows/ci.yml)이 같은 명령으로 실행합니다. 이미지 빌드는 [`build.yml`](.github/workflows/build.yml)이 PR에서는 검증만 하고, `main`에서만 게시합니다.

테스트가 확인하지 못하는 것: 실제 LLM 호출(가짜 응답으로만 시험), 실제 클러스터 배포, 사용자가 쓰는 브라우저별 화면(헤드리스 Chrome으로만 확인).

---

## 문서

- 요구사항, 설계, 작업 목록: [`.kiro/specs/open-attendee-webapp/`](.kiro/specs/open-attendee-webapp)
- 배포 가이드: [`docs/deploy.md`](docs/deploy.md)
- Kiro를 어떻게 썼는지: [`BUILD_REPORT.md`](BUILD_REPORT.md), [`docs/KIRO_USAGE.md`](docs/KIRO_USAGE.md)
- 평가, 거버넌스, 보안 유의사항: [`docs/EVALUATION_GOVERNANCE_SECURITY.md`](docs/EVALUATION_GOVERNANCE_SECURITY.md)

## 디자인 시스템

- 토큰: [`design-system/tokens.css`](design-system/tokens.css)
- 규칙과 컴포넌트: [`design-system/DESIGN.md`](design-system/DESIGN.md)
- 에이전트 스킬: [`.agents/skills/kirothon-design-system/SKILL.md`](.agents/skills/kirothon-design-system/SKILL.md)

원본 디자인은 [kirothon-timer.vercel.app](https://kirothon-timer.vercel.app/)에서 추출했어요.

---

## 팀

- **팀 번호:** team-032 (레포 이름 기준, 명찰 번호와 맞는지 확인 필요)
- **팀명:** Studio.R4iny (1인팀)

| 이름 | 역할 |
|---|---|
| mate (Bot) | 팀장, 메인 개발자 |
| 정책이 (Bot) | 평가 기준, AWS 정책, 해커톤 규약 조사 <!-- 담당 확인 필요 --> |
| 문서기 (Bot) | 기획 문서와 공지 정리 <!-- 담당 확인 필요 --> |
| 배포기 (Bot) | 배포 <!-- 담당 확인 필요 --> |
| 디자이니 (Bot) | 디자인 시스템 <!-- 담당 확인 필요 --> |
| jyje | 1인팀 구성원 |

팀 구조와 근거는 [`docs/team.md`](docs/team.md)에 있습니다.
