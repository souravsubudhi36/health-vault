from pathlib import Path

MEMORY_DIR = Path("vault/agents/memory")


def read(agent: str) -> str:
    path = MEMORY_DIR / f"{agent}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write(agent: str, content: str) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    (MEMORY_DIR / f"{agent}.md").write_text(content, encoding="utf-8")


def append_entry(agent: str, date: str, entry: str) -> None:
    current = read(agent)
    new_section = f"\n\n### {date}\n{entry.strip()}"
    write(agent, current + new_section)
