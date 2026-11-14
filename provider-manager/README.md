# provider-manager

Credentials and inference config for generative AI providers: AWS Bedrock (API key), OpenAI (API key), OpenAI Codex (subscription).

## Set keys

```bash
cp .env.example .env   # .env is gitignored; every variable is listed there
```

- `PROVIDER`: `openai` (default), `bedrock` or `codex`
- openai: `OPENAI_API_KEY`, optional `OPENAI_MODEL`
- bedrock: `AWS_BEARER_TOKEN_BEDROCK`, `AWS_REGION`, optional `BEDROCK_MODEL_ID`
- codex (optional, off by default): `CODEX_ENABLED=true` (or `PROVIDER=codex`), then sign in. Optional `CODEX_HOME`, `CODEX_AUTH_FILE`, `CODEX_BIN`, `CODEX_MODEL`, `CODEX_TIMEOUT`. When off, nothing Codex is installed or needed, and `status` shows `codex disabled`.

## How it works

`factory.build_model(name)` returns a [Strands Agents](https://strandsagents.com) model
(`OpenAIModel`, `BedrockModel` or `CodexModel`). `factory.ask` runs `Agent(model=...)` for all of
them, so only the model differs. `CodexModel` is a custom Strands model that runs
`codex exec` with your `codex login` sign-in. It is text only (no tools, no streaming).
Using a ChatGPT subscription through the Codex CLI follows OpenAI's terms for that plan; check
them before automated or shared use.

## Run

```bash
cd src
uv run python -m provider_manager status
uv run python -m provider_manager ask "hello"
PROVIDER=bedrock uv run python -m provider_manager ask "hello"
uv run python -m provider_manager ask --provider codex "hello"
```

## Check

```bash
cd src
uv run ruff check --fix . && uv run ruff format . && uv run ty check . && uv run pytest
```

## Codex (optional)

Local: install the CLI yourself (`npm i -g @openai/codex`), set `CODEX_ENABLED=true`, run `codex login`.
If `PROVIDER=codex` but Codex is off or not installed, `ask` stops with a message that says what to do.

### Container

```bash
docker build -t provider-manager .                       # no Codex inside
docker build --build-arg INSTALL_CODEX=true -t provider-manager .   # Codex baked in
docker run --rm --env-file .env -e CODEX_ENABLED=true \
  -v codex-home:/codex-home provider-manager
```

Without the build arg, the entrypoint installs node and Codex at start, only if `CODEX_ENABLED=true`
(or `PROVIDER=codex`) and `codex` is missing. `CODEX_HOME=/codex-home` is a volume, so the login
survives restarts. `.env` and `~/.codex` are never copied into the image (`.dockerignore`).

### Log in inside the container

```bash
docker run --rm -it -e CODEX_ENABLED=true -v codex-home:/codex-home provider-manager codex login --device-auth
```

It prints a link and a one-time code. Open the link in any browser, type the code, approve. The
token is saved in the `codex-home` volume.

- Verified here: local `codex-cli 0.166.0` lists `--device-auth` in `codex login --help`, plus `--with-api-key` and `--with-access-token`.
- From docs only (not run): the flow above, per [simplified.guide](https://www.simplified.guide/codex/device-auth-login) and [laozhang.ai](https://blog.laozhang.ai/en/posts/codex-headless-login). One source says device-code login may need to be enabled in your ChatGPT settings or workspace first.
- Minimum version: not verified. 0.166.0 works; older ones were not tested.
- Fallbacks: mount a pre-made `auth.json` volume (treat it as a secret, read-only), or `printenv OPENAI_API_KEY | codex login --with-api-key`.
- Docker build and run were not tested.
