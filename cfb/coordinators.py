"""Coordinator detector: keep table coordinators current from Wikipedia team-season pages.

Run weekly by the worker (job "coordinator_watch"), about 3 requests a run (50 pages per request).
For each FBS team and unit (offense, defense):
  - no row yet this season -> add it, with is_new computed against last season (the T-OCDC rule: none of this
    season's names was listed last season).  This is how each new season's preseason staff gets loaded.
  - the infobox now lists a name the stored row doesn't -> a *pending* coordinator_changes row for an admin.
    Confirming it adds the new names to the season's row; is_new (preseason) never changes.
The parsing is the one T-OCDC used (2026-11-18): both infobox templates, co-coordinator fields, notes dropped.

    docker compose exec worker python -m cfb.coordinators 2026 --dry-run    (print only, saves nothing)
    docker compose exec worker python -m cfb.coordinators 2026
"""

import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from cfb.db import connect

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "sports-model-research/0.1 (personal, low-volume research)"

# Our team name -> Wikipedia's, where they differ (found 2026-11-18)
TITLE_MAP = {
    "App State Mountaineers": "Appalachian State Mountaineers",
    "Delaware Blue Hens": "Delaware Fightin' Blue Hens",
    "Florida International Panthers": "FIU Panthers",
    "Hawai'i Rainbow Warriors": "Hawaii Rainbow Warriors",
    "Massachusetts Minutemen": "UMass Minutemen",
    "Miami (OH) RedHawks": "Miami RedHawks",
    "San José State Spartans": "San Jose State Spartans",
    "UL Monroe Warhawks": "Louisiana–Monroe Warhawks",
}

FBS_TEAMS_SQL = """
SELECT DISTINCT t.id, t.school, t.mascot
FROM games g
JOIN teams t ON t.id IN (g.home_id, g.away_id)
WHERE g.league = 'cfb'
  AND g.season = %(season)s
  AND ((t.id = g.home_id AND g.home_classification = 'fbs')
       OR (t.id = g.away_id AND g.away_classification = 'fbs'))
ORDER BY t.school
"""

UNITS = {"offense": r"(co)?off_coach\d*", "defense": r"(co)?def_coach\d*"}


def page_title(season, school, mascot):
    name = f"{school} {mascot}"
    return f"{season} {TITLE_MAP.get(name, name)} football team"


def fetch_pages(titles):
    """{title: wikitext before the first section heading, or None if there's no such page}."""
    pages = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        params = {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                  "titles": "|".join(batch), "redirects": 1, "format": "json", "formatversion": 2, "maxlag": 5}
        req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": USER_AGENT})
        for attempt in range(5):
            try:
                data = json.load(urllib.request.urlopen(req, timeout=60))
                break
            except urllib.error.HTTPError as err:
                if err.code != 429 or attempt == 4:
                    raise
                time.sleep(int(err.headers.get("Retry-After") or 60))
        query = data.get("query", {})
        asked = {t: t for t in batch}
        for n in query.get("normalized", []):
            asked[n["to"]] = asked.get(n["from"], n["from"])
        for r in query.get("redirects", []):
            asked[r["to"]] = asked.get(r["from"], r["from"])
        for p in query.get("pages", []):
            title = asked.get(p["title"], p["title"])
            if p.get("missing") or "revisions" not in p:
                pages[title] = None
            else:
                pages[title] = p["revisions"][0]["slots"]["main"]["content"].split("\n==", 1)[0]
        for t in batch:
            pages.setdefault(t, None)
        time.sleep(5)
    return pages


def infobox_params(text):
    """The season infobox's fields as {name: raw value}; {} if the page has no season infobox."""
    start = re.search(r"\{\{\s*Infobox (?:NCAA|college sports) team season", text, re.I)
    if not start:
        return {}
    i, depth_t, depth_l, cur, parts = start.start() + 2, 1, 0, [], []
    while i < len(text) and depth_t > 0:
        two = text[i:i + 2]
        if two == "{{":
            depth_t += 1; cur.append(two); i += 2; continue
        if two == "}}":
            depth_t -= 1
            if depth_t == 0:
                break
            cur.append(two); i += 2; continue
        if two == "[[":
            depth_l += 1; cur.append(two); i += 2; continue
        if two == "]]":
            depth_l -= 1; cur.append(two); i += 2; continue
        if text[i] == "|" and depth_t == 1 and depth_l == 0:
            parts.append("".join(cur)); cur = []; i += 1; continue
        cur.append(text[i]); i += 1
    parts.append("".join(cur))
    out = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


def name_key(name):
    """A name reduced for comparing: no accents, no punctuation other than . ' -, lower case."""
    p = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    p = re.sub(r"[^A-Za-z.' -]", " ", p)
    return re.sub(r"\s+", " ", p).strip(" .-'").lower()


def field_names(value):
    """Display names in one coordinator field (links resolved; notes, refs and "(interim)" dropped)."""
    v = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    v = re.sub(r"<ref.*?(</ref>|/>)", "", v, flags=re.S)
    v = re.sub(r"\{\{\s*(?:nowrap|small)\s*\|(.*?)\}\}", r"\1", v, flags=re.I)
    v = re.sub(r"\{\{\s*(?:plainlist|ubl|unbulleted list|flatlist)\s*\|?", "", v, flags=re.I).replace("}}", "")
    v = re.sub(r"\[\[([^|\]]*\|)?([^\]]*)\]\]", r"\2", v)
    v = re.sub(r"\([^)]*\)", "", v)
    out = []
    for piece in re.split(r"<br\s*/?>|\n\*?|/|;|,| and | & ", v):
        p = re.sub(r"\b(interim|acting|co-?coordinator|coordinator|promoted.*|resigned.*|fired.*)\b", "", piece, flags=re.I)
        p = re.sub(r"[^\w.' -]", " ", p)
        p = re.sub(r"\s+", " ", p).strip(" .-'")
        if len(name_key(p).split()) >= 2:
            out.append(p)
    return out


def coordinators_on_page(text):
    """({'offense': [names], 'defense': [names]}, {'offense': raw field text, ...}) from one page."""
    params = infobox_params(text)
    names, raw = {}, {}
    for unit, pattern in UNITS.items():
        fields = [v for k, v in params.items() if re.fullmatch(pattern, k)]
        found = []
        for f in fields:
            for n in field_names(f):
                if name_key(n) not in [name_key(x) for x in found]:
                    found.append(n)
        names[unit] = found
        raw[unit] = " | ".join(fields)[:2000]
    return names, raw


def keys(names):
    return {name_key(n) for n in names}


def is_new(conn, team_id, season, unit, names):
    """T-OCDC rule against last season's row: None if there's no row, False if both are empty, else no name in common."""
    prev = conn.execute(
        "SELECT names FROM coordinators WHERE team_id = %s AND season = %s AND unit = %s",
        (team_id, season - 1, unit),
    ).fetchone()
    if prev is None:
        return None
    if not names and not prev[0]:
        return False
    return not (keys(names) & keys(prev[0]))


def check_unit(conn, team_id, season, unit, names, raw, title):
    """Compare one team-unit with the stored row.  Returns 'added', 'same' or 'pending' (or 'already pending')."""
    row = conn.execute(
        "SELECT names FROM coordinators WHERE team_id = %s AND season = %s AND unit = %s",
        (team_id, season, unit),
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO coordinators (team_id, season, unit, names, is_new, raw_field, source, source_title)
            VALUES (%s, %s, %s, %s, %s, %s, 'wikipedia', %s)
            """,
            (team_id, season, unit, names, is_new(conn, team_id, season, unit, names), raw, title),
        )
        return "added"
    if not (keys(names) - keys(row[0])):
        return "same"              # nothing new listed (a name dropped from the page is not a new coordinator)
    waiting = conn.execute(
        """
        SELECT new_names FROM coordinator_changes
        WHERE team_id = %s AND season = %s AND unit = %s AND status = 'pending'
        """,
        (team_id, season, unit),
    ).fetchall()
    if any(keys(w[0]) == keys(names) for w in waiting):
        return "already pending"
    conn.execute(
        """
        INSERT INTO coordinator_changes (team_id, season, unit, old_names, new_names, source_title, note)
        VALUES (%s, %s, %s, %s, %s, %s, 'found by the coordinator detector')
        """,
        (team_id, season, unit, row[0], names, title),
    )
    return "pending"


def run(season, dry_run=False):
    """Check every FBS team's page once.  Returns how many team-units had each outcome."""
    with connect() as conn:
        teams = conn.execute(FBS_TEAMS_SQL, {"season": season}).fetchall()
    titles = {page_title(season, school, mascot): (team_id, school) for team_id, school, mascot in teams}
    pages = fetch_pages(list(titles))
    counts = {"added": 0, "same": 0, "pending": 0, "already pending": 0, "no page": 0}
    for title, (team_id, school) in titles.items():
        text = pages.get(title)
        if not text:
            counts["no page"] += 1
            print(f"coordinator watch: no page for {school} ({title})")
            continue
        names, raw = coordinators_on_page(text)
        if dry_run:
            print(f"{school:28} OC {', '.join(names['offense']) or '-':40} DC {', '.join(names['defense']) or '-'}")
            continue
        with connect() as conn:
            for unit in UNITS:
                outcome = check_unit(conn, team_id, season, unit, names[unit], raw[unit], title)
                counts[outcome] += 1
                if outcome == "pending":
                    print(f"coordinator watch: {school} {unit}: now lists {', '.join(names[unit])}, waiting for confirmation")
    return counts


if __name__ == "__main__":
    season = int(sys.argv[1])
    print(run(season, dry_run="--dry-run" in sys.argv))
