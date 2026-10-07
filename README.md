# AI DevOps Incident Agent

**I Gave an AI Agent a Production Incident**

## Learn More

- Watch the video: [I Gave an AI Agent a Production Incident](https://youtu.be/47s2mKKJXsc?si=hpoJR-RrZkiU8L5l)
- Join the cohort, register here: [labs.learnwithdevopsengineer.com](https://labs.learnwithdevopsengineer.com)
- Topmate: [topmate.io/learnwithdevopsengineer](https://topmate.io/learnwithdevopsengineer)

The demo runs a tiny TaskFlow API with PostgreSQL. The AI agent has a fixed set of read-only troubleshooting tools and prints each visible step to the terminal:

- investigation note
- selected tool
- tool arguments
- tool result
- final diagnosis

It deliberately does **not** print private model reasoning.

## Incident 1

Both containers are running and the API health endpoint returns 200, but `/tasks` fails because the API is configured with the wrong database hostname.

## Incident 2

Containers, DNS and health checks all look good, but real requests fail because the application's PostgreSQL connection pool is exhausted.

## Safety

The agent can inspect only the TaskFlow demo environment. It cannot restart/delete containers, modify configuration, or execute arbitrary shell commands.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Put your Gradient model access key in `.env`, then follow `RUNBOOK.md`.
```

The Gradient integration uses OpenAI-style chat completions and tool calling so the terminal can display every tool invocation and result.
