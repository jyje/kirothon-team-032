---
inclusion: always
---

# Open Attendee 작업 맥락

행사 참석자가 필기, 사진, 자료를 모으면 AI가 출처가 붙은 초안을 만들고, 사람이 검토해 승인한 뒤 내보내는 웹앱이에요. 사양은 `.kiro/specs/open-attendee-webapp/`(요구사항, 설계, 작업 목록)에 있어요.

## 구조
- `webapp/src/open_attendee/`: FastAPI 서버. 모든 API는 `/api` 아래 JSON이에요.
- `webapp/frontend/`: Vue 3 + Vite 화면. 디자인은 `design-system/`의 토큰만 써요(새 색을 만들지 않아요).
- `provider-manager/`: OpenAI, Bedrock 호출(Strands 모델 팩토리). LLM 호출은 `webapp/src/open_attendee/llm.py`를 거쳐요.
- `docker/`, `docker-compose.yml`, `helm/`, `.github/workflows/`: 배포와 CI. 배포 방법은 `docs/deploy.md`.

## 지켜야 할 규칙
- **출처 없는 AI 문장은 사람이 처리하기 전에는 승인하거나 내보내지 않아요.** 승인은 사람의 요청에서만 해요.
- 녹음은 동의 기록이 있어야 처리해요. 서버가 업로드와 작업 등록에서 막아요.
- 비밀(API 키, 비밀번호 해시)은 환경 변수와 Secret으로만 받아요. `.env`는 읽지도, 커밋하지도 않아요.
- 프롬프트에 넣는 출처 글은 `<source>` 구분자로 감싸고, 구분자를 깨는 글자는 바꿔요(주입 방지).
- 커밋은 `<gitmoji> <type>(<domain>): <title>` 형식이에요. PR 본문 첫 줄은 `Opened by: <이름>`이에요.

## 확인 명령
- 서버: `cd webapp/src && uv run ruff check . && uv run ruff format --check . && uv run pytest`
- 화면: `cd webapp/frontend && npm run build`
- 차트: `helm lint helm --set image.tag=test`

## 제출 전 확인
`.kiro/`(specs, steering, hooks)는 Kiro에서 만든 그대로 커밋해야 해요. PR을 열기 전에 새로 생기거나 바뀐 `.kiro/` 파일이 모두 커밋에 들어 있는지 확인해요.
