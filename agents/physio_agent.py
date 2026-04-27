from pathlib import Path
from datetime import datetime, timedelta
import anthropic
from . import memory

_VAULT_HEALTH = Path("vault/Health")

_SYSTEM = """You are an elite sports physiotherapist working exclusively with a tennis player \
on their journey to become a professional. You have deep expertise in athlete recovery, \
injury prevention, and physical performance optimization for tennis. \
You are rigorous, data-driven, and genuinely invested in this player's long-term health."""


def _load_health_notes(days: int = 14) -> str:
    today = datetime.today().date()
    notes = []
    for i in range(days):
        date = (today - timedelta(days=i)).isoformat()
        path = _VAULT_HEALTH / f"{date}.md"
        if path.exists():
            notes.append(f"=== {date} ===\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(reversed(notes)) if notes else "No health data available yet."


def run(client: anthropic.Anthropic, today: str) -> str:
    health_data = _load_health_notes(14)
    prior_memory = memory.read("physio")

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2000,
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"""Today: {today}

## Health Data — Last 14 Days
{health_data}

## Your Previous Observations
{prior_memory or "First assessment — no prior notes."}

---
Provide your daily physiotherapy assessment:

**RECOVERY STATUS:** [1–10] — [one-line reasoning]
**TRAINING READINESS:** [Full Training / Modified Training / Rest Day]

**Physical Condition:**
[2–3 sentences on overall state. Flag: HRV drop >15% week-over-week, \
sleep <6h for 3+ consecutive days, resting HR elevated >5 bpm above 7-day avg, \
steps <3000 for 2+ consecutive days]

**Key Metrics Today:**
- HRV: [value] ms vs 7-day avg [avg] ms
- Sleep: [hours] h — [trend: improving/stable/declining]
- Resting HR: [value] bpm — [trend]
- Activity: [steps] steps, [exercise_min] min exercise

**Recommendations:**
[3–5 specific bullet points — warm-up focus, injury prevention, recovery protocols]

**Memory Note:**
[1–2 bullet points of observations worth tracking long-term, e.g. baseline shifts or recurring patterns]""",
        }],
    )

    report = response.content[0].text

    if "Memory Note" in report:
        mem_raw = report.split("Memory Note")[1].split("\n\n")[0]
        memory.append_entry("physio", today, mem_raw.strip(": \n"))

    return report
