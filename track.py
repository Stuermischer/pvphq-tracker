import datetime
import json
import re
import sys
import time
import urllib.request

# Name in history.json -> mögliche Adressen auf der Seite
LADDERS = {
    "overall": ["overall"],
    "sword": ["sword"],
    "axe": ["axe"],
    "mace": ["mace"],
    "spear_mace": ["spear_mace"],
    "uhc": ["uhc"],
    "netherite_pot": ["netherite_pot"],
    "pot": ["pot"],
    "smp": ["smp"],
    "diamond_smp": ["diamond_smp"],
    "vanilla": ["vanilla"],
    "cart": ["cart"],
}
HOSTS = ["https://pvphq.com", "https://flowpvp.gg"]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; pvphq-tracker/1.0)"}
TRIES = 3  # Versuche pro Modus (die Seite liefert manchmal nur eine leere Standardseite)
WAIT = 6  # Sekunden Pause zwischen den Versuchen (wird jedes Mal länger)
DEADLINE = time.time() + 12 * 60  # nach 12 Minuten nicht mehr wiederholen


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", "replace")


def parse(html):
    m = re.search(r"([\d][\d.,\s]*)\s+players\s+ranked", html, re.I) or re.search(
        r"of\s+([\d][\d.,]*)\s+players", html, re.I
    )
    if not m:
        return None
    n = int(re.sub(r"\D", "", m.group(1)))
    return n if n > 0 else None


def count(name, paths):
    for attempt in range(TRIES):
        for path in paths:
            for host in HOSTS:
                try:
                    # Zeitstempel in der Adresse, damit keine zwischengespeicherte Leerseite kommt
                    html = fetch(f"{host}/leaderboard/{path}?t={int(time.time())}")
                    n = parse(html)
                    if n:
                        return n
                    print(f"{name}: {host} lieferte keine Zahl (Versuch {attempt + 1})", file=sys.stderr)
                except Exception as e:
                    print(f"{name}: {host}: {e}", file=sys.stderr)
        if attempt < TRIES - 1 and time.time() < DEADLINE:
            time.sleep(WAIT * (attempt + 1))
        else:
            break
    return None


now = datetime.datetime.now(datetime.timezone.utc)
# Der Lauf ist für 5 Minuten vor der vollen Stunde geplant (xx:55) und startet bei GitHub oft
# etwas später. Die Messung wird deshalb der nächsten vollen Stunde zugeordnet.
hour = (now + datetime.timedelta(minutes=5)).replace(minute=0, second=0, microsecond=0)
point = {"t": int(hour.timestamp() * 1000)}
missing = []
for ladder, paths in LADDERS.items():
    c = count(ladder, paths)
    if c is not None:
        point[ladder] = c
    else:
        missing.append(ladder)

if len(point) == 1:
    # Seite liefert gerade keine Zahlen (z. B. Wartung oder Ausfall): Lauf überspringen, nichts speichern
    print("Keine Zahlen gefunden, Lauf übersprungen")
    sys.exit(0)

try:
    with open("history.json", encoding="utf-8") as f:
        history = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    history = []

if history and history[-1].get("t") == point["t"]:
    # gleiche volle Stunde (z. B. Lauf von Hand): ergänzen statt doppelt speichern
    history[-1].update(point)
else:
    history.append(point)
history = history[-10000:]

with open("history.json", "w", encoding="utf-8") as f:
    json.dump(history, f, separators=(",", ":"))

print(point)
if missing:
    print("Nicht gefunden:", ", ".join(missing))
