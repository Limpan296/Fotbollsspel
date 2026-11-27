#!/usr/bin/env python3
"""
Bygger vemarjag.json (ledtrådar för spelet "Vem är jag?") från samma datakälla som players.json
(github.com/salimt/football-datasets, Transfermarkt).

Allt som sägs i en ledtråd kommer ur datasetet: födelseland/medborgarskap, födelseår, position, fot,
antal unika seniorklubbar, klubbar, klubbarnas länder, senaste/nuvarande klubb och landskamper.
Titlar och utmärkelser finns inte i datasetet och används därför inte.
Varje fråga kontrolleras mot hela datasetet så att bara en spelare passar på samtliga fem ledtrådar.

Användning:
  python3 build_vemarjag.py players.json [utmapp] [--local DIR]
    players.json  filen som build_players_data.py gjort (innehåller seniorklubbar per spelare)
    --local DIR   använd CSV-filer från DIR (datalake/transfermarkt) i stället för att hämta dem
"""
import csv, json, os, re, sys, collections, datetime, tempfile, urllib.request

REPO = "salimt/football-datasets"
BASE = "https://media.githubusercontent.com/media/%s/main/datalake/transfermarkt/" % REPO
FILES = {
    "profiles": "player_profiles/player_profiles.csv",
    "national": "player_national_performances/player_national_performances.csv",
    "details": "team_details/team_details.csv",
    "transfers": "transfer_history/transfer_history.csv",
    "values": "player_market_value/player_market_value.csv",
}
POOL_MAX = 900          # max antal frågor
MIN_PEAK_VALUE = 25e6   # "kända nog": högsta marknadsvärde...
MIN_CAPS = 70           # ...eller många landskamper

SV = {  # engelska landsnamn (Transfermarkt) -> svenska
 "Afghanistan":"Afghanistan","Albania":"Albanien","Algeria":"Algeriet","Angola":"Angola","Argentina":"Argentina","Armenia":"Armenien",
 "Australia":"Australien","Austria":"Österrike","Azerbaijan":"Azerbajdzjan","Belarus":"Belarus","Belgium":"Belgien","Benin":"Benin",
 "Bolivia":"Bolivia","Bosnia-Herzegovina":"Bosnien och Hercegovina","Brazil":"Brasilien","Bulgaria":"Bulgarien","Burkina Faso":"Burkina Faso",
 "Cameroon":"Kamerun","Canada":"Kanada","Cape Verde":"Kap Verde","Chile":"Chile","China":"Kina","Colombia":"Colombia","Congo":"Kongo-Brazzaville",
 "DR Congo":"Kongo-Kinshasa","Costa Rica":"Costa Rica","Cote d'Ivoire":"Elfenbenskusten","Croatia":"Kroatien","Cuba":"Kuba","Curacao":"Curaçao",
 "Cyprus":"Cypern","Czech Republic":"Tjeckien","Denmark":"Danmark","Ecuador":"Ecuador","Egypt":"Egypten","England":"England","Equatorial Guinea":"Ekvatorialguinea",
 "Estonia":"Estland","Finland":"Finland","France":"Frankrike","Gabon":"Gabon","Gambia":"Gambia","Georgia":"Georgien","Germany":"Tyskland","Ghana":"Ghana",
 "Greece":"Grekland","Guinea":"Guinea","Guinea-Bissau":"Guinea-Bissau","Haiti":"Haiti","Honduras":"Honduras","Hungary":"Ungern","Iceland":"Island",
 "Iran":"Iran","Iraq":"Irak","Ireland":"Irland","Israel":"Israel","Italy":"Italien","Jamaica":"Jamaica","Japan":"Japan","Kazakhstan":"Kazakstan",
 "Kenya":"Kenya","Korea, South":"Sydkorea","Kosovo":"Kosovo","Latvia":"Lettland","Lithuania":"Litauen","Luxembourg":"Luxemburg","Mali":"Mali",
 "Mexico":"Mexiko","Moldova":"Moldavien","Montenegro":"Montenegro","Morocco":"Marocko","Mozambique":"Moçambique","Netherlands":"Nederländerna",
 "New Zealand":"Nya Zeeland","Nigeria":"Nigeria","North Macedonia":"Nordmakedonien","Northern Ireland":"Nordirland","Norway":"Norge","Panama":"Panama",
 "Paraguay":"Paraguay","Peru":"Peru","Poland":"Polen","Portugal":"Portugal","Romania":"Rumänien","Russia":"Ryssland","Scotland":"Skottland",
 "Senegal":"Senegal","Serbia":"Serbien","Sierra Leone":"Sierra Leone","Slovakia":"Slovakien","Slovenia":"Slovenien","South Africa":"Sydafrika",
 "Spain":"Spanien","Sweden":"Sverige","Switzerland":"Schweiz","Syria":"Syrien","Togo":"Togo","Trinidad and Tobago":"Trinidad och Tobago","Tunisia":"Tunisien",
 "Turkey":"Turkiet","Uganda":"Uganda","Ukraine":"Ukraina","United States":"USA","Uruguay":"Uruguay","Venezuela":"Venezuela","Wales":"Wales","Zambia":"Zambia","Zimbabwe":"Zimbabwe",
 "Saudi Arabia":"Saudiarabien","Qatar":"Qatar","United Arab Emirates":"Förenade Arabemiraten","India":"Indien","Thailand":"Thailand","Tanzania":"Tanzania",
 "Suriname":"Surinam","Congo DR":"Kongo-Kinshasa","Korea, North":"Nordkorea","Libya":"Libyen","Türkiye":"Turkiet","The Gambia":"Gambia","Guadeloupe":"Guadeloupe","Martinique":"Martinique","Mauritania":"Mauretanien","Dominican Republic":"Dominikanska republiken","Central African Republic":"Centralafrikanska republiken","Philippines":"Filippinerna","El Salvador":"El Salvador","Indonesia":"Indonesien","Malta":"Malta","Monaco":"Monaco","Andorra":"Andorra","Liechtenstein":"Liechtenstein","Madagascar":"Madagaskar","Liberia":"Liberia","Comoros":"Komorerna",
}
POS = {  # Transfermarkt-position -> (svenskt ord med "en/ett"-fri form)
 "Goalkeeper":"målvakt","Defender":"försvarare","Defender - Centre-Back":"mittback","Defender - Right-Back":"högerback","Defender - Left-Back":"vänsterback",
 "Defender - Sweeper":"libero","Midfield":"mittfältare","Midfield - Central Midfield":"central mittfältare","Midfield - Defensive Midfield":"defensiv mittfältare",
 "Midfield - Attacking Midfield":"offensiv mittfältare","Midfield - Right Midfield":"högermittfältare","Midfield - Left Midfield":"vänstermittfältare",
 "Attack":"anfallare","Attack - Centre-Forward":"anfallare","Attack - Right Winger":"högerytter","Attack - Left Winger":"vänsterytter","Attack - Second Striker":"andra anfallare",
}
FOOT = {"right": "högerfotad", "left": "vänsterfotad", "both": "tvåfotad"}
NOT_A_CLUB = {"515", "123", "75", "2113"}


def open_csv(key, local):
    if local:
        return open(os.path.join(local, FILES[key]), encoding="utf-8", newline="")
    path = os.path.join(tempfile.gettempdir(), "fotbollsspelen_vem_" + key + ".csv")
    print("Hämtar", FILES[key], "…", flush=True)
    urllib.request.urlretrieve(BASE + FILES[key], path)
    return open(path, encoding="utf-8", newline="")


def strip_id(n): return re.sub(r"\s*\(\d+\)\s*$", "", n or "").strip()
def first_nat(c): return (re.split(r"\s{2,}", (c or "").strip())[0] if c else "").strip()
def sv(x): return SV.get(x)
def lst(a):
    return a[0] if len(a) == 1 else ", ".join(a[:-1]) + " och " + a[-1]
def floor_to(n, step): return (n // step) * step


def main():
    args = sys.argv[1:]
    local = None
    if "--local" in args:
        i = args.index("--local"); local = args[i + 1]; del args[i:i + 2]
    players_json = args[0]; out_dir = args[1] if len(args) > 1 else "."
    PJ = json.load(open(players_json, encoding="utf-8"))
    club_ids = [str(c) for c in PJ["clubIds"]]; club_names = PJ["clubNames"]
    cname = dict(zip(club_ids, club_names))
    pclubs = {str(p[0]): {club_ids[i] for i in p[2]} for p in PJ["players"]}
    pname = {str(p[0]): p[1] for p in PJ["players"]}

    # klubbland
    ccountry = {}
    with open_csv("details", local) as f:
        for r in csv.DictReader(f):
            if r["country_name"]: ccountry[r["club_id"]] = r["country_name"]

    # profiler
    prof = {}
    with open_csv("profiles", local) as f:
        for r in csv.DictReader(f):
            pid = r["player_id"]
            if pid in pclubs and not r["date_of_death"]:
                prof[pid] = r

    # högsta marknadsvärde (för "kändisfaktor")
    peak = collections.defaultdict(float)
    with open_csv("values", local) as f:
        for r in csv.DictReader(f):
            try: v = float(r["value"])
            except ValueError: continue
            if r["player_id"] in prof and v > peak[r["player_id"]]: peak[r["player_id"]] = v

    # landslag: vilket team_id är A-landslaget för vilket land? Rösta: spelarens landslag med flest matcher.
    nat = collections.defaultdict(list)
    with open_csv("national", local) as f:
        for r in csv.DictReader(f):
            if r["player_id"] in prof:
                nat[r["player_id"]].append((r["team_id"], int(r["matches"] or 0), int(r["goals"] or 0)))
    votes = collections.defaultdict(collections.Counter)
    for pid, rows in nat.items():
        c = first_nat(prof[pid]["citizenship"])
        if c: votes[max(rows, key=lambda x: x[1])[0]][c] += 1
    team_country = {t: v.most_common(1)[0][0] for t, v in votes.items() if sum(v.values()) >= 3}

    def caps(pid):
        best = (0, 0, None)
        cits = [x.strip() for x in re.split(r"\s{2,}", prof[pid]["citizenship"] or "") if x.strip()]
        for t, m, g in nat.get(pid, []):
            if team_country.get(t) in cits and m > best[0]: best = (m, g, team_country[t])
        return best

    # senaste klubb via transferhistorik (för spelare som lagt av)
    last_club = {}
    with open_csv("transfers", local) as f:
        for r in csv.DictReader(f):
            pid = r["player_id"]
            if pid not in prof: continue
            for side in ("to", "from"):
                t = r[side + "_team_id"]
                if t in pclubs[pid]:
                    d = r["transfer_date"] or ""
                    if pid not in last_club or d >= last_club[pid][0]: last_club[pid] = (d, t)

    # fakta per spelare
    F = {}
    miss = collections.Counter()
    for pid, r in prof.items():
        pos = POS.get(r["position"])
        nation = first_nat(r["citizenship"])
        if not pos or not r["date_of_birth"]: continue
        if not sv(nation): miss[nation] += 1; continue
        birth = r["country_of_birth"]
        cur = r["current_club_id"]
        retired = cur == "123"
        if retired or cur in NOT_A_CLUB or cur not in pclubs[pid]:
            lc = last_club.get(pid)
            cur_club = lc[1] if lc else None
        else:
            cur_club = cur
        if not cur_club: continue
        m, g, cn = caps(pid)
        h = float(r["height"] or 0)
        F[pid] = {
            "id": int(pid), "name": pname[pid], "nation": nation, "birth": birth if sv(birth) else None, "year": int(r["date_of_birth"][:4]),
            "pos": r["position"], "foot": r["foot"] if r["foot"] in FOOT else None, "h": int(h * 100) if 1 < h < 2.3 else (int(h) if 150 < h < 230 else 0),
            "clubs": pclubs[pid], "n": len(pclubs[pid]), "cur": cur_club, "ret": retired or cur in NOT_A_CLUB,
            "caps": m, "ngoals": g, "capsOf": cn,
            "countries": {ccountry[c] for c in pclubs[pid] if c in ccountry},
        }
    print("Saknade länder i ordlistan:", miss.most_common(12))

    # urval: kända spelare
    fame = {}
    for pid, f in F.items():
        fame[pid] = max(peak.get(pid, 0) / 1e6, f["caps"] * 0.6)
    cand = [pid for pid, f in F.items() if (peak.get(pid, 0) >= MIN_PEAK_VALUE or f["caps"] >= MIN_CAPS) and f["n"] >= 2]
    cand.sort(key=lambda p: -fame[p])
    cand = cand[:POOL_MAX + 300]
    print("Kandidater:", len(cand))

    club_pop = collections.Counter(c for f in F.values() for c in f["clubs"])
    by_club = collections.defaultdict(set)
    for pid, f in F.items():
        for c in f["clubs"]: by_club[c].add(pid)

    def tense(f, a, b): return b if f["ret"] else a   # nutid / dåtid

    def build(pid):
        f = F[pid]
        used = []
        # ledtråd 1: född i/medborgarskap + antal klubbar
        loc = ("Jag är född i " + sv(f["birth"])) if f["birth"] else ("Jag har medborgarskap i " + sv(f["nation"]))
        c1 = "%s och har representerat %d olika klubbar under min seniorkarriär." % (loc, f["n"])
        # ledtråd 2: position + fot
        c2 = "Jag %s som %s%s." % (tense(f, "spelar", "spelade"), POS[f["pos"]], (" och är " + FOOT[f["foot"]]) if f["foot"] else "")
        # ledtråd 3: länder (minst två kända) annars födelseår + längd
        ctr = sorted(f["countries"])
        use_countries = len(ctr) >= 2
        if use_countries:
            shown = ctr[:4]
            if not all(sv(c) for c in shown): return None
            c3 = "Jag har %sspelat i %s." % ("bland annat " if len(ctr) > len(shown) else "", lst([sv(c) for c in shown]))
        else:
            c3 = "Jag är född %d%s." % (f["year"], (" och är över %s m lång" % ("%d,%02d" % (floor_to(f["h"], 5) // 100, floor_to(f["h"], 5) % 100))) if f["h"] else "")
        # ledtråd 5: nuvarande/senaste klubb + landskamper (+ födelseår om det inte redan sagts)
        curn = cname[f["cur"]].strip()
        sent = ["Min %s klubb %s %s." % ("senaste" if f["ret"] else "nuvarande", "var" if f["ret"] else "är", curn)]
        has_caps = bool(f["caps"] >= 20 and f["capsOf"] and sv(f["capsOf"]))
        if has_caps: sent.append("Jag har gjort minst %d landskamper för %s." % (floor_to(f["caps"], 10), sv(f["capsOf"])))
        if use_countries: sent.append("Jag är född %d." % f["year"])
        c5 = " ".join(sent)
        # ledtråd 4: kända klubbar först; lägg till fler tills bara en spelare passar
        cl = sorted(f["clubs"] - {f["cur"]} if len(f["clubs"]) > 3 else f["clubs"], key=lambda c: (-club_pop[c], c))
        for k in range(3, min(6, len(cl)) + 1):
            chosen = cl[:k]
            match = set.intersection(*[by_club[c] for c in chosen])
            match = [p for p in match if satisfies(F[p], f, use_countries, has_caps)]
            if len(match) == 1:
                c4 = "Jag har representerat %s." % lst([cname[c].strip() for c in chosen])
                return {"id": f["id"], "name": f["name"], "clues": [c1, c2, c3, c4, c5], "clubs": f["n"]}
        return None

    def satisfies(o, f, uc, has_caps):
        """Passar spelare o på samma ledtrådar som f? (c1: land+antal, c2: position+fot, c3, c5)"""
        if o["n"] != f["n"] or o["pos"] != f["pos"]: return False
        if f["birth"]:
            if o["birth"] != f["birth"]: return False
        elif o["nation"] != f["nation"]: return False
        if f["foot"] and o["foot"] != f["foot"]: return False
        if uc and not f["countries"] <= o["countries"]: return False
        if not uc and o["year"] != f["year"]: return False
        if o["cur"] != f["cur"]: return False
        if has_caps and not (o["caps"] >= floor_to(f["caps"], 10) and o["capsOf"] == f["capsOf"]): return False
        return True

    out = []
    for i, pid in enumerate(cand):
        q = build(pid)
        if q: out.append((pid, q))
        if len(out) >= POOL_MAX: break
    n = len(out)
    res = []
    for i, (pid, q) in enumerate(out):
        q["d"] = 1 if i < n * 0.25 else (2 if i < n * 0.65 else 3)
        res.append(q)
    data = {"source": "https://github.com/" + REPO, "built": datetime.date.today().isoformat(), "questions": res}
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "vemarjag.json")
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("Frågor:", len(res), "| svårighet:", collections.Counter(q["d"] for q in res), "| fil:", round(os.path.getsize(path) / 1e3), "kB")


if __name__ == "__main__":
    main()
