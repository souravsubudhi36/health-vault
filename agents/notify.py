import os
import requests

_API = "https://api.telegram.org"
_LIMIT = 4096


def telegram(text: str, parse_mode: str = "Markdown") -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"{_API}/bot{token}/sendMessage"

    chunks = [text[i : i + _LIMIT] for i in range(0, len(text), _LIMIT)]
    for chunk in chunks:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": chunk, "parse_mode": parse_mode},
            timeout=10,
        )
        resp.raise_for_status()
