# provider-manager

Credentials and inference config for generative AI providers: AWS Bedrock (API key), OpenAI (API key), OpenAI Codex (subscription).

## Set keys

```bash
cp .env.example .env   # .env is gitignored
```

- Bedrock: `AWS_BEARER_TOKEN_BEDROCK` and `AWS_REGION` (needs boto3 >= 1.39)
- OpenAI: `OPENAI_API_KEY`
- Codex: run `codex login`; `CODEX_AUTH_FILE` overrides the token path. Status only, no inference yet.

## Run

```bash
cd src
uv run python -m provider_manager status
uv run python -m provider_manager ask "hello"
```

## Check

```bash
cd src
uv run ruff check --fix . && uv run ruff format . && uv run ty check . && uv run pytest
```
