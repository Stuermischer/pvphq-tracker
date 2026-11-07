import datetime
import html as htmllib
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

# Messungen vor dem 04.11.2026, 16:00 Uhr (MEZ) werden entfernt (die Messung um 16:20 bleibt)
CUTOFF = int(datetime.datetime(2026, 11, 4, 15, 0, tzinfo=datetime.timezone.utc).timestamp() * 1000)

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


TOP_RE = re.compile(r"(?:🥇|🥈|🥉|\d\.)\s+(?:([HLMR]T\d)\s+)?([A-Za-z0-9_]{1,16})\s+—\s+(\d+)\s+(?:TR|PTS)")


def parse_top(html):
    """Top 5 aus der Seitenbeschreibung: [[Name, Punkte, Stufe], ...]"""
    m = re.search(r"players\s+ranked", html, re.I)
    if not m:
        return []
    seg = htmllib.unescape(html[m.end():m.end() + 700])
    out = []
    for tier, name, pts in TOP_RE.findall(seg):
        out.append([name, int(pts), tier])
        if len(out) == 5:
            break
    return out


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


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
tops = {}  # Top 5 je Modus
when = {}  # Zeitpunkt, an dem die Zahl des jeweiligen Modus tatsächlich gelesen wurde

for attempt in range(PASSES):
    # abwechselnd pvphq.com und flowpvp.gg, pro Durchgang nur eine Anfrage je Modus
    host = HOSTS[attempt % len(HOSTS)]
    for name in list(todo):
        n = None
        page = ""
        try:
            page = fetch(f"{host}/leaderboard/{LADDERS[name]}?t={int(time.time())}")
            n = parse(page)
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
        tops[name] = parse_top(page)
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
    for k, v in tops.items():
        print(k, "Top 5:", ", ".join(f"{e[0]} {e[1]}" for e in v) or "nicht gefunden")
    if todo:
        print("Nicht gefunden:", ", ".join(todo))
    sys.exit(0)

history.append(point)
history = history[-10000:]

with open("history.json", "w", encoding="utf-8") as f:
    json.dump(history, f, separators=(",", ":"))

# Top 5 je Modus in top.json (aktueller Stand plus Liste der Wechsel an der Spitze und Neueinsteiger)
top = load_json("top.json", {})
if not isinstance(top, dict):
    top = {}
top.setdefault("modes", {})
top.setdefault("log", [])
for name, entries in tops.items():
    if not entries:
        continue
    old = (top["modes"].get(name) or {}).get("top") or []
    tm = int(when[name] * 1000)
    if old:
        if old[0][0] != entries[0][0]:
            top["log"].append({"t": tm, "mode": name, "kind": "leader", "from": old[0][0], "to": entries[0][0]})
        known = {e[0] for e in old}
        for rank, e in enumerate(entries, 1):
            if e[0] not in known and not (rank == 1 and old[0][0] != entries[0][0]):
                top["log"].append({"t": tm, "mode": name, "kind": "enter", "name": e[0], "rank": rank})
    top["modes"][name] = {"t": tm, "top": entries}
top["t"] = point["t"]
top["log"] = top["log"][-300:]
with open("top.json", "w", encoding="utf-8") as f:
    json.dump(top, f, ensure_ascii=False, separators=(",", ":"))

print(point)
if todo:
    print("Nicht gefunden:", ", ".join(todo))
