"""Einmalige Rettung der Messungen vom 8.11.2026, die der Roboter damals verworfen hat.

Die Zahlen stehen noch in den Protokollen der alten Läufe auf GitHub. Dieses Skript liest sie
dort aus und trägt sie mit der Uhrzeit des jeweiligen Laufs in history.json ein.
Es läuft auf GitHub (Workflow "Recover measurements"), nicht auf deinem Rechner."""
import datetime
import json
import os
import re
import subprocess
import sys

REPO = os.environ["REPO"]
SINCE = "2026-11-07T23:00:00Z"  # 8.11.2026, 00:00 Uhr (MEZ)
MIN_GAP = 20 * 60  # Sekunden: Läufe, zu denen es schon eine Messung gibt, werden nicht doppelt eingetragen
LADDERS = ["overall", "sword", "axe", "mace", "spear_mace", "uhc", "netherite_pot", "pot", "smp",
           "diamond_smp", "vanilla", "cart"]

LINE = re.compile(
    r"(\d{4}-\d{2}-\d{2}T[\d:.]+Z)\s+([a-z_]+): (\d+) (?:weicht stark von|liegt weit unter dem letzten Wert) (\d+)"
)


def gh(*args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return r.stdout


def seconds(iso):
    iso = iso.rstrip("Z")
    if "." in iso:
        head, frac = iso.split(".")
        iso = head + "." + frac[:6]
    return datetime.datetime.fromisoformat(iso).replace(tzinfo=datetime.timezone.utc).timestamp()


try:
    with open("history.json", encoding="utf-8") as f:
        history = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    history = []

try:
    # Wichtig: ausdrücklich GET. Mit "-f" würde gh sonst POST senden und GitHub den Fehler 404 zurückgeben.
    raw = gh("api", "--method", "GET", f"repos/{REPO}/actions/workflows/track.yml/runs?per_page=100&created=%3E%3D{SINCE}")
    runs = json.loads(raw)["workflow_runs"]
except Exception as e:
    print("FEHLER beim Abrufen der Läufe von GitHub:", e)
    print("Hinweis: Unter Settings > Actions > General muss bei 'Workflow permissions' mindestens Lesezugriff erlaubt sein.")
    sys.exit(1)
print(f"{len(runs)} Läufe seit {SINCE} gefunden")

recovered = []
for run in sorted(runs, key=lambda r: r["run_started_at"]):
    if run["event"] != "schedule":
        continue  # Läufe von Hand speichern ohnehin nichts
    t0 = seconds(run["run_started_at"])
    when = datetime.datetime.fromtimestamp(t0, datetime.timezone.utc).strftime("%d.%m. %H:%M UTC")
    try:
        log = gh("run", "view", str(run["id"]), "--repo", REPO, "--log")
    except Exception as e:
        print(f"{when}: Protokoll nicht lesbar ({e})")
        continue
    vals = {}
    for m in LINE.finditer(log):
        if m.group(2) in LADDERS:
            vals[m.group(2)] = (int(m.group(3)), seconds(m.group(1)))  # der letzte Durchgang zählt
    if not vals:
        print(f"{when}: keine verworfenen Zahlen im Protokoll")
        continue
    entry = {"t": int(t0 * 1000)}
    entry.update({k: v[0] for k, v in vals.items()})
    offsets = {k: round(v[1] - t0) for k, v in vals.items() if round(v[1] - t0) > 0}
    if offsets:
        entry["o"] = offsets
    # nicht eintragen, wenn es zu diesem Lauf schon eine Messung gibt oder dieselben Zahlen schon gespeichert sind
    dup = False
    for p in history:
        if "t" not in p:
            continue
        if abs(p["t"] / 1000 - t0) < MIN_GAP or all(p.get(k) == entry[k] for k in vals):
            dup = True
            break
    if dup:
        print(f"{when}: schon vorhanden, übersprungen")
        continue
    history.append(entry)
    recovered.append(entry)
    print(f"{when}: {len(vals)} Modi nachgetragen, Overall {entry.get('overall')}")

markers = [p for p in history if "t" not in p]
points = sorted((p for p in history if "t" in p), key=lambda p: p["t"])
with open("history.json", "w", encoding="utf-8") as f:
    json.dump(markers + points, f, ensure_ascii=False, separators=(",", ":"))
print(f"Fertig: {len(recovered)} Messungen nachgetragen, insgesamt {len(points)} Messungen in history.json")
