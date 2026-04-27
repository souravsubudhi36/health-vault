from pathlib import Path
import anthropic
from . import memory

_VAULT_HEALTH = Path("vault/Health")

_SYSTEM = """You are a sports nutritionist specializing in tennis performance and athlete development. \
You design nutrition plans that optimize energy for training, accelerate recovery, and support long-term \
athletic adaptation. You are precise with numbers and always explain the why behind each recommendation."""


def _parse_frontmatter(date: str) -> dict:
    path = _VAULT_HEALTH / f"{date}.md"
    if not path.exists():
        return {}
    metrics = {}
    in_frontmatter = False
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip() == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter and ":" in line:
            key, _, val = line.partition(":")
            val = val.strip()
            try:
                metrics[key.strip()] = float(val) if val not in ("null", "", "—") else None
            except ValueError:
                metrics[key.strip()] = val
    return metrics


def run(client: anthropic.Anthropic, today: str, physio_report: str, coach_report: str) -> str:
    m = _parse_frontmatter(today)
    prior_memory = memory.read("nutrition")

    weight = m.get("weight", "unknown")
    active_kcal = m.get("active_energy", "unknown")
    resting_kcal = m.get("resting_energy", "unknown")
    exercise_min = m.get("exercise_min", "unknown")
    steps = m.get("steps", "unknown")

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1500,
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"""Today: {today}

## Today's Biometrics
- Weight: {weight} kg
- Active Energy Burned: {active_kcal} kcal
- Resting Metabolic Rate: {resting_kcal} kcal
- Exercise Duration: {exercise_min} min
- Steps: {steps}

## Physio Report
{physio_report}

## Coach's Training Plan Today
{coach_report}

## Your Previous Nutrition Notes
{prior_memory or "New athlete — establishing baseline nutrition plan."}

---
Provide today's nutrition plan:

**CALORIE TARGET:** [X kcal] — [brief rationale based on activity and recovery needs]

**MACROS:**
- Protein: [X g] ([X g/kg body weight]) — key sources: [...]
- Carbohydrates: [X g] — timing: [pre/post training specifics]
- Fats: [X g] — key sources: [...]

**MEAL TIMING:**
- Pre-training ([X hrs before]): [what to eat]
- During training (if >90 min): [what to consume]
- Post-training (within 30 min): [recovery meal]
- Evening: [wind-down nutrition]

**HYDRATION:**
- Total fluid target: [X L]
- Electrolyte needs: [specific recommendation based on training load]

**TOP 5 FOODS TODAY:**
[Specific foods with reasons tied to today's training/recovery demands]

**AVOID:**
[Any specific foods/habits to skip based on current physical state or training type]

**Memory Note:**
[Patterns or adjustments worth tracking long-term, e.g. weight trends, energy correlation with diet]""",
        }],
    )

    report = response.content[0].text

    if "Memory Note" in report:
        mem_raw = report.split("Memory Note")[1].split("\n\n")[0]
        memory.append_entry("nutrition", today, mem_raw.strip(": \n"))

    return report
