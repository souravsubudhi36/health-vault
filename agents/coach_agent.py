from pathlib import Path
from datetime import datetime, timedelta
import anthropic
from . import memory

_SESSIONS_DIR = Path("vault/Tennis/Sessions")
_GOALS_FILE = Path("vault/Tennis/Goals.md")
_PROGRESS_FILE = Path("vault/Tennis/Progress.md")

_SYSTEM = """You are an elite tennis coach specializing in developing players from amateur to professional level. \
You combine technical tennis expertise with sports science to build personalized development programs. \
You track statistics obsessively, identify patterns across sessions, and give direct, actionable feedback. \
You always reference the player's pro goal when making recommendations."""


def _load_recent_sessions(days: int = 30) -> str:
    today = datetime.today().date()
    sessions = []
    for i in range(days):
        date = (today - timedelta(days=i)).isoformat()
        path = _SESSIONS_DIR / f"{date}.md"
        if path.exists():
            # Truncate long session files to keep context manageable
            sessions.append(f"=== Session {date} ===\n{path.read_text(encoding='utf-8')[:2000]}")
    return "\n\n".join(reversed(sessions)) if sessions else "No sessions recorded yet — player is just starting out."


def run(client: anthropic.Anthropic, today: str, physio_report: str) -> str:
    sessions = _load_recent_sessions(30)
    coach_memory = memory.read("coach")
    goals = _GOALS_FILE.read_text(encoding="utf-8") if _GOALS_FILE.exists() else "Goal: Become a professional tennis player."

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2500,
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"""Today: {today}

## Player Goals
{goals}

## Physiotherapist's Assessment (today)
{physio_report}

## Recent Training Sessions (last 30 days)
{sessions}

## Your Coaching History & Player Development Notes
{coach_memory or "New player — establishing baseline. First session needed."}

---
Provide your daily coaching report:

**TODAY'S TRAINING PLAN:**
[Specific drills, intensity, duration — calibrated to today's physio readiness. \
If physio says Rest Day, prescribe active recovery and mental work only.]

**TECHNICAL FOCUS:**
[1–2 specific technical elements based on recent session data. Be precise: \
"work on low-to-high racquet path on forehand" not "improve forehand".]

**SESSION ANALYSIS** (if sessions exist):
| Shot | Success Rate | Trend | Key Issue |
|------|-------------|-------|-----------|
| Forehand | X% | ↑/↓/→ | ... |
| Backhand | X% | ↑/↓/→ | ... |
| Volley | X% | ↑/↓/→ | ... |
| Serve | X% | ↑/↓/→ | ... |

**PROGRESS TOWARDS PRO GOAL:**
[Honest, specific assessment. Reference milestones from Goals.md. \
What's on track, what's lagging, what's the biggest gap right now.]

**THIS WEEK'S PRIORITY:**
[Single most impactful focus area]

**Memory Note:**
[Key technical or developmental observations to track long-term]""",
        }],
    )

    report = response.content[0].text

    if "Memory Note" in report:
        mem_raw = report.split("Memory Note")[1].split("\n\n")[0]
        memory.append_entry("coach", today, mem_raw.strip(": \n"))

    return report
