"""
parse_health.py
---------------
Reads plain-text Apple Health files from health/apple-health/incoming/,
parses them into structured JSON, and writes results to
health/apple-health/parsed/.

Each incoming file has the format:
    DATA_TYPE_HEADER
    ===SECTION===
    value or date lines...

Handles: sleep (session grouping), HRV, resting HR, steps, weight,
active energy, blood oxygen, exercise minutes, and more.
"""

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

INCOMING_DIR = Path("health/apple-health/incoming")
RAW_DIR = Path("health/apple-health/raw")
PARSED_DIR = Path("health/apple-health/parsed")

# ---------------------------------------------------------------------------
# Text parsing helpers
# ---------------------------------------------------------------------------

def parse_sections(raw_text: str) -> dict:
    """Split plain-text into a dict of section_name → [lines]."""
    sections: dict = {}
    current_section = None
    current_lines: list = []

    for line in raw_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("===") and stripped.endswith("===") and len(stripped) > 6:
            if current_section is not None:
                sections[current_section] = current_lines
            current_section = stripped.strip("=").strip()
            current_lines = []
        elif current_section is not None and stripped:
            current_lines.append(stripped)

    if current_section is not None:
        sections[current_section] = current_lines

    return sections


def parse_dt(s: str):
    """Try multiple datetime formats; return datetime or None."""
    formats = [
        "%b %d, %Y at %I:%M %p",
        "%b %d, %Y at %I:%M:%S %p",
        "%b %d, %Y, %I:%M %p",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]
    s = s.strip()
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Generic metric parser (steps, HRV, weight, energy, etc.)
# ---------------------------------------------------------------------------

def parse_generic(sections: dict) -> list:
    records = []
    values = sections.get("VALUE", [])
    starts = sections.get("START_DATE", [])
    ends = sections.get("END_DATE", [])

    for i, raw_val in enumerate(values):
        start = parse_dt(starts[i]) if i < len(starts) else None
        end = parse_dt(ends[i]) if i < len(ends) else None
        if start is None:
            continue
        try:
            val = float(raw_val)
        except (ValueError, TypeError):
            val = raw_val

        records.append({
            "value": val,
            "start": start.isoformat(),
            "end": end.isoformat() if end else None,
            "date": start.date().isoformat(),
        })

    return records


# ---------------------------------------------------------------------------
# Sleep parser – groups segments into sessions
# ---------------------------------------------------------------------------

def parse_sleep(sections: dict) -> list:
    stages = sections.get("VALUE", [])
    starts = sections.get("START_DATE", [])
    ends = sections.get("END_DATE", [])

    segments = []
    for i, stage in enumerate(stages):
        start = parse_dt(starts[i]) if i < len(starts) else None
        end = parse_dt(ends[i]) if i < len(ends) else None
        if start and end:
            segments.append({
                "stage": stage,
                "start": start,
                "end": end,
                "duration_min": round((end - start).total_seconds() / 60, 1),
            })

    if not segments:
        return []

    segments.sort(key=lambda s: s["start"])

    # Group into sessions: gap > 2 h → new session
    sessions = []
    current = [segments[0]]
    for seg in segments[1:]:
        gap = (seg["start"] - current[-1]["end"]).total_seconds()
        if gap > 7200:
            sessions.append(current)
            current = [seg]
        else:
            current.append(seg)
    sessions.append(current)

    results = []
    for session in sessions:
        total_min = sum(s["duration_min"] for s in session)
        by_stage: dict = {}
        for s in session:
            by_stage[s["stage"]] = round(by_stage.get(s["stage"], 0) + s["duration_min"], 1)

        session_start = session[0]["start"]
        session_end = session[-1]["end"]

        # Attribute sleep to the morning date (the date you woke up)
        date = session_end.date().isoformat()

        results.append({
            "date": date,
            "start": session_start.isoformat(),
            "end": session_end.isoformat(),
            "total_min": round(total_min, 1),
            "stages": by_stage,
        })

    return results


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate(records: list, key_field: str = "start") -> list:
    """Keep the last-seen record per key (higher value wins for numeric)."""
    seen: dict = {}
    for r in records:
        k = r.get(key_field) or r.get("date")
        if k is None:
            continue
        existing = seen.get(k)
        if existing is None:
            seen[k] = r
        else:
            # For numeric values keep the higher one (Watch vs iPhone dedup)
            ev = existing.get("value")
            rv = r.get("value")
            if isinstance(ev, (int, float)) and isinstance(rv, (int, float)):
                if rv > ev:
                    seen[k] = r
            else:
                seen[k] = r  # prefer newer

    return sorted(seen.values(), key=lambda x: x.get(key_field) or x.get("date") or "")


# ---------------------------------------------------------------------------
# File-level processing
# ---------------------------------------------------------------------------

def process_file(filepath: Path) -> tuple:
    content = filepath.read_text(encoding="utf-8")
    lines = content.strip().split("\n")
    data_type = lines[0].strip() if lines else "UNKNOWN"
    sections = parse_sections(content)

    if data_type == "SLEEP_DATA":
        records = parse_sleep(sections)
    else:
        records = parse_generic(sections)

    return data_type, records


def load_existing(data_type: str) -> list:
    path = PARSED_DIR / f"{data_type.lower()}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def save_parsed(data_type: str, records: list):
    path = PARSED_DIR / f"{data_type.lower()}.json"
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    files = [f for f in INCOMING_DIR.iterdir() if f.suffix == ".txt"]
    if not files:
        print("No incoming files to process.")
        return

    all_new: dict = {}

    for filepath in sorted(files):
        print(f"  Parsing {filepath.name} …")
        try:
            data_type, records = process_file(filepath)
        except Exception as exc:
            print(f"    ERROR: {exc}")
            continue

        all_new.setdefault(data_type, []).extend(records)

        # Archive a raw copy
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(filepath, RAW_DIR / f"{data_type.lower()}_latest.txt")

        # Remove from incoming
        filepath.unlink()

    for data_type, new_records in all_new.items():
        existing = load_existing(data_type)
        key_field = "start" if any("start" in r for r in new_records) else "date"
        merged = existing + new_records
        final = deduplicate(merged, key_field=key_field)
        save_parsed(data_type, final)
        print(f"  Saved {len(final)} records → {data_type.lower()}.json")


if __name__ == "__main__":
    main()
