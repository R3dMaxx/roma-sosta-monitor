import os
import re
import json
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

STATE_FILE = "state.json"

SOURCES = {
    "Roma Mobilità": [
        "https://romamobilita.it/it/servizi/sosta",
        "https://romamobilita.it/it"
    ],
    "Roma Capitale": [
        "https://www.comune.roma.it/web/it/home.page"
    ],
}

KW_MAIN = ["ibrid", "hybrid", "mild", "mhev"]
KW_PARK = ["strisce blu", "sosta", "parchegg", "tariff", "gratuit", "esenz", "agevol"]

def telegram_send(message: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    r.raise_for_status()

def now_rome() -> datetime:
    return datetime.now(ZoneInfo("Europe/Rome"))

def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def fetch_text(url: str) -> str:
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def is_relevant(text: str) -> bool:
    return any(k in text for k in KW_MAIN) and any(k in text for k in KW_PARK)

def main():
    # Esegui SOLO alle 07:30 ora di Roma (evita doppio run per ora legale/solare)
    t = now_rome()
    if not (t.hour == 7 and t.minute == 30):
        return

    state = load_state()
    updates = []

    for source, urls in SOURCES.items():
        for url in urls:
            try:
                text = fetch_text(url)
            except Exception:
                continue

            if not is_relevant(text):
                continue

            h = sha(text)
            key = f"{source}::{url}"
            prev = state.get(key)

            # Notifica solo se è cambiato rispetto all’ultima esecuzione “utile”
            if prev and prev != h:
                updates.append((source, url))

            state[key] = h

    save_state(state)

    if updates:
        msg = (
            "<b>Possibile novità – Strisce blu (ibridi, focus mild hybrid)</b>\n"
            f"<b>Rilevazione:</b> {t.strftime('%Y-%m-%d %H:%M')} (Europe/Rome)\n\n"
        )
        for source, url in updates[:6]:
            msg += f"<b>Fonte:</b> {source}\n<b>Link:</b> {url}\n\n"

        msg += "Apri i link per verificare testo ufficiale, data pubblicazione e decorrenza (se indicate)."
        telegram_send(msg)

if __name__ == "__main__":
    main()
