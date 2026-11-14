FROM python:3.13-slim

# Optional: bake the Codex CLI in at build time (docker build --build-arg INSTALL_CODEX=true).
# Without it, the entrypoint installs Codex at start, only if CODEX_ENABLED=true.
ARG INSTALL_CODEX=false

ENV UV_LINK_MODE=copy CODEX_HOME=/codex-home
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN if [ "$INSTALL_CODEX" = "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends nodejs npm \
      && npm install -g @openai/codex \
      && rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /app
COPY src/pyproject.toml src/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/provider_manager ./provider_manager
ENV PATH="/app/.venv/bin:$PATH"

# Login lives here. Mount a volume; never copy ~/.codex or .env into the image.
VOLUME /codex-home
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "provider_manager", "status"]
