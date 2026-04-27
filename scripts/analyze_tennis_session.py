#!/usr/bin/env python3
"""
Tennis session video analyzer.

Extracts frames from a recorded session, sends them to Claude Vision in batches,
identifies every shot (forehand/backhand/volley/serve/overhead), classifies
outcome (in/out/net/winner) and quality, then saves a structured session report
to vault/Tennis/Sessions/YYYY-MM-DD.md and sends a Telegram summary.

Usage (from repo root):
    python scripts/analyze_tennis_session.py path/to/session.mp4
    python scripts/analyze_tennis_session.py path/to/session.mp4 --date 2026-04-27
    python scripts/analyze_tennis_session.py path/to/session.mp4 --fps 0.5 --no-notify
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import anthropic
import requests

_SESSIONS_DIR = Path("vault/Tennis/Sessions")
_MEMORY_DIR = Path("vault/agents/memory")

# Shot types the model should recognise
_SHOT_TYPES = ["forehand", "backhand", "volley", "serve", "overhead", "dropshot", "lob", "return"]
_SUCCESS_OUTCOMES = {"winner", "in", "return_in"}

# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

def extract_frames(video_path: str, fps: float = 1.0) -> list[tuple[str, float]]:
    """Return list of (base64_jpeg, timestamp_seconds) extracted at given FPS."""
    with tempfile.TemporaryDirectory() as tmp:
        pattern = os.path.join(tmp, "frame_%05d.jpg")
        result = subprocess.run(
            ["ffmpeg", "-i", video_path, "-vf", f"fps={fps}", "-q:v", "4", pattern],
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed:\n{result.stderr.decode()}")

        frames = []
        for frame_file in sorted(Path(tmp).glob("frame_*.jpg")):
            idx = int(frame_file.stem.split("_")[1]) - 1
            timestamp = idx / fps
            with open(frame_file, "rb") as f:
                b64 = base64.standard_b64encode(f.read()).decode("utf-8")
            frames.append((b64, timestamp))

    return frames


# ---------------------------------------------------------------------------
# Claude Vision analysis
# ---------------------------------------------------------------------------

_ANALYSIS_PROMPT = """You are an expert tennis coach analysing frames from a training session.

For each frame where a shot is being executed or just completed, identify:
1. shot_type: one of forehand | backhand | volley | serve | overhead | dropshot | lob | return
2. outcome: winner | in | out | net | forced_error | unknown
3. quality: excellent | good | fair | poor  (based on body position, swing mechanics, balance)
4. feedback: one specific coaching tip (e.g. "Keep your elbow higher on the backswing")
5. form_notes: brief notes on stance, swing path, contact point, follow-through

Return a JSON array. Only include frames with a clear shot event. If no shot is visible, return [].

Format:
[
  {
    "timestamp": 3.0,
    "shot_type": "forehand",
    "outcome": "in",
    "quality": "good",
    "feedback": "Good hip rotation — extend the follow-through across your body",
    "form_notes": {
      "stance": "semi-open, balanced",
      "swing": "low-to-high path",
      "contact": "slightly late",
      "follow_through": "cut short"
    }
  }
]"""


def _build_content(batch: list[tuple[str, float]]) -> list:
    content = []
    for b64, ts in batch:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })
        content.append({"type": "text", "text": f"Timestamp: {ts:.1f}s"})
    content.append({"type": "text", "text": _ANALYSIS_PROMPT})
    return content


def _parse_json_response(text: str) -> list:
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return []


def analyse_frames(client: anthropic.Anthropic, frames: list, batch_size: int = 6) -> list:
    all_shots = []
    total_batches = (len(frames) + batch_size - 1) // batch_size

    for i in range(0, len(frames), batch_size):
        batch = frames[i : i + batch_size]
        batch_num = i // batch_size + 1
        start_ts = batch[0][1]
        print(f"  Analysing batch {batch_num}/{total_batches} (t={start_ts:.0f}s–{batch[-1][1]:.0f}s)...")

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": _build_content(batch)}],
        )
        shots = _parse_json_response(response.content[0].text)
        all_shots.extend(shots)

    return all_shots


# ---------------------------------------------------------------------------
# Statistics & report generation
# ---------------------------------------------------------------------------

def compute_stats(shots: list) -> dict:
    stats: dict = {st: {"attempts": 0, "success": 0} for st in _SHOT_TYPES}

    for shot in shots:
        st = shot.get("shot_type", "").lower()
        outcome = shot.get("outcome", "").lower()
        if st in stats:
            stats[st]["attempts"] += 1
            if outcome in _SUCCESS_OUTCOMES:
                stats[st]["success"] += 1

    for st, data in stats.items():
        data["rate"] = (
            round(data["success"] / data["attempts"] * 100) if data["attempts"] > 0 else None
        )

    total_attempts = sum(d["attempts"] for d in stats.values())
    total_success = sum(d["success"] for d in stats.values())
    overall_rate = round(total_success / total_attempts * 100) if total_attempts > 0 else 0

    return {
        "by_shot": stats,
        "total_attempts": total_attempts,
        "total_success": total_success,
        "overall_rate": overall_rate,
    }


def _rate_cell(data: dict) -> str:
    if data["attempts"] == 0:
        return "| — | — | — |"
    rate = f"{data['rate']}%" if data["rate"] is not None else "—"
    return f"| {data['attempts']} | {data['success']} | {rate} |"


def build_session_note(date: str, shots: list, stats: dict, video_path: str) -> str:
    by_shot = stats["by_shot"]

    fm_lines = [
        "---",
        f"date: {date}",
        f"total_shots: {stats['total_attempts']}",
        f"overall_success_rate: {stats['overall_rate']}",
    ]
    for st in ["forehand", "backhand", "volley", "serve"]:
        rate = by_shot[st].get("rate")
        fm_lines.append(f"{st}_rate: {rate if rate is not None else 'null'}")
    fm_lines += ["tags: [tennis, session]", "---", ""]

    body = [
        f"# Tennis Session — {date}",
        "",
        f"> Video: `{video_path}`",
        "",
        "## Shot Statistics",
        "",
        "| Shot Type | Attempts | Successful | Success Rate |",
        "|-----------|----------|------------|--------------|",
    ]

    label_map = {
        "forehand": "Forehand", "backhand": "Backhand", "volley": "Volley",
        "serve": "Serve", "overhead": "Overhead", "dropshot": "Drop Shot",
        "lob": "Lob", "return": "Return",
    }
    for st, label in label_map.items():
        body.append(f"| {label} {_rate_cell(by_shot[st])}")

    body += [
        "",
        f"**Overall Success Rate:** {stats['overall_rate']}%  |  "
        f"**Total Shots:** {stats['total_attempts']}  |  "
        f"**Successful:** {stats['total_success']}",
        "",
        "## Shot-by-Shot Log",
        "",
    ]

    for shot in sorted(shots, key=lambda s: s.get("timestamp", 0)):
        ts = shot.get("timestamp", 0)
        st = shot.get("shot_type", "?").title()
        outcome = shot.get("outcome", "?")
        quality = shot.get("quality", "?")
        feedback = shot.get("feedback", "")
        tick = "✅" if outcome in _SUCCESS_OUTCOMES else "❌"
        body.append(f"- `{ts:.0f}s` **{st}** — {tick} _{outcome}_ | {quality} | {feedback}")

    # Coaching insights: top improvement areas
    poor_shots = [s for s in shots if s.get("quality") in ("poor", "fair")]
    if poor_shots:
        body += ["", "## Key Areas to Improve", ""]
        seen: set = set()
        for s in poor_shots[:6]:
            fb = s.get("feedback", "")
            if fb and fb not in seen:
                body.append(f"- [{s.get('shot_type','').title()} @ {s.get('timestamp',0):.0f}s] {fb}")
                seen.add(fb)

    body += ["", "## Coach Notes", "", "_Filled by coach agent in nightly report._", ""]

    return "\n".join(fm_lines + body)


# ---------------------------------------------------------------------------
# Telegram summary
# ---------------------------------------------------------------------------

def _send_telegram(date: str, stats: dict) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("  Telegram env vars not set — skipping notification.")
        return

    by_shot = stats["by_shot"]

    def row(label: str, key: str) -> str:
        d = by_shot.get(key, {})
        if not d["attempts"]:
            return ""
        return f"  {label}: {d['success']}/{d['attempts']} ({d['rate']}%)"

    lines = [
        f"*Tennis Session — {date}*",
        f"Overall: *{stats['overall_rate']}%* ({stats['total_success']}/{stats['total_attempts']} shots)",
        "",
        row("Forehand", "forehand"),
        row("Backhand", "backhand"),
        row("Volley", "volley"),
        row("Serve", "serve"),
        row("Overhead", "overhead"),
        "",
        "_Full report saved in vault/Tennis/Sessions/_",
    ]
    msg = "\n".join(l for l in lines if l is not None)

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
        timeout=10,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse a tennis session video.")
    parser.add_argument("video", help="Path to the session video (MP4/MOV)")
    parser.add_argument("--date", default=datetime.today().strftime("%Y-%m-%d"))
    parser.add_argument("--fps", type=float, default=1.0, help="Frames per second to extract (default 1.0)")
    parser.add_argument("--batch-size", type=int, default=6, help="Frames per Claude API call")
    parser.add_argument("--no-notify", action="store_true", help="Skip Telegram notification")
    args = parser.parse_args()

    if not Path(args.video).exists():
        print(f"Error: video not found: {args.video}", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print(f"Extracting frames from '{args.video}' at {args.fps} FPS...")
    frames = extract_frames(args.video, fps=args.fps)
    print(f"  {len(frames)} frames extracted.")

    print("Sending frames to Claude Vision for shot analysis...")
    shots = analyse_frames(client, frames, batch_size=args.batch_size)
    print(f"  {len(shots)} shot events detected.")

    stats = compute_stats(shots)
    print(f"  Overall success rate: {stats['overall_rate']}% ({stats['total_success']}/{stats['total_attempts']})")

    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    note = build_session_note(args.date, shots, stats, args.video)
    note_path = _SESSIONS_DIR / f"{args.date}.md"
    note_path.write_text(note, encoding="utf-8")
    print(f"Session report → {note_path}")

    json_path = _SESSIONS_DIR / f"{args.date}.json"
    json_path.write_text(json.dumps({"date": args.date, "shots": shots, "stats": stats}, indent=2), encoding="utf-8")
    print(f"Raw JSON      → {json_path}")

    if not args.no_notify:
        print("Sending Telegram notification...")
        try:
            _send_telegram(args.date, stats)
            print("  Sent.")
        except Exception as exc:
            print(f"  Telegram failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
