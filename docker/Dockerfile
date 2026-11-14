# syntax=docker/dockerfile:1
# 빌드 맥락은 저장소 루트다: docker build -f docker/Dockerfile .
# Vue 화면을 빌드하고(node), Python 서버에 얹어서(FastAPI) 이미지 하나로 낸다.
ARG NODE_VERSION=22
ARG PYTHON_VERSION=3.13

# --- 1) 화면 빌드 ---------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS frontend
WORKDIR /build
# vite.config.ts가 ../../design-system 의 토큰을 가져오므로 같은 상대 위치에 둔다.
COPY design-system ./design-system
WORKDIR /build/webapp/frontend
COPY webapp/frontend/package.json webapp/frontend/package-lock.json ./
RUN npm ci
COPY webapp/frontend/ ./
RUN npm run build

# --- 2) 서버 의존성 -------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS backend
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
# webapp은 ../../provider-manager/src 를 경로 의존성으로 쓰므로 같은 상대 위치를 지킨다.
WORKDIR /app
COPY provider-manager/src ./provider-manager/src
WORKDIR /app/webapp/src
COPY webapp/src/pyproject.toml webapp/src/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY webapp/src/open_attendee ./open_attendee
RUN uv sync --frozen --no-dev

# --- 3) 실행 이미지 -------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime
# 비루트로 실행한다. /data에 SQLite와 업로드 파일이 쌓인다(볼륨으로 붙인다).
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
 && mkdir /data && chown app:app /data
COPY --from=backend /app /app
COPY --from=frontend /build/webapp/frontend/dist /app/webapp/frontend/dist
WORKDIR /app/webapp/src
ENV PATH="/app/webapp/src/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIST=/app/webapp/frontend/dist \
    DATA_DIR=/data
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).status == 200 else 1)"]
CMD ["uvicorn", "open_attendee.main:app", "--host", "0.0.0.0", "--port", "8080"]
