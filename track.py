import datetime
import json
import re
import sys
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


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def count(paths):
    for path in paths:
        for host in HOSTS:
            try:
                html = fetch(f"{host}/leaderboard/{path}")
                m = re.search(
                    r"([\d][\d.,\s]*)\s+players\s+ranked", html, re.I
                ) or re.search(r"of\s+([\d][\d.,]*)\s+players", html, re.I)
                if m:
                    n = int(re.sub(r"\D", "", m.group(1)))
                    if n > 0:
                        return n
            except Exception as e:
                print(f"{path} {host}: {e}", file=sys.stderr)
    return None


point = {"t": int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)}
for ladder, paths in LADDERS.items():
    c = count(paths)
    if c is not None:
        point[ladder] = c

if len(point) == 1:
    sys.exit("Keine Zahlen gefunden")

try:
    with open("history.json", encoding="utf-8") as f:
        history = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    history = []

history.append(point)
history = history[-5000:]

with open("history.json", "w", encoding="utf-8") as f:
    json.dump(history, f, separators=(",", ":"))

print(point)
