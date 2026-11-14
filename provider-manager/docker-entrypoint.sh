#!/bin/sh
# Install the optional Codex CLI at start only when CODEX_ENABLED=true (or PROVIDER=codex).
set -eu
case "${CODEX_ENABLED:-}:${PROVIDER:-}" in
  [Tt][Rr][Uu][Ee]:*|1:*|*:codex)
    if ! command -v "${CODEX_BIN:-codex}" >/dev/null 2>&1; then
      echo "CODEX_ENABLED: installing Codex CLI (node + @openai/codex)" >&2
      if ! command -v npm >/dev/null 2>&1; then
        apt-get update -qq && apt-get install -y -qq --no-install-recommends nodejs npm \
          && rm -rf /var/lib/apt/lists/*
      fi
      npm install -g @openai/codex
    fi
    mkdir -p "${CODEX_HOME:-$HOME/.codex}"
    ;;
esac
exec "$@"
