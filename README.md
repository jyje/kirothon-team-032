<div align="center">

# Open Attendee

밋업 들으러 가는 당신을 위한 요약 도구

[![CI](https://github.com/jyje/open-attendee/actions/workflows/ci.yml/badge.svg)](https://github.com/jyje/open-attendee/actions/workflows/ci.yml)
[![Build image](https://github.com/jyje/open-attendee/actions/workflows/build.yml/badge.svg)](https://github.com/jyje/open-attendee/actions/workflows/build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

밋업, 이벤트, 학회, 미팅에서 직접 기록하고 참고자료를 받아, AI로 요약해 원하는 형태로 정리하는 필기 도구입니다. 정리된 초안에 내 인사이트를 더한 뒤 최종 검토합니다. 이 프로젝트는 AWS Kiro Crew로 구성한 AI 에이전트 팀과 함께 만들었습니다.

**Demo:** [https://attendee.app.jyje.online](https://attendee.app.jyje.online) (prd). 소유자 1명용 로그인이 필요합니다. 컨테이너 이미지는 `ghcr.io/jyje/open-attendee`(prd), `-stg`, `-dev`로 공개되어 있고, 아래 6절의 명령으로 직접 실행해 볼 수도 있습니다.

**발표자료:** [`PRESENTATION.pdf`](PRESENTATION.pdf) (12쪽)

> **지금 구현 단계:** 기록(필기, 사진, 자료 첨부, 녹음 동의 게이트)부터 AI 요약, 출처가 붙은 초안, 검토와 승인, 마크다운·HTML 내보내기까지 동작합니다. 브라우저 녹음과 CPU 전사는 기능 설정으로 켤 수 있습니다. 기능별 상태는 2절 표에 있습니다.

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
| 발표자료(PDF·PPTX) 첨부와 페이지별 텍스트 추출 (30MB까지) | 자료를 직접 읽고 요약해야 함 | **동작** | [`processors/docs.py`](webapp/src/open_attendee/processors/docs.py), [`assets.py`](webapp/src/open_attendee/assets.py) |
| 참고자료 받기 (PDF, TXT, MD) | 흩어진 참고자료를 따로 찾아야 함 | **동작** (URL 가져오기는 구현 전) | [`assets.py`](webapp/src/open_attendee/assets.py) |
| 녹음과 STT 전사 (동의 확인 후에만 처리) | 3~4시간 녹음을 직접 정리해야 함 | **녹음과 로컬 전사 구현**, 기본 설정에서 꺼져 있음 | [`consent.py`](webapp/src/open_attendee/consent.py) |
| AI 요약, 초안 (모든 문장에 출처, 출처가 뒷받침하는지 AI가 한 번 더 확인) | 요약에 시간이 많이 듦 | **동작** (요청 안에서 동기 실행) | [`llm.py`](webapp/src/open_attendee/llm.py), [`drafts.py`](webapp/src/open_attendee/drafts.py), [`SummaryPanel.vue`](webapp/frontend/src/components/SummaryPanel.vue) |
| 원하는 템플릿 선택, 저장, 재사용 | 원하는 형태로 정리하는 기능이 부족함 | 블로그 템플릿 1개만 고정, 선택·저장은 구현 전 | |
| 인사이트 추가와 최종 검토 (미검증 문장 처리, 사람만 승인, 승인한 초안만 내보내기) | AI 요약만으로는 내 생각이 빠짐 | **동작** (마크다운·HTML) | [`DraftPanel.vue`](webapp/frontend/src/components/DraftPanel.vue), [`drafts.py`](webapp/src/open_attendee/drafts.py) |

설치 환경은 맥북, 모바일(반응형 웹), AWS, 온프레미스입니다. 자세한 방법은 6절에 씁니다.

### 구조

```text
브라우저 (Vue 3 + Vite)
   │  /api  (JSON, 쿠키 세션, CSRF 토큰)
   ▼
FastAPI 서버 ─ SQLite (SQLModel) ─ 파일 저장소 (로컬 볼륨 또는 S3)
   │
   └─ provider-manager (OpenAI / Bedrock, Strands 모델 팩토리)
```

- 이미지 하나로 나옵니다. Vue 화면을 빌드해서 FastAPI가 같이 서빙합니다.
- 서버는 `/api` 아래 JSON만 냅니다. 화면은 [`design-system/`](design-system)의 토큰과 글꼴을 그대로 씁니다.
- 컨테이너는 비루트(uid 10001)로 8080 포트에서 실행합니다. amd64와 arm64 이미지를 모두 만듭니다.

### 개인정보와 보안 기본값

- **녹음은 동의 기록이 있어야만 처리합니다.** 서버가 파일을 저장하기 전에 동의 상태를 확인합니다. 본인 혼자 말한 음성 메모만 예외입니다. 지금 배포에서는 녹음 기능 자체가 꺼져 있습니다(`FEATURE_RECORDING=false`).
- **사진의 위치 정보(EXIF)는 저장하지 않습니다.** 촬영 시각만 남깁니다.
- 소유자 1명의 비밀번호(argon2 해시)로 로그인하고, 로그인 시도는 접속자 IP별로 분당 5회까지 받으며, 쓰기 요청은 CSRF 토큰을 검사합니다.
- 비밀 값은 환경 변수와 Kubernetes Secret으로만 받고, 저장소와 이미지에는 넣지 않으며 로그에서는 가립니다.

---

## 3. 사용 시나리오

1. 발표를 들으며 웹에 필기하고, 사진과 발표자료를 첨부합니다. 녹음이 켜진 환경에서는 동의를 선택하고 브라우저에서 녹음합니다.
2. AI 에이전트가 기록을 요약하고, 블로그 템플릿에 맞춰 출처가 붙은 초안을 만듭니다.
3. 사용자가 초안에 자기 인사이트를 더하고, 미검증 문장을 처리한 뒤 승인하고, 마크다운이나 HTML로 내려받습니다.

## 4. 기대 효과

- **서비스 10개 이상 → 1개**: 필기, 사진, PDF, 요약, 내보내기를 한곳에서 합니다.
- **새 구독료 없음**: 내 AWS, 내 서버, 내 AI 키를 씁니다. 사용료는 따로 듭니다.
- **믿을 수 있는 요약**: 모든 문장에 출처가 붙고, 확인되지 않은 문장은 표시됩니다.
- **개인정보 보호**: 사진 위치 정보는 지우고, 동의 없는 녹음은 처리하지 않습니다.
- **어디서든 실행**: 이미지 하나로 맥북, AWS, 온프레미스에서 돕니다.

정리 시간 목표는 30분 이내입니다. 새로 승인한 초안에는 마지막 필기 수정이나 자료 추가부터 승인까지의 경과 시간이 표시됩니다. 대기 시간도 포함되며, 수작업과 같은 자료로 비교한 결과는 [#62](https://github.com/jyje/open-attendee/issues/62)에서 추적합니다.

## 5. 차별점

- 여러 플랫폼에 흩어진 기능을 한곳에서 씁니다.
- 새 구독료 대신 내 AWS, 온프레미스, AI 구독을 씁니다.
- 내게 필요한 세부 기능을 직접 정합니다.
- 초안의 모든 문장에 출처를 붙이고, 확인되지 않은 문장은 사람이 처리하기 전에는 내보내지 않습니다.

---

## 6. 설치와 실행

필요한 것: [uv](https://docs.astral.sh/uv/)(Python 3.13), Node.js 22, Docker(컨테이너로 실행할 때).

```bash
git clone https://github.com/jyje/open-attendee.git
cd open-attendee
```

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

`main`(과 `dev`, `stg`, `prd`)에 머지되면 GitHub Actions가 amd64와 arm64 이미지를 만들어 `r<번호>-<커밋>` 태그로 올립니다. `main`과 `dev`는 `ghcr.io/jyje/open-attendee-dev`, `stg`는 `-stg`, `prd`는 `ghcr.io/jyje/open-attendee`입니다. 차트의 기본 이미지는 `prd`용이라서 개발 이미지는 `--set image.repository=...`로 바꿉니다.

```bash
helm upgrade --install open-attendee ./helm -n open-attendee --create-namespace \
  --set image.repository=ghcr.io/jyje/open-attendee-dev \
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

Playwright 테스트는 실제 프런트엔드 빌드와 임시 FastAPI·SQLite를 연결합니다. 데스크톱 Chromium에서 로그인, 필기 저장, 템플릿 복제·저장, 초안 승인과 HTML·Markdown 다운로드를 확인합니다. 모바일 Chromium 에뮬레이션에서는 사이드바와 키보드 업로드를 확인합니다. [#43](https://github.com/jyje/open-attendee/issues/43)

저장소 루트에서 실행합니다.

```bash
(cd webapp/src && uv sync --frozen)
(cd webapp/frontend && npm ci && npx playwright install chromium && npm run test:e2e)
```

실패 시 로컬에서는 `webapp/frontend/test-results/`의 스크린샷과 추적 파일을 확인하고, GitHub CI에서는 `browser-test-results` 아티팩트를 확인합니다. 초안 생성에는 테스트 모델 응답을 사용합니다.

---

## 8. 현재 상태와 로드맵

**구현 정도:** 기록(로그인, 행사, 필기, 사진, PDF·참고자료, 녹음 동의 게이트)과 AI 요약, 출처가 붙은 초안, 지지 판정, 검토·승인, 마크다운 내보내기가 동작하고 테스트와 CI가 있습니다. 실제 OpenAI 호출로 끝까지 확인했지만, AI의 지지 판정은 느슨해서 추정 문장도 통과했습니다. 그래서 사람의 검토와 승인이 필수입니다.

**자료** 화면의 **녹음 동의**에서 행사별 동의 날짜와 방법을 기록하고 철회할 수 있습니다. 철회한 동의는 새 녹음 자료를 올리는 데 사용할 수 없습니다. [#64](https://github.com/jyje/open-attendee/issues/64)

[한국 행사 녹음과 전사 자료 안내](docs/recording-privacy-kr.md)에 녹음, 전사, 모델 전송, 공개 기준과 배포별로 확인할 항목을 정리했습니다. [#85](https://github.com/jyje/open-attendee/issues/85)

동의를 철회하면 연결된 음성 다운로드와 전사 조회가 차단되고, 대기 중이거나 실행 중인 전사 요청이 취소됩니다. 해당 음성을 입력으로 사용한 요약·초안은 조회와 내보내기가 차단되며, 유효한 자료로 다시 만들 수 있습니다. 전체 출처가 저장되지 않은 예전 결과는 영향 범위를 확인할 수 없으면 접근을 제한합니다. 원본과 전사는 저장된 자료의 **지우기**로, 저장된 요약·초안은 **행사 삭제**로 제거할 수 있습니다. 이미 내보낸 파일은 받은 곳에서 별도로 관리해야 합니다. [#65](https://github.com/jyje/open-attendee/issues/65)

녹음이 켜진 환경의 **자료** 화면에서 행사 동의를 선택하면 브라우저로 녹음을 시작하고 중지한 뒤 저장할 수 있습니다. [#67](https://github.com/jyje/open-attendee/issues/67)

녹음이 서버에 저장된 뒤 응답이 끊겨 **녹음 저장**을 다시 눌러도 같은 녹음은 한 건으로 유지됩니다. 장시간 녹음의 네트워크 중단 검증에서 발견한 문제입니다. [#79](https://github.com/jyje/open-attendee/issues/79)

브라우저가 마이크 녹음 중단을 감지하면 화면에 알립니다. 중단 전까지 기록된 부분은 **녹음 저장**으로 저장할 수 있습니다. [#81](https://github.com/jyje/open-attendee/issues/81)

로컬 전사기가 설정된 환경에서는 **자료**에서 저장한 음성의 전사를 요청하고 시간 구간을 볼 수 있습니다. 전사 구간은 요약과 초안의 출처로 사용할 수 있습니다. [#70](https://github.com/jyje/open-attendee/issues/70)

자료 화면에서 **전사 후 음성 원본 보관**을 행사별로 선택합니다. 기본값은 삭제이며, 전사 구간이 저장된 뒤 원본 삭제를 별도 작업으로 실행합니다. [#71](https://github.com/jyje/open-attendee/issues/71)

**자료**에서 사진의 **얼굴 확인**을 열어 자동 후보를 검토하고 필요한 영역을 직접 보완할 수 있습니다. 확인한 영역의 흐림은 저장 사진과 축소판 모두에 적용됩니다. [#74](https://github.com/jyje/open-attendee/issues/74)

웹앱의 요약과 초안은 SQLite 작업 큐에서 실행됩니다. 화면은 서버 전송 이벤트(SSE)로 상태를 갱신하고, 새로고침하면 대기 중이거나 실행 중인 작업을 다시 연결합니다. 워커는 실패한 작업을 최대 세 번까지 시도하며, 중단된 작업은 임대가 만료되면 회수합니다. [#47](https://github.com/jyje/open-attendee/issues/47)

승인한 초안은 HTML 파일로도 내려받을 수 있습니다. AI 생성 표시, 미검증 의견 표시, 출처가 포함되며 인터넷 연결 없이 브라우저에서 열립니다. [#41](https://github.com/jyje/open-attendee/issues/41)

사이드바의 **템플릿**에서 블로그·LinkedIn 형식과 사용자 템플릿을 복제할 수 있습니다. 편집한 문체와 섹션을 다음 행사에서도 사용하며, 만든 초안에는 당시 템플릿의 이름과 섹션이 남습니다. [#39](https://github.com/jyje/open-attendee/issues/39)

첨부 파일은 로컬 볼륨이나 S3에 저장할 수 있습니다. 설정은 [배포 가이드](docs/deploy.md#s3-첨부-저장소)를 참고하세요. [#53](https://github.com/jyje/open-attendee/issues/53)

배포 후에는 [상태 점검 명령](docs/deploy.md#4-확인과-되돌리기)으로 준비 상태, LLM 설정, 첨부 저장소를 확인할 수 있습니다. [#57](https://github.com/jyje/open-attendee/issues/57)

AI 문장을 수정하면 기존 연결 출처를 다시 확인합니다. 판정 결과가 연결된 자료의 실제 인용문을 포함해야 검증 상태로 저장됩니다. 사람은 승인 전에 근거를 검토합니다. [#31](https://github.com/jyje/open-attendee/issues/31) · [#33](https://github.com/jyje/open-attendee/issues/33)

**배포 환경 (반영됨)**
- 다단계 `Dockerfile`(화면 빌드, 서버 의존성, 실행), 비루트, 8080, amd64와 arm64. 로컬용 `docker-compose.yml`.
- `helm/`: 설정은 ConfigMap, 비밀은 미리 만든 Secret 참조, 데이터는 PVC, `/healthz` 확인, 복제본 1개.
- 환경별 Helm 값 파일은 `dev`, `stg`, `prd`에서 각각 발행한 이미지를 선택합니다. [#59](https://github.com/jyje/open-attendee/issues/59)
- CI: `ci.yml`(테스트, 린트, 화면 빌드, helm lint), `build.yml`(브랜치별 이미지, 불변 태그).
- microk8s에 맞춘 값: 기본 저장소가 NFS라서 SQLite를 `delete` 저널로 사용, 인그레스 `nginx`와 `nginx-letsencrypt-prod`, 업로드 본문 32m, 인그레스 뒤 접속자 IP별 로그인 제한(`FORWARDED_ALLOW_IPS`).

**로드맵 (아직 반영하지 않음)**
- 실제 기기의 장시간 마이크 녹음과 중단 복구 검증. [#68](https://github.com/jyje/open-attendee/issues/68)
- 수작업과 앱의 정리 시간 및 결과 품질 비교. [측정 절차와 합성 자료](docs/validation/event-summary-benchmark.md)를 준비했고, 사람의 작업 시간과 품질 측정이 남아 있습니다. [#62](https://github.com/jyje/open-attendee/issues/62)
- 데이터 보관 기간과 삭제 정책. [#84](https://github.com/jyje/open-attendee/issues/84)
- 여러 사용자와 공유, AWS GPU 전사. 이번 범위 밖입니다.

---

## 문서

- 배포 가이드: [`docs/deploy.md`](docs/deploy.md)
- Kiro를 어떻게 썼는지: [`BUILD_REPORT.md`](BUILD_REPORT.md), [`docs/KIRO_USAGE.md`](docs/KIRO_USAGE.md)
- 평가, 거버넌스, 보안 유의사항: [`docs/EVALUATION_GOVERNANCE_SECURITY.md`](docs/EVALUATION_GOVERNANCE_SECURITY.md)
- 발표자료: [`PRESENTATION.pdf`](PRESENTATION.pdf). 원본은 [`slidev/slides.md`](slidev/slides.md)이고, 글꼴은 Pretendard(한글)와 Rubik(영문 제목, 디자인 시스템)을 npm으로 묶어 PDF에 넣었습니다.

  ```bash
  cd slidev
  npm ci
  npm i --no-save playwright-chromium    # PDF 내보내기에 필요합니다
  npx slidev export --output ../PRESENTATION.pdf --wait 3000
  ```

## 출처와 라이선스

- 이 저장소의 코드는 [MIT](LICENSE)입니다. 화면, 서버, 배포 설정은 이 해커톤에서 새로 작성했습니다.
- **디자인**: [kirothon-timer.vercel.app](https://kirothon-timer.vercel.app/)에서 추출한 토큰([`design-system/`](design-system))과, AWS의 오픈소스 [Cloudscape](https://cloudscape.design/) 디자인 토큰 참고 자료(Apache-2.0, [`docs/references/cloudscape/`](docs/references/cloudscape)에 라이선스와 출처 포함).
- **글꼴**: `@fontsource`로 내려받는 Rubik(OFL-1.1), Rubik Mono One, Permanent Marker(Apache-2.0).
- **주요 라이브러리**: Vue, Vite, FastAPI, SQLModel, Pillow, pypdf, Strands Agents 등. 각 라이선스는 해당 패키지를 따릅니다.
- **CI 이미지 빌드 방식**은 작성자 본인의 저장소 [`jyje/mungchilog`](https://github.com/jyje/mungchilog)의 `build.yml` 구성을 참고했습니다.

## 디자인 시스템

- 토큰: [`design-system/tokens.css`](design-system/tokens.css)
- 규칙과 컴포넌트: [`design-system/DESIGN.md`](design-system/DESIGN.md)
- 에이전트 스킬: [`.agents/skills/kirothon-design-system/SKILL.md`](.agents/skills/kirothon-design-system/SKILL.md)

원본 디자인은 [kirothon-timer.vercel.app](https://kirothon-timer.vercel.app/)에서 추출했어요.

---

## 팀

- **팀 번호:** team-032 (해커톤 제출 당시 레포 이름은 `kirothon-team-032`였고, 이후 `open-attendee`로 옮겼습니다)
- **팀명:** Studio.R4iny (1인팀)

| 이름 | 역할 |
|---|---|
| 팀장이 (Bot) | 팀장 |
| 정책이 (Bot) | 평가 기준, 거버넌스, 보안 유의사항 문서와 Kiro 활용 증거, 정책 점검 |
| 문서기 (Bot) | 기획 문서와 공지 정리 <!-- 담당 확인 필요 --> |
| 배포기 (Bot) | 배포 <!-- 담당 확인 필요 --> |
| 디자이니 (Bot) | 디자인 시스템 <!-- 담당 확인 필요 --> |
| jyje | 1인팀 구성원 |

팀 구조와 근거는 [`docs/team.md`](docs/team.md)에 있습니다.
