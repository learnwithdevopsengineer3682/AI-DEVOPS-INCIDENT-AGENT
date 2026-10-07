from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

from dotenv import load_dotenv
from gradient import Gradient
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty
from rich.rule import Rule

from agent.tools import TOOLS, TOOL_DECLARATIONS

load_dotenv()

console = Console()
START_TIME = time.monotonic()

SYSTEM_INSTRUCTION = """
You are a read-only DevOps incident investigation agent for TaskFlow.

Your job is to identify the most likely root cause using only the provided
tools and the evidence returned by them.

Rules:
1. Do not claim you executed anything unless a tool result proves it.
2. Do not request arbitrary shell access.
3. Do not make destructive changes.
4. Before a tool call, when useful, give ONE short user-facing sentence saying
   what you are checking and why. Do not expose hidden chain-of-thought.
5. Use evidence step by step. A running container does not prove an app works.
6. Distinguish between container/process failure, DNS/service discovery,
   runtime configuration, and connection-pool exhaustion.
7. When you have enough evidence, stop calling tools and return:
   ROOT CAUSE
   EVIDENCE
   SAFE FIX
   VERIFY
8. Never request or expose passwords, API keys, or secrets.
9. Keep terminal-facing notes concise so a viewer can follow them live.
""".strip()


def elapsed() -> str:
    total = int(time.monotonic() - START_TIME)
    return f"{total // 60:02d}:{total % 60:02d}"


def print_banner():
    console.print(
        Panel.fit(
            "[bold]AI DEVOPS INCIDENT AGENT[/bold]\n"
            "TaskFlow • Read-only investigation",
            border_style="cyan",
        )
    )


def print_note(text: str):
    clean = " ".join(text.split())
    if clean:
        console.print(f"\n[bold cyan][{elapsed()}] INVESTIGATION[/bold cyan]")
        console.print(clean)


def print_tool(name: str, arguments: dict[str, Any]):
    console.print(f"\n[bold yellow][{elapsed()}] TOOL[/bold yellow]")
    console.print(f"[bold]{name}[/bold]({json.dumps(arguments, ensure_ascii=False)})")


def print_result(result: Any):
    console.print(f"[bold green][{elapsed()}] RESULT[/bold green]")
    console.print(Pretty(result, expand_all=False, max_string=4000))


def print_final(text: str):
    console.print()
    console.print(Rule("FINAL DIAGNOSIS"))
    console.print(text.strip())


def to_openai_tool_declarations() -> list[dict[str, Any]]:
    tools = []
    for declaration in TOOL_DECLARATIONS:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": declaration["name"],
                    "description": declaration["description"],
                    "parameters": declaration["parameters"],
                },
            }
        )

    return tools


def get_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def model_dump(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return dict(obj)


def parse_tool_arguments(arguments: Any) -> dict[str, Any]:
    if not arguments:
        return {}
    if isinstance(arguments, dict):
        return arguments
    return json.loads(arguments)


def run_agent(prompt: str, model: str, max_rounds: int):
    model_access_key = os.getenv("MODEL_ACCESS_KEY")
    if not model_access_key:
        console.print(
            "[bold red]MODEL_ACCESS_KEY is missing.[/bold red]\n"
            "Copy .env.example to .env and add your Gradient model access key."
        )
        sys.exit(2)

    client = Gradient(model_access_key=model_access_key)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {
            "role": "user",
            "content": f"INCIDENT REPORTED BY USER:\n{prompt}",
        }
    ]
    tools = to_openai_tool_declarations()

    print_banner()
    console.print(f"\n[bold]Incident:[/bold] {prompt}")
    console.print(Rule())

    for _ in range(max_rounds):
        try:
            response = client.chat.completions.create(
                messages=messages,
                model=model,
                tools=tools,
                tool_choice="auto",
                max_tokens=900,
            )
        except Exception as exc:
            console.print(
                Panel(
                    f"{type(exc).__name__}: {exc}",
                    title="MODEL/API ERROR",
                    border_style="red",
                )
            )
            console.print(
                "The investigation stopped before a diagnosis. "
                "This can also be useful on camera: the agent itself has "
                "an external model/API dependency."
            )
            raise

        choices = get_value(response, "choices", [])
        message = get_value(choices[0], "message", {}) if choices else {}
        content = get_value(message, "content", "") or ""
        tool_calls = get_value(message, "tool_calls", []) or []

        assistant_message = model_dump(message)
        messages.append(assistant_message)

        if content and tool_calls:
            print_note(content)

        if not tool_calls:
            print_final(content or "No final diagnosis returned.")
            return

        for tool_call in tool_calls:
            function = get_value(tool_call, "function", {})
            name = get_value(function, "name")
            tool_call_id = get_value(tool_call, "id")

            try:
                args = parse_tool_arguments(get_value(function, "arguments", "{}"))
            except json.JSONDecodeError as exc:
                args = {}
                result = {"error": f"Invalid tool arguments JSON: {exc}"}
                print_tool(name or "unknown", args)
                print_result(result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
                continue

            print_tool(name, args)

            try:
                if name not in TOOLS:
                    result = {"error": f"Unknown tool requested: {name}"}
                else:
                    result = TOOLS[name](**args)
            except Exception as exc:
                result = {"error": f"{type(exc).__name__}: {exc}"}

            print_result(result)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    console.print(
        Panel(
            f"Stopped after {max_rounds} investigation rounds.",
            border_style="red",
        )
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="TaskFlow AI DevOps incident agent"
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Incident description. If omitted, you will be prompted.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("GRADIENT_MODEL", "openai-gpt-oss-120b"),
    )
    parser.add_argument("--max-rounds", type=int, default=12)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    prompt = args.prompt
    if not prompt:
        console.print("[bold]Describe the incident:[/bold]")
        prompt = input("> ").strip()

    if not prompt:
        raise SystemExit("Incident description cannot be empty.")

    run_agent(prompt=prompt, model=args.model, max_rounds=args.max_rounds)
