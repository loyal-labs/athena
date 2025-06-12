# Running locally
You can run locally with `uv`:
```
uv run uvicorn app:app --reload
```

Alternatively, use docker compose. You'll need these variables:
```
# 1Password service account
OP_SERVICE_ACCOUNT_TOKEN=
# Postgres credentials
POSTGRES_DB=
POSTGRES_USER=
POSTGRES_PASSWORD=
```

Run docker compose:
```
docker-compose up -d
```