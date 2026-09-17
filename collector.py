#!/usr/bin/env python3
"""
collector.py — ververst data/fryslan.json met stemuitslagen van
Provinciale Staten Fryslân, uit de publieke Notubiz-bronnen.

Alleen standaardbibliotheek. Wordt wekelijks gedraaid door
.github/workflows/update.yml — kan ook los gedraaid worden:

    python3 collector.py
"""

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

API = "https://api.notubiz.nl"
VERSION = "1.21"          # verplicht; oudere versies negeren stil alle parameters
UA = "stimmen-fryslan/1.0 (open data hergebruik, github pages; +https://github.com)"

ORGANISATIE = 822          # Provincie Fryslân
GREMIUM = 430               # Provinciale Staten, plenair
SLUG = "fryslan"
VAN = "2023-03-29"          # installatie van de huidige Staten

OUT_PATH = os.path.join(os.path.dirname(__file__), "data", "fryslan.json")


# --------------------------------------------------------------------------- http

def _get(url, pause=0.5):
    last = None
    for poging in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read().decode("utf-8", errors="replace")
            time.sleep(pause)
            return body
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last = e
            time.sleep(2 * (poging + 1))
    raise RuntimeError("Ophalen mislukt: %s (%s)" % (url, last))


def api(path, params):
    p = dict(params)
    p["format"] = "json"
    p["version"] = VERSION
    qs = urllib.parse.urlencode(p, quote_via=urllib.parse.quote)
    raw = _get("%s/%s?%s" % (API, path.lstrip("/"), qs))
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("Geen JSON van %s/%s\n%s" % (API, path, raw[:300]))


# --------------------------------------------------------------------------- api

def haal_vergaderingen(datum_van, datum_tot):
    out, pagina = [], 1
    while pagina <= 100:
        data = api("events", {
            "organisation_id": ORGANISATIE,
            "date_from": "%s 00:00:00" % datum_van,
            "date_to": "%s 23:59:59" % datum_tot,
            "page": pagina,
        })
        events = data.get("events") or []
        if not events:
            break
        for ev in events:
            if (ev.get("gremium") or {}).get("id") != GREMIUM:
                continue
            if ((ev.get("event_type_data") or {}).get("agenda_item_count") or 0) <= 0:
                continue
            plan = (ev.get("plannings") or [{}])[0]
            out.append((ev.get("id"), (plan.get("start_date") or "")[:10], _titel(ev)))
        pag = data.get("pagination") or {}
        if pag.get("has_more_pages") is False or not events:
            break
        pagina += 1
    out.sort(key=lambda r: r[1])
    return out


def _titel(ev):
    attrs = ev.get("attributes")
    if isinstance(attrs, dict):
        for k in ("1", 1):
            if k in attrs:
                return str(attrs[k])
        for v in attrs.values():
            if isinstance(v, str):
                return v
    if isinstance(attrs, list):
        for a in attrs:
            if isinstance(a, dict) and str(a.get("id")) == "1":
                return str(a.get("value") or "")
    return ""


def haal_stemmingen(meeting_id):
    data = api("agenda_items/votings", {"meeting_id": meeting_id})
    res = []
    for v in data.get("votings") or []:
        td = v.get("type_data") or {}
        stemmen = td.get("votes") or []
        res.append({
            "id": v.get("id"),
            "voting_id": td.get("voting_id"),
            "titel": (td.get("title") or "").strip(),
            "uitslag": {"adopted": "aangenomen", "rejected": "verworpen",
                        "equal": "staken"}.get(td.get("voting_result"), td.get("voting_result") or ""),
            "type": _type_uit_titel(td.get("voting_type"), td.get("title")),
            "api_voor": sum(1 for s in stemmen if s.get("vote") == "in_favor"),
            "api_tegen": sum(1 for s in stemmen if s.get("vote") == "against"),
        })
    return res


def _type_uit_titel(voting_type, titel):
    if voting_type:
        return voting_type
    t = (titel or "").lower()
    if "moasje" in t or "motie" in t:
        return "motie"
    if "amendemint" in t or "amendement" in t:
        return "amendement"
    return "besluit"


def portal_url(meeting_id):
    try:
        d = api("events/meetings/%s" % meeting_id, {})
        u = d.get("url") or (d.get("meeting") or {}).get("url")
        if u:
            return u
    except Exception:
        pass
    return "https://%s.notubiz.nl/vergadering/%s" % (SLUG, meeting_id)


# --------------------------------------------------------------------- html-parser

class _FractieParser(HTMLParser):
    """Leest een votes_parties-blok: buitenste <li> = fractienaam,
    binnenste <li class="in_favor|against"> = stem van een lid."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.diepte = 0
        self.fracties = {}
        self._naam = []
        self._huidig = None

    def handle_starttag(self, tag, attrs):
        if tag != "li":
            return
        klasse = dict(attrs).get("class") or ""
        self.diepte += 1
        if self.diepte == 1:
            self._naam = []
            self._huidig = None
        elif self._huidig:
            if "in_favor" in klasse:
                self.fracties[self._huidig]["voor"] += 1
            elif "against" in klasse:
                self.fracties[self._huidig]["tegen"] += 1

    def handle_endtag(self, tag):
        if tag == "li":
            self.diepte = max(0, self.diepte - 1)
            if self.diepte == 0:
                self._huidig = None

    def handle_data(self, data):
        if self.diepte == 1:
            t = data.strip()
            if t and t.lower() != "leden:":
                self._naam.append(t)
                naam = " ".join(self._naam).strip()
                if naam:
                    self._huidig = naam
                    self.fracties.setdefault(naam, {"voor": 0, "tegen": 0})


def parse_pagina(html):
    markers = [(m.start(), int(m.group(1))) for m in re.finditer(r"chart_(\d+)", html)]
    gezien, uniek = set(), []
    for pos, vid in markers:
        if vid not in gezien:
            gezien.add(vid)
            uniek.append((pos, vid))

    resultaat = {}
    for i, (pos, vid) in enumerate(uniek):
        eind = uniek[i + 1][0] if i + 1 < len(uniek) else len(html)
        stuk = html[pos:eind]
        blokken = re.findall(r'votes_parties.*?<ul[^>]*>(.*?)</ul>\s*</div>', stuk, re.S | re.I)
        if not blokken:
            m = re.search(r"votes_parties(.*)$", stuk, re.S | re.I)
            blokken = [m.group(1)] if m else []
        p = _FractieParser()
        for b in blokken:
            p.feed(b)
        p.close()
        if p.fracties:
            resultaat[vid] = p.fracties
    return resultaat


# --------------------------------------------------------------------------- main

def main():
    tot = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print("Vergaderingen ophalen van %s tot %s ..." % (VAN, tot))
    vergaderingen = haal_vergaderingen(VAN, tot)
    print("%d plenaire vergaderingen gevonden." % len(vergaderingen))

    votings = []
    for n, (mid, datum, titel) in enumerate(vergaderingen, 1):
        try:
            stemmingen = haal_stemmingen(mid)
        except Exception as e:
            print("  ! vergadering %s: votings mislukt (%s)" % (mid, e))
            continue
        if not stemmingen:
            continue

        per_fractie = {}
        try:
            html = _get(portal_url(mid))
            per_fractie = parse_pagina(html)
        except Exception as e:
            print("  ! vergadering %s: portal mislukt (%s)" % (mid, e))

        print("[%d/%d] %s  vergadering %s: %d stemmingen, %d met fracties"
              % (n, len(vergaderingen), datum, mid, len(stemmingen), len(per_fractie)))

        for s in stemmingen:
            fr = per_fractie.get(s["id"]) or per_fractie.get(s["voting_id"]) or {}
            fracties = {naam: {"voor": t["voor"], "tegen": t["tegen"]}
                        for naam, t in sorted(fr.items())}
            votings.append({
                "id": s["id"],
                "datum": datum,
                "vergadering": titel,
                "titel": s["titel"],
                "type": s["type"],
                "uitslag": s["uitslag"],
                "fracties": fracties,
                "totaal_voor": sum(f["voor"] for f in fracties.values()) or s["api_voor"],
                "totaal_tegen": sum(f["tegen"] for f in fracties.values()) or s["api_tegen"],
            })

    votings.sort(key=lambda v: (v["datum"], v["id"]), reverse=True)

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provincie": "Fryslân",
        "bron": "Notubiz open data (fryslan.notubiz.nl)",
        "van": VAN,
        "tot": tot,
        "votings": votings,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("\nGeschreven: %s (%d stemmingen)" % (OUT_PATH, len(votings)))


if __name__ == "__main__":
    main()
