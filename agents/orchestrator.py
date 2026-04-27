#!/usr/bin/env python3
"""
Nightly orchestrator — runs physio, coach, and nutrition agents in sequence,
compiles a report, sends via Telegram, and saves the full report to vault.

Usage (from repo root):
    python -m agents.orchestrator
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic

from . import coach_agent, memory, notify, nutrition_agent, physio_agent

_REPORT_DIR = Path("vault/agents/reports")


def _extract_section(text: str, header: str, lines: int = 6) -> str:
    """Pull N lines after a header keyword."""
    text_lines = text.split("\n")
    for i, line in enumerate(text_lines):
        if header.lower() in line.lower():
            snippet = "\n".join(text_lines[i : i + lines + 1]).strip()
            return snippet
    return ""


def _compile_telegram_report(today: str, physio: str, coach: str, nutrition: str) -> str:
    physio_status = _extract_section(physio, "RECOVERY STATUS", 1)
    physio_readiness = _extract_section(physio, "TRAINING READINESS", 1)
    physio_condition = _extract_section(physio, "Physical Condition", 3)

    coach_plan = _extract_section(coach, "TODAY'S TRAINING PLAN", 5)
    coach_focus = _extract_section(coach, "TECHNICAL FOCUS", 3)
    coach_priority = _extract_section(coach, "THIS WEEK'S PRIORITY", 2)

    nutrition_calories = _extract_section(nutrition, "CALORIE TARGET", 1)
    nutrition_macros = _extract_section(nutrition, "MACROS", 4)
    nutrition_hydration = _extract_section(nutrition, "HYDRATION", 2)

    lines = [
        f"*Daily Tennis Report — {today}*",
        "",
        "*PHYSIO*",
        physio_status,
        physio_readiness,
        physio_condition,
        "",
        "*COACH*",
        coach_plan,
        "",
        f"Focus: {coach_focus}",
        f"Week Priority: {coach_priority}",
        "",
        "*NUTRITION*",
        nutrition_calories,
        nutrition_macros,
        nutrition_hydration,
        "",
        f"_Full report: vault/agents/reports/{today}.md_",
    ]
    return "\n".join(line for line in lines if line is not None)


def run(today: str | None = None) -> None:
    today = today or datetime.today().strftime("%Y-%m-%d")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print(f"[{today}] Running physio agent...")
    physio = physio_agent.run(client, today)

    print(f"[{today}] Running coach agent...")
    coach = coach_agent.run(client, today, physio_report=physio)

    print(f"[{today}] Running nutrition agent...")
    nutrition = nutrition_agent.run(client, today, physio_report=physio, coach_report=coach)

    telegram_msg = _compile_telegram_report(today, physio, coach, nutrition)

    print(f"[{today}] Sending Telegram notification...")
    try:
        notify.telegram(telegram_msg)
        print("  Sent.")
    except Exception as exc:
        print(f"  Telegram failed: {exc}", file=sys.stderr)

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    full = "\n\n---\n\n".join([
        f"# Daily Report — {today}",
        f"## Physio\n{physio}",
        f"## Coach\n{coach}",
        f"## Nutrition\n{nutrition}",
    ])
    (_REPORT_DIR / f"{today}.md").write_text(full, encoding="utf-8")
    print(f"[{today}] Full report saved → vault/agents/reports/{today}.md")


if __name__ == "__main__":
    run()
