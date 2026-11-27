#!/usr/bin/env python3
"""
Bygger players.json till Fotbollsspelen från github.com/salimt/football-datasets.

Datakällor (datalake/transfermarkt/):
  player_profiles/player_profiles.csv       spelar-ID och namn
  transfer_history/transfer_history.csv     alla transfers (Git LFS, ~80 MB)
  team_children/team_children.csv           ungdoms-, B- och reservlag per moderklubb
  team_details/team_details.csv             fullständiga klubbnamn
  player_latest_market_value/...csv         används bara för att rangordna spelare med samma namn

Per spelare räknas UNIKA seniorklubbar (efter klubb-ID, inte antal transfers).
Lån räknas. Ungdoms-, B-, reserv- och "klubbar" som Retired / Without Club räknas inte.

Användning:
  python3 build_players_data.py [utmapp]          hämtar färsk data från GitHub
  python3 build_players_data.py [utmapp] --local DIR   använder CSV-filer från DIR (datalake/transfermarkt)
"""
import csv, json, os, re, sys, collections, datetime, tempfile, urllib.request

REPO = "salimt/football-datasets"
BASE = "https://media.githubusercontent.com/media/%s/main/datalake/transfermarkt/" % REPO
FILES = {
    "profiles": "player_profiles/player_profiles.csv",
    "transfers": "transfer_history/transfer_history.csv",
    "children": "team_children/team_children.csv",
    "details": "team_details/team_details.csv",
    "values": "player_latest_market_value/player_latest_market_value.csv",
}

# Transfermarkts "klubbar" som inte är riktiga lag.
NOT_A_CLUB = {"515", "123", "75", "2113"}  # Without Club, Retired, Unknown, Career break
NOT_A_CLUB_NAMES = re.compile(r"^(without club|retired|unknown|career break|ban|banned|suspended)$", re.I)

# Namnmönster för ungdoms-, B- och reservlag som inte finns i team_children.
YOUTH = re.compile(
    r"(\bU\s?-?\d{2}\b|\bUnder[\s-]?\d{2}\b|\bYouth\b|\bYth\b\.?|\bYout\w*|\bJuniors?\b|\bJgd\b\.?|\bJun\b\.?|"
    r"\bPrimavera\b|\bReserves?\b|\bRes\b\.?|\bSub[\s-]?\d{2}\b|\bJuvenil\w*|\bAmateurs?\b|\bCastilla\b|"
    r"\bNext Gen\b|^Jong\s|\bAcademy\b|\bAcad\b\.?|\bUEFA U\d+\b)",
    re.I,
)
RESERVE_SUFFIX = re.compile(r"\s(B|C|D|II|III|IV|2|3)$")


def open_csv(key, local):
    if local:
        path = os.path.join(local, FILES[key])
        return open(path, encoding="utf-8", newline="")
    # Hämtar alltid färsk data (annars skulle en gammal nedladdning återanvändas).
    path = os.path.join(tempfile.gettempdir(), "fotbollsspelen_" + key + ".csv")
    print("Hämtar", FILES[key], "…", flush=True)
    urllib.request.urlretrieve(BASE + FILES[key], path)
    return open(path, encoding="utf-8", newline="")


def strip_id(name):
    return re.sub(r"\s*\(\d+\)\s*$", "", name or "").strip()


def main():
    args = [a for a in sys.argv[1:]]
    local = None
    if "--local" in args:
        i = args.index("--local"); local = args[i + 1]; del args[i:i + 2]
    out_dir = args[0] if args else "."
    os.makedirs(out_dir, exist_ok=True)

    # 1. Barnlag (ungdom, B, reserv) som ska uteslutas.
    child_ids = set()
    with open_csv("children", local) as f:
        for r in csv.DictReader(f):
            if r["child_team_id"] == r["parent_team_id"]:
                continue
            # Datasetet har enstaka omvända rader (t.ex. Atalanta BC som "barn" till Atalanta BC U17).
            # En koppling där "föräldern" själv är ett ungdoms-/reservlag ignoreras.
            pname = r.get("parent_team_name") or ""
            if YOUTH.search(pname) or RESERVE_SUFFIX.search(pname):
                continue
            child_ids.add(r["child_team_id"])

    # 2. Fullständiga klubbnamn från team_details.
    full_name = {}
    with open_csv("details", local) as f:
        for r in csv.DictReader(f):
            full_name[r["club_id"]] = strip_id(r["club_name"])

    # 3. Transfers: unika klubbar per spelare och klubbnamn.
    names = collections.defaultdict(collections.Counter)
    pclubs = collections.defaultdict(set)
    ntransfers = collections.Counter()
    with open_csv("transfers", local) as f:
        for r in csv.DictReader(f):
            pid = r["player_id"]
            ntransfers[pid] += 1
            for side in ("from", "to"):
                tid = r[side + "_team_id"]
                nm = r[side + "_team_name"]
                if tid:
                    names[tid][nm] += 1
                    pclubs[pid].add(tid)

    def is_senior(tid):
        if tid in NOT_A_CLUB or tid in child_ids:
            return False
        nm = names[tid].most_common(1)[0][0] if names[tid] else full_name.get(tid, "")
        if NOT_A_CLUB_NAMES.match(nm):
            return False
        for cand in {nm, full_name.get(tid, "")}:
            if cand and (YOUTH.search(cand) or RESERVE_SUFFIX.search(cand)):
                return False
        return True

    senior_cache = {}
    def senior(tid):
        if tid not in senior_cache:
            senior_cache[tid] = is_senior(tid)
        return senior_cache[tid]

    # 4. Marknadsvärde, bara för rangordning vid lika namn.
    value = {}
    with open_csv("values", local) as f:
        for r in csv.DictReader(f):
            try:
                value[r["player_id"]] = float(r["value"])
            except ValueError:
                pass

    # 5. Profiler: namn + nuvarande klubb (om den saknas i transferhistoriken).
    players = []
    with open_csv("profiles", local) as f:
        for r in csv.DictReader(f):
            pid = r["player_id"]
            clubs = {t for t in pclubs.get(pid, ()) if senior(t)}
            for extra in (r.get("current_club_id"), r.get("on_loan_from_club_id")):
                if extra and extra.strip() and extra not in ("0",):
                    if extra not in names:
                        names[extra][r.get("current_club_name") or r.get("on_loan_from_club_name") or ""] += 1
                    if senior(extra):
                        clubs.add(extra)
            if not clubs:
                continue
            name = strip_id(r["player_name"])
            if not name:
                continue
            players.append((pid, name, clubs))

    players.sort(key=lambda p: (-value.get(p[0], 0.0), -ntransfers.get(p[0], 0), int(p[0])))

    # 6. Komprimera: klubbtabell + spelare som [id, namn, [klubbindex]].
    used = sorted({t for _, _, cs in players for t in cs}, key=int)
    idx = {t: i for i, t in enumerate(used)}
    club_names = []
    for t in used:
        nm = names[t].most_common(1)[0][0] if names[t] else ""
        club_names.append(full_name.get(t) or nm)

    data = {
        "source": "https://github.com/" + REPO,
        "built": datetime.date.today().isoformat(),
        "clubIds": [int(t) for t in used],
        "clubNames": club_names,
        "players": [[int(pid), nm, sorted(idx[t] for t in cs)] for pid, nm, cs in players],
    }
    out = os.path.join(out_dir, "players.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("Spelare:", len(players), "| klubbar:", len(used), "| fil:", round(os.path.getsize(out) / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
