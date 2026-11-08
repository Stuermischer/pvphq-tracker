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
MAX_JUMP = 0.25  # einzelne Zahlen, die mehr als 25 % vom letzten Wert abweichen, gelten als fehlerhaft geladen
RESET_MIN = 9  # fallen so viele Modi gleichzeitig stark ab, ist es ein Reset der Seite, kein Ladefehler
DEADLINE = time.time() + 14 * 60  # danach keine weiteren Durchgänge

MEZ = datetime.timezone(datetime.timedelta(hours=1))


def ms(*args):
    return int(datetime.datetime(*args, tzinfo=MEZ).timestamp() * 1000)


# --- Einmaliger Neustart nach dem Reset von PvPHQ (8.11.2026) ---------------------------------
# Der bisherige Verlauf wird in history_archive_<RESET_ID>.json gesichert, danach beginnt der
# Verlauf neu mit der Messung von Hand unten. Ändert man RESET_ID, passiert das erneut.
RESET_ID = "2026-11-08"
SEED = {
    "t": ms(2026, 11, 8, 0, 0),  # 8.11.2026, 00:00 Uhr
    "overall": 5322, "sword": 2891, "axe": 257, "mace": 322, "spear_mace": 771, "uhc": 586,
    "netherite_pot": 84, "pot": 221, "smp": 158, "diamond_smp": 1357, "vanilla": 457, "cart": 417,
}
OLD_SEED_T = ms(2026, 11, 8, 0, 30)  # frühere Uhrzeit der Startmessung (wird auf SEED["t"] korrigiert)

# Von Hand gestartete Läufe sind nur ein Test: Sie zeigen die Zahlen, speichern aber keine Messung.
DRY = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"

TOP_RE = re.compile(
    r"(?:🥇|🥈|🥉|\d\.)\s*(?:([A-Z]{1,3}\d)\s+)?([A-Za-z0-9_]{1,16})\s*[—–-]\s*(\d+)\s*(?:TR|PTS)"
)


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


def after_ranked(html, length):
    m = re.search(r"players\s+ranked", html, re.I)
    return htmllib.unescape(html[m.end():m.end() + length]) if m else ""


def parse_top(html):
    """Top 5 aus der Seitenbeschreibung: [[Name, Punkte, Stufe], ...]"""
    out = []
    for tier, name, pts in TOP_RE.findall(after_ranked(html, 900)):
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


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def last_value(history, name):
    for p in reversed(history):
        if isinstance(p.get(name), int):
            return p[name]
    return None


def archive(history, label):
    """Sichert den bisherigen Verlauf in einer eigenen Datei, bevor er ersetzt wird."""
    if not any("t" in p for p in history):
        return
    path = f"history_archive_{label}.json"
    n = 2
    while os.path.exists(path):
        path = f"history_archive_{label}_{n}.json"
        n += 1
    save_json(path, history)
    print(f"Alter Verlauf gesichert in {path}")


def update_top():
    """Top 5 je Modus in top.json. Unabhängig davon, ob die Zahl des Modus angenommen wurde."""
    top = load_json("top.json", {})
    if not isinstance(top, dict):
        top = {}
    top.setdefault("modes", {})
    top.setdefault("log", [])
    for name, entries in tops.items():
        old = (top["modes"].get(name) or {}).get("top") or []
        tm = int(top_when[name] * 1000)
        if old and not is_reset:
            if old[0][0] != entries[0][0]:
                top["log"].append({"t": tm, "mode": name, "kind": "leader", "from": old[0][0], "to": entries[0][0]})
            known = {e[0] for e in old}
            for rank, e in enumerate(entries, 1):
                if e[0] not in known and not (rank == 1 and old[0][0] != entries[0][0]):
                    top["log"].append({"t": tm, "mode": name, "kind": "enter", "name": e[0], "rank": rank})
        top["modes"][name] = {"t": tm, "top": entries}
    top["t"] = int(start * 1000)
    top["log"] = top["log"][-300:]
    save_json("top.json", top)


history = load_json("history.json", [])
if not isinstance(history, list):
    history = []

# Einmaliger Neustart mit der Messung von Hand
if not any(p.get("reset") == RESET_ID for p in history):
    archive(history, RESET_ID)
    history = [{"reset": RESET_ID}, dict(SEED)]
    save_json("history.json", history)
    print("Verlauf neu gestartet mit der Messung von Hand:", SEED)
else:
    # Uhrzeit der Startmessung nachträglich auf 00:00 Uhr korrigieren
    fixed = False
    for p in history:
        if p.get("t") == OLD_SEED_T and p.get("overall") == SEED["overall"]:
            p["t"] = SEED["t"]
            fixed = True
    if fixed:
        save_json("history.json", history)
        print("Uhrzeit der Startmessung auf 00:00 Uhr korrigiert")

start = time.time()  # Start des Laufs
todo = list(LADDERS)
found = {}
when = {}  # Zeitpunkt, an dem die Zahl des jeweiligen Modus tatsächlich gelesen wurde
tops = {}  # Top 5 je Modus
top_when = {}
snippets = {}  # Seitentext zur Fehlersuche, wenn die Zahl gelesen wurde, die Top 5 aber nicht
rejected = {}  # stark abweichende Zahlen: Name -> (Zahl, Zeitpunkt)
is_reset = False

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
        # Top 5 werden immer mitgelesen, auch wenn die Zahl danach verworfen wird
        tp = parse_top(page) if page else []
        if tp:
            tops[name] = tp
            top_when[name] = time.time()
        elif n is not None and name not in snippets:
            snippets[name] = after_ranked(page, 200)
        if n is None:
            continue
        last = last_value(history, name)
        if last and abs(n - last) / last > MAX_JUMP:
            print(f"{name}: {n} weicht stark von {last} ab, verworfen", file=sys.stderr)
            rejected[name] = (n, time.time())
            continue
        rejected.pop(name, None)
        found[name] = n
        when[name] = time.time()
        todo.remove(name)
    if not todo or time.time() > DEADLINE or attempt == PASSES - 1:
        break
    time.sleep(PAUSE * (attempt + 1))

# Reset der Seite erkennen: fallen (fast) alle Modi gleichzeitig stark ab, ist das kein Ladefehler.
open_rej = {k: v for k, v in rejected.items() if k in todo}
is_reset = len(open_rej) >= RESET_MIN and all(
    v[0] < (last_value(history, k) or 0) * (1 - MAX_JUMP) for k, v in open_rej.items()
)
if is_reset:
    print(f"{len(open_rej)} Modi sind gleichzeitig stark abgefallen: Reset der Seite erkannt, Verlauf wird neu gestartet")
    for k, v in open_rej.items():
        found[k], when[k] = v[0], v[1]
        todo.remove(k)

# Top 5 speichern (Momentaufnahme, keine Messung, deshalb auch bei Testläufen)
if tops:
    update_top()
print(f"Top 5 gelesen für {len(tops)} von {len(LADDERS)} Modi")
no_top = [k for k in LADDERS if k not in tops]
if no_top:
    print("Top 5 nicht lesbar bei:", ", ".join(no_top))
for k, v in list(snippets.items())[:3]:
    print(f"  Seitentext nach 'players ranked' bei {k}: {v!r}")

if not found:
    # Seite liefert gerade keine Zahlen (z. B. Wartung oder Ausfall): Lauf überspringen
    print("Keine Zahlen gefunden, Lauf übersprungen")
    sys.exit(0)

point = {"t": int(start * 1000)}
point.update(found)
offsets = {k: round(when[k] - start) for k in found if round(when[k] - start) > 0}
if offsets:
    point["o"] = offsets

if DRY:
    print("Testlauf (von Hand gestartet), es wird keine Messung gespeichert:")
    print(point)
    if todo:
        print("Nicht gefunden:", ", ".join(todo))
    if is_reset:
        print("(Im normalen Lauf würde jetzt der alte Verlauf gesichert und neu gestartet.)")
    sys.exit(0)

if is_reset:
    stamp = datetime.datetime.now(datetime.timezone.utc)
    archive(history, "auto_" + stamp.strftime("%Y%m%d_%H%M"))
    history = [{"reset": "auto-" + stamp.strftime("%Y-%m-%d %H:%M")}]
history.append(point)
history = history[-10000:]
save_json("history.json", history)

print(point)
if todo:
    print("Nicht gefunden:", ", ".join(todo))
