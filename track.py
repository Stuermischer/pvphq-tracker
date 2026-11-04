import datetime
import json
import os
import re
import sys
import time
import urllib.request

# Name in history.json -> Adresse auf der Seite
LADDERS = {
    "overall": "overall",
    "sword": "sword",
    "axe": "axe",
    "mace": "mace",
    "spear_mace": "spear_mace",
    "uhc": "uhc",
    "netherite_pot": "netherite_pot",
    "pot": "pot",
    "smp": "smp",
    "diamond_smp": "diamond_smp",
    "vanilla": "vanilla",
    "cart": "cart",
}
HOSTS = ["https://pvphq.com", "https://flowpvp.gg"]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; pvphq-tracker/1.0)"}

PASSES = 4  # Durchgänge: Fehlende Modi werden nach einer Pause erneut abgefragt
PAUSE = 30  # Sekunden Pause vor dem nächsten Durchgang (wird jedes Mal länger)
DELAY = 2  # Sekunden Abstand zwischen zwei Anfragen, damit kein Rate Limit ausgelöst wird
MAX_JUMP = 0.25  # Zahlen, die mehr als 25 % vom letzten Wert abweichen, gelten als fehlerhaft geladen
DEADLINE = time.time() + 14 * 60  # danach keine weiteren Durchgänge

# Messungen vor dem 03.11.2026, 00:00 Uhr (MEZ) werden entfernt
CUTOFF = int(datetime.datetime(2026, 11, 2, 23, 0, tzinfo=datetime.timezone.utc).timestamp() * 1000)

# Von Hand gestartete Läufe sind nur ein Test: Sie zeigen die Zahlen, speichern aber nichts.
DRY = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"


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


def last_value(history, name):
    for p in reversed(history):
        if isinstance(p.get(name), int):
            return p[name]
    return None


try:
    with open("history.json", encoding="utf-8") as f:
        history = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    history = []
history = [p for p in history if p.get("t", 0) >= CUTOFF]

start = time.time()  # Start des Laufs
todo = list(LADDERS)
found = {}
when = {}  # Zeitpunkt, an dem die Zahl des jeweiligen Modus tatsächlich gelesen wurde

for attempt in range(PASSES):
    # abwechselnd pvphq.com und flowpvp.gg, pro Durchgang nur eine Anfrage je Modus
    host = HOSTS[attempt % len(HOSTS)]
    for name in list(todo):
        n = None
        try:
            n = parse(fetch(f"{host}/leaderboard/{LADDERS[name]}?t={int(time.time())}"))
            if n is None:
                print(f"{name}: {host} lieferte keine Zahl (Durchgang {attempt + 1})", file=sys.stderr)
        except Exception as e:
            print(f"{name}: {host}: {e}", file=sys.stderr)
        time.sleep(DELAY)
        if n is None:
            continue
        last = last_value(history, name)
        if last and abs(n - last) / last > MAX_JUMP:
            print(f"{name}: {n} weicht stark von {last} ab, verworfen", file=sys.stderr)
            continue
        found[name] = n
        when[name] = time.time()
        todo.remove(name)
    if not todo or time.time() > DEADLINE or attempt == PASSES - 1:
        break
    time.sleep(PAUSE * (attempt + 1))

if not found:
    # Seite liefert gerade keine Zahlen (z. B. Wartung oder Ausfall): Lauf überspringen
    print("Keine Zahlen gefunden, Lauf übersprungen")
    sys.exit(0)

# t = Start des Laufs. Weil die Modi nacheinander (und bei Fehlern erst später) gelesen werden,
# steht in "o" für jeden Modus, wie viele Sekunden nach dem Start er wirklich gemessen wurde.
point = {"t": int(start * 1000)}
point.update(found)
offsets = {k: round(when[k] - start) for k in found if round(when[k] - start) > 0}
if offsets:
    point["o"] = offsets

if DRY:
    print("Testlauf (von Hand gestartet), es wird nichts gespeichert:")
    print(point)
    if todo:
        print("Nicht gefunden:", ", ".join(todo))
    sys.exit(0)

history.append(point)
history = history[-10000:]

with open("history.json", "w", encoding="utf-8") as f:
    json.dump(history, f, separators=(",", ":"))

print(point)
if todo:
    print("Nicht gefunden:", ", ".join(todo))
