from __future__ import annotations

import re
from typing import Any

import docker
import requests

docker_client = docker.from_env()

ALLOWED_CONTAINERS = {"taskflow-api", "taskflow-db"}
CONTAINER_ALIASES = {
    "taskflow_api": "taskflow-api",
    "taskflow_db": "taskflow-db",
}
ALLOWED_ENV_KEYS = {"DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_POOL_MAX"}


def _require_container(name: str):
    name = CONTAINER_ALIASES.get(name, name)
    if name not in ALLOWED_CONTAINERS:
        raise ValueError(
            f"Container '{name}' is not allowed. "
            f"Allowed: {sorted(ALLOWED_CONTAINERS)}"
        )
    return docker_client.containers.get(name)


def list_containers() -> dict[str, Any]:
    """List TaskFlow containers with runtime and health status."""
    rows = []

    for name in sorted(ALLOWED_CONTAINERS):
        try:
            container = docker_client.containers.get(name)
            container.reload()
            health = (
                container.attrs.get("State", {})
                .get("Health", {})
                .get("Status", "not-configured")
            )
            rows.append(
                {"name": name, "status": container.status, "health": health}
            )
        except docker.errors.NotFound:
            rows.append(
                {"name": name, "status": "not-found", "health": "unknown"}
            )

    return {"containers": rows}


def check_endpoint(path: str = "/tasks") -> dict[str, Any]:
    """Call a TaskFlow endpoint through localhost."""
    if not path.startswith("/"):
        raise ValueError("path must start with '/'")

    url = f"http://localhost:8000{path}"

    try:
        response = requests.get(url, timeout=5)
        body = response.text
        if len(body) > 800:
            body = body[:800] + "...[truncated]"

        return {
            "url": url,
            "status_code": response.status_code,
            "body": body,
        }
    except Exception as exc:
        return {"url": url, "error": f"{type(exc).__name__}: {exc}"}


def get_logs(container_name: str, lines: int = 40) -> dict[str, Any]:
    """Read recent logs from a TaskFlow container."""
    container = _require_container(container_name)
    safe_lines = max(5, min(int(lines), 80))

    text = container.logs(tail=safe_lines).decode("utf-8", errors="replace")
    if len(text) > 4000:
        text = text[-4000:]

    return {
        "container": container_name,
        "lines_requested": safe_lines,
        "logs": text,
    }


def inspect_container(container_name: str) -> dict[str, Any]:
    """Inspect status, health, and attached Docker networks."""
    container = _require_container(container_name)
    container.reload()

    state = container.attrs.get("State", {})
    networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})

    return {
        "name": container_name,
        "status": state.get("Status"),
        "running": state.get("Running"),
        "health": state.get("Health", {}).get("Status", "not-configured"),
        "networks": sorted(networks.keys()),
    }


def get_runtime_config(container_name: str = "taskflow-api") -> dict[str, Any]:
    """Read only safe non-secret runtime settings."""
    container = _require_container(container_name)
    container.reload()

    result = {}
    for entry in container.attrs.get("Config", {}).get("Env", []):
        if "=" not in entry:
            continue
        key, value = entry.split("=", 1)
        if key in ALLOWED_ENV_KEYS:
            result[key] = value

    return {
        "container": container_name,
        "environment": result,
        "note": "Sensitive values such as DB_PASSWORD are intentionally hidden.",
    }


def test_dns(container_name: str, hostname: str) -> dict[str, Any]:
    """Resolve a hostname from inside a TaskFlow container."""
    container = _require_container(container_name)

    if not re.fullmatch(r"[A-Za-z0-9._-]{1,253}", hostname):
        raise ValueError("hostname contains unsupported characters")

    script = (
        "import socket; "
        f"h={hostname!r}; "
        "print(socket.gethostbyname(h))"
    )

    result = container.exec_run(["python", "-c", script])

    return {
        "container": container_name,
        "hostname": hostname,
        "success": result.exit_code == 0,
        "exit_code": result.exit_code,
        "output": result.output.decode("utf-8", errors="replace").strip(),
    }


def get_network_services() -> dict[str, Any]:
    """Show TaskFlow container names on the Docker network."""
    network = docker_client.networks.get("taskflow-net")
    network.reload()

    services = []
    for _, details in network.attrs.get("Containers", {}).items():
        name = details.get("Name")
        if name not in ALLOWED_CONTAINERS:
            continue
        services.append(
            {
                "container": name,
                "ipv4": details.get("IPv4Address", "").split("/")[0],
                "known_name": name,
            }
        )

    return {"network": "taskflow-net", "services": services}


def get_pool_stats() -> dict[str, Any]:
    """Read application database connection-pool statistics."""
    try:
        response = requests.get("http://localhost:8000/debug/pool", timeout=5)
        return {
            "status_code": response.status_code,
            "pool": response.json(),
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


TOOLS = {
    "list_containers": list_containers,
    "check_endpoint": check_endpoint,
    "get_logs": get_logs,
    "inspect_container": inspect_container,
    "get_runtime_config": get_runtime_config,
    "test_dns": test_dns,
    "get_network_services": get_network_services,
    "get_pool_stats": get_pool_stats,
}

TOOL_DECLARATIONS = [
    {
        "type": "function",
        "name": "list_containers",
        "description": "List TaskFlow API and DB containers with status and health.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "check_endpoint",
        "description": "Call a TaskFlow API endpoint such as /health or /tasks.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path beginning with '/', for example /tasks",
                }
            },
        },
    },
    {
        "type": "function",
        "name": "get_logs",
        "description": "Read recent logs from taskflow-api or taskflow-db.",
        "parameters": {
            "type": "object",
            "properties": {
                "container_name": {
                    "type": "string",
                    "enum": ["taskflow-api", "taskflow-db"],
                },
                "lines": {"type": "integer"},
            },
            "required": ["container_name"],
        },
    },
    {
        "type": "function",
        "name": "inspect_container",
        "description": "Inspect one TaskFlow container's status, health, and networks.",
        "parameters": {
            "type": "object",
            "properties": {
                "container_name": {
                    "type": "string",
                    "enum": ["taskflow-api", "taskflow-db"],
                }
            },
            "required": ["container_name"],
        },
    },
    {
        "type": "function",
        "name": "get_runtime_config",
        "description": "Read safe non-secret TaskFlow DB runtime configuration.",
        "parameters": {
            "type": "object",
            "properties": {
                "container_name": {
                    "type": "string",
                    "enum": ["taskflow-api"],
                }
            },
        },
    },
    {
        "type": "function",
        "name": "test_dns",
        "description": "Test hostname resolution from inside a TaskFlow container.",
        "parameters": {
            "type": "object",
            "properties": {
                "container_name": {
                    "type": "string",
                    "enum": ["taskflow-api", "taskflow-db"],
                },
                "hostname": {"type": "string"},
            },
            "required": ["container_name", "hostname"],
        },
    },
    {
        "type": "function",
        "name": "get_network_services",
        "description": "List TaskFlow service/container names on taskflow-net.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "get_pool_stats",
        "description": (
            "Read TaskFlow DB connection-pool stats. Useful when health checks "
            "pass but real requests still fail."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
]
