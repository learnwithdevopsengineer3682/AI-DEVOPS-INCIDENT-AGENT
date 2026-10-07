## One-time setup

### Linux / macOS / WSL

```bash
cd ai-devops-incident-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```env
MODEL_ACCESS_KEY=YOUR_REAL_KEY
GRADIENT_MODEL=openai-gpt-oss-120b
```

---

# Incident 1 — Wrong database hostname

## Reset

Linux / WSL:

```bash
docker compose down -v --remove-orphans
cp scenarios/incident1.env .env.compose
```

## Start the broken application

```bash
docker compose --env-file .env.compose up -d --build
docker compose ps
```

## Show the misleading health check

```bash
curl -i http://localhost:8000/health
```

Expected: HTTP 200.

## Show the real failure

```bash
curl -i http://localhost:8000/tasks
```

Expected: HTTP 500.

## Start the AI agent

```bash
python -m agent.agent
```

Type:

```text
Users cannot load tasks. Investigate the application and identify the root cause.
```

Or:

```bash
python -m agent.agent --prompt "Users cannot load tasks. Investigate the application and identify the root cause."
```

Do not manually troubleshoot while it is running. Let the terminal trace tell the story.

## Apply the human-approved fix

Linux / WSL:

```bash
cp scenarios/healthy.env .env.compose
docker compose --env-file .env.compose up -d --force-recreate taskflow-api
```

## Verify recovery

```bash
curl -i http://localhost:8000/tasks
```

Expected: HTTP 200.

Optional AI verification:

```bash
python -m agent.agent --prompt "The configuration was corrected. Verify whether TaskFlow has recovered."
```

---

# Incident 2 — Connection-pool exhaustion

## Start healthy

Linux / WSL:

```bash
docker compose down -v --remove-orphans
cp scenarios/healthy.env .env.compose
docker compose --env-file .env.compose up -d --build
```

Confirm:

```bash
curl -i http://localhost:8000/health
curl -i http://localhost:8000/tasks
```

Both should work.

## Trigger the harder incident

Linux / WSL:

```bash
./scripts/incident2_start.sh
```

This intentionally holds all three application DB-pool connections.

## Show the symptom

```bash
docker compose ps
curl -i http://localhost:8000/health
curl -i http://localhost:8000/tasks
```

The first two look healthy. `/tasks` should return HTTP 503.

For more mystery in the video, crop/hide the response body and show only the failing status.

## Let AI investigate

```bash
python -m agent.agent
```

Type:

```text
Users are reporting failures when loading tasks. Basic health checks appear normal. Investigate and identify the root cause.
```

## Release the held connections

Linux / WSL:

```bash
./scripts/incident2_release.sh
```

Verify:

```bash
curl -i http://localhost:8000/tasks
```

---

# Cleanup

```bash
docker compose down -v --remove-orphans
```

# Useful commands while recording

```bash
docker logs -f taskflow-api
docker logs -f taskflow-db
docker network inspect taskflow-net
```

Show only DB host manually:

```bash
docker exec taskflow-api env | grep '^DB_HOST='
```
