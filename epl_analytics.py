import datetime
import json
import os
import re
import sys
import time
from zoneinfo import ZoneInfo
import requests

# In-memory session caches so we never hit the network twice in one run
_EPL_LEAGUE_CACHE = None
_EPL_MATCH_XG_CACHE = None
_FPL_BOOTSTRAP_CACHE = None

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_LEAGUE_CACHE_FILE = os.path.join(_BASE_DIR, "epl_stats_cache.json")
_MATCH_XG_CACHE_FILE = os.path.join(_BASE_DIR, "epl_match_xg_cache.json")

_FOTMOB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def format_epl_name(name):
    """Maps FanDuel/Odds API EPL team names to FotMob's team names."""
    name_map = {
        "Manchester United": "Manchester United",
        "Manchester City": "Manchester City",
        "Crystal Palace": "Crystal Palace",
        "West Ham United": "West Ham",
        "Leeds United": "Leeds",
        "Brighton and Hove Albion": "Brighton",
        "Wolverhampton Wanderers": "Wolverhampton",
        "Tottenham Hotspur": "Tottenham",
        "Nottingham Forest": "Nottingham Forest",
        "Newcastle United": "Newcastle",
        "Newcastle Utd": "Newcastle",
        "Ipswich Town": "Ipswich",
        "Leicester City": "Leicester",
        "Luton Town": "Luton",
    }
    if name in name_map:
        return name_map[name]
    return name.replace(" Hotspur", "").replace(" FC", "").replace("AFC ", "").strip()


def _load_match_xg_cache():
    """Loads the permanent per-match xG cache from disk."""
    global _EPL_MATCH_XG_CACHE
    if _EPL_MATCH_XG_CACHE is not None:
        return _EPL_MATCH_XG_CACHE

    if os.path.exists(_MATCH_XG_CACHE_FILE):
        try:
            with open(_MATCH_XG_CACHE_FILE, "r", encoding="utf-8") as f:
                _EPL_MATCH_XG_CACHE = json.load(f)
                return _EPL_MATCH_XG_CACHE
        except Exception:
            pass

    _EPL_MATCH_XG_CACHE = {}
    return _EPL_MATCH_XG_CACHE


def _save_match_xg_cache():
    """Persists the permanent per-match xG cache to disk."""
    if _EPL_MATCH_XG_CACHE is None:
        return
    try:
        with open(_MATCH_XG_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_EPL_MATCH_XG_CACHE, f)
    except Exception:
        pass


def _extract_xg_from_stats_tree(node):
    """Recursively searches FotMob's match stats JSON for the Expected goals (xG) pair."""
    if isinstance(node, dict):
        key = str(node.get("key", "")).lower()
        title = str(node.get("title", "")).lower()
        if key == "expected_goals" or "expected goals" in title or title == "xg":
            stats = node.get("stats")
            if isinstance(stats, list) and len(stats) >= 2:
                try:
                    return float(stats[0]), float(stats[1])
                except (TypeError, ValueError):
                    pass
        for v in node.values():
            found = _extract_xg_from_stats_tree(v)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _extract_xg_from_stats_tree(item)
            if found is not None:
                return found
    return None


def _get_match_xg(match_obj):
    """Returns (home_xg, away_xg) for a completed FotMob match, using the permanent local cache."""
    match_id = str(match_obj.get("id", "")).strip()
    if not match_id:
        return 0.0, 0.0

    cache = _load_match_xg_cache()
    if match_id in cache:
        cached = cache[match_id]
        return float(cached.get("h", 0.0)), float(cached.get("a", 0.0))

    page_url = match_obj.get("pageUrl", "")
    url = f"https://www.fotmob.com{page_url}" if page_url.startswith("/") else f"https://www.fotmob.com/match/{match_id}"

    try:
        res = requests.get(url, headers=_FOTMOB_HEADERS, timeout=12)
        if res.status_code != 200:
            print(f"⚠️ [EPL] Match {match_id} HTTP {res.status_code} ({url})")
            return 0.0, 0.0

        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', res.text, re.DOTALL)
        if m:
            raw = json.loads(m.group(1))
            page_props = raw.get("props", {}).get("pageProps", {})
            xg_pair = _extract_xg_from_stats_tree(page_props)
            if xg_pair is not None:
                h_xg, a_xg = xg_pair
                cache[match_id] = {"h": h_xg, "a": a_xg}
                _save_match_xg_cache()
                time.sleep(0.25)
                return h_xg, a_xg
            else:
                print(f"⚠️ [EPL] No xG found in __NEXT_DATA__ for match {match_id} (pageProps keys: {list(page_props.keys())})")
    except Exception as e:
        print(f"⚠️ [EPL] Could not fetch match xG for {match_id}: {e}")

    return 0.0, 0.0


def _find_key_recursive(node, target_key):
    """Recursively finds the first non-empty value for target_key inside nested JSON."""
    if isinstance(node, dict):
        if target_key in node and node[target_key]:
            return node[target_key]
        for v in node.values():
            found = _find_key_recursive(v, target_key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_key_recursive(item, target_key)
            if found is not None:
                return found
    return None


def _get_epl_master_data():
    """Fetches ALL EPL xG/xPTS standings & fixtures in ONE request via FotMob's __NEXT_DATA__, with daily JSON caching."""
    global _EPL_LEAGUE_CACHE
    if _EPL_LEAGUE_CACHE is not None:
        return _EPL_LEAGUE_CACHE

    today_str = datetime.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    force_refresh = "--refresh" in sys.argv

    # 1. Check local daily JSON cache first
    cache_data = {}
    if os.path.exists(_LEAGUE_CACHE_FILE):
        try:
            with open(_LEAGUE_CACHE_FILE, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
        except Exception:
            pass

    if not force_refresh and cache_data.get("date") == today_str and cache_data.get("source") == "fotmob" and cache_data.get("data"):
        print("📦 [EPL CACHE] Loaded today's FotMob EPL data from local cache.")
        _EPL_LEAGUE_CACHE = cache_data["data"]
        return _EPL_LEAGUE_CACHE

    # 2. Fetch live from FotMob's Premier League table page (League ID 47)
    url = "https://www.fotmob.com/leagues/47/table/premier-league"
    print("⚽ [EPL] Fetching FotMob Premier League data...")
    try:
        res = requests.get(url, headers=_FOTMOB_HEADERS, timeout=15)
        if res.status_code != 200:
            print(f"⚠️ [EPL] FotMob HTTP {res.status_code}")
        else:
            match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', res.text, re.DOTALL)
            if not match:
                print("⚠️ [EPL] __NEXT_DATA__ tag not found in FotMob HTML.")
            else:
                raw_json = json.loads(match.group(1))
                page_props = raw_json.get("props", {}).get("pageProps", {})

                # Recursively locate the xG standings table (or fallback to standard 'all' table) and fixtures
                xg_rows = _find_key_recursive(page_props, "xg")
                if not isinstance(xg_rows, list):
                    xg_rows = _find_key_recursive(page_props, "all") or []

                all_matches = _find_key_recursive(page_props, "allMatches") or []

                if isinstance(xg_rows, list) and len(xg_rows) > 0:
                    parsed_payload = {"xg_table": xg_rows, "matches": all_matches}
                    _EPL_LEAGUE_CACHE = parsed_payload
                    try:
                        with open(_LEAGUE_CACHE_FILE, "w", encoding="utf-8") as f:
                            json.dump({"date": today_str, "source": "fotmob", "data": parsed_payload}, f)
                        print(f"💾 [EPL CACHE] Saved fresh FotMob EPL metrics for {today_str} ({len(xg_rows)} teams, {len(all_matches)} matches).")
                    except Exception:
                        pass
                    return _EPL_LEAGUE_CACHE
                else:
                    print(f"⚠️ [EPL] Could not locate table rows. pageProps keys: {list(page_props.keys())}")
    except Exception as e:
        print(f"⚠️ [EPL] FotMob connection error: {e}")

    # 3. Fallback to older cached FotMob data if temporarily unreachable
    if cache_data.get("source") == "fotmob" and cache_data.get("data"):
        print("⚠️ [EPL] Live FotMob fetch failed; falling back to last known cached data.")
        _EPL_LEAGUE_CACHE = cache_data["data"]
        return _EPL_LEAGUE_CACHE

    _EPL_LEAGUE_CACHE = {}
    return _EPL_LEAGUE_CACHE


def fetch_epl_xpts_rankings():
    """Calculates EPL xPTS rankings instantly from FotMob's xG table."""
    data = _get_epl_master_data()
    xg_rows = data.get("xg_table", [])
    if not xg_rows:
        return {}

    team_xpts = []
    for row in xg_rows:
        name = (row.get("name") or row.get("shortName") or "").lower().strip()
        xpts = float(row.get("xPoints") or row.get("xpts") or row.get("pts") or 0)
        if name:
            team_xpts.append((name, xpts))

    team_xpts.sort(key=lambda x: x[1], reverse=True)
    return {name: {"rank": str(rank)} for rank, (name, _) in enumerate(team_xpts, 1)}


def fetch_epl_team_metrics(team_name):
    """Returns Points, Expected Points (xPTS), Luck (pts - xpts), and Season xG / xGA from FotMob."""
    data = _get_epl_master_data()
    xg_rows = data.get("xg_table", [])
    if not xg_rows:
        return None

    search_name = format_epl_name(team_name).lower()
    for row in xg_rows:
        title = (row.get("name") or "").lower()
        short_title = (row.get("shortName") or "").lower()
        if search_name in title or title in search_name or (short_title and (search_name in short_title or short_title in search_name)):
            pts = float(row.get("pts", 0))
            xpts = float(row.get("xPoints") or row.get("xpts") or pts)
            xg = float(row.get("xg", 0.0))
            xga = float(row.get("xgConceded") or row.get("xga") or 0.0)
            return {
                "ppda": 0.0,
                "ppda_allowed": 0.0,
                "pts": pts,
                "xpts": xpts,
                "luck": pts - xpts,
                "xg": xg,
                "xga": xga,
                "xg_diff": xg - xga,
            }
    return None


def _parse_fotmob_score(match_obj):
    """Extracts (home_goals, away_goals) from a FotMob fixture object."""
    status = match_obj.get("status", {})
    score_str = status.get("scoreStr") or match_obj.get("score") or ""
    parts = re.findall(r"\d+", str(score_str))
    if len(parts) >= 2:
        return int(parts[0]), int(parts[1])
    return None, None


def _format_fotmob_date(match_obj, include_year=False):
    raw_utc = match_obj.get("status", {}).get("utcTime") or match_obj.get("utcTime") or ""
    if raw_utc:
        try:
            dt = datetime.datetime.fromisoformat(raw_utc.replace("Z", "+00:00"))
            return dt.strftime("%b %d, %Y" if include_year else "%b %d")
        except ValueError:
            pass
    return raw_utc[:10]


def fetch_epl_xg_form(team_name):
    """Extracts last 5 completed matches with per-match xG/xGA (permanently cached by match ID)."""
    data = _get_epl_master_data()
    matches = data.get("matches", [])
    if not matches:
        return []

    search_name = format_epl_name(team_name).lower()
    completed = []
    for m in matches:
        if not m.get("status", {}).get("finished"):
            continue
        h_name = (m.get("home", {}).get("name") or "").lower()
        a_name = (m.get("away", {}).get("name") or "").lower()
        if search_name in h_name or search_name in a_name:
            completed.append(m)

    if not completed:
        return []

    last_5 = completed[-5:][::-1]
    team_results = []

    for match in last_5:
        h_team = match.get("home", {}).get("name", "")
        a_team = match.get("away", {}).get("name", "")
        h_goals, a_goals = _parse_fotmob_score(match)
        if h_goals is None:
            continue

        h_xg, a_xg = _get_match_xg(match)
        is_home = search_name in h_team.lower()

        if is_home:
            opponent, venue = a_team, "H"
            scored, conceded = h_goals, a_goals
            xG, xGA = h_xg, a_xg
        else:
            opponent, venue = h_team, "A"
            scored, conceded = a_goals, h_goals
            xG, xGA = a_xg, h_xg

        result = "W" if scored > conceded else "L" if scored < conceded else "D"
        team_results.append({
            "date": _format_fotmob_date(match),
            "venue": venue,
            "opponent": opponent,
            "result": result,
            "scored": scored,
            "missed": conceded,
            "xG": xG,
            "xGA": xGA,
        })

    return team_results


def fetch_epl_head_to_head(team_a, team_b):
    """Finds completed H2H matches with per-match xG/xGA from FotMob's season fixtures."""
    data = _get_epl_master_data()
    matches = data.get("matches", [])
    if not matches:
        return []

    search_a = format_epl_name(team_a).lower()
    search_b = format_epl_name(team_b).lower()

    h2h_matches = []
    for match in reversed(matches):
        if not match.get("status", {}).get("finished"):
            continue
        h_title = (match.get("home", {}).get("name") or "").lower()
        a_title = (match.get("away", {}).get("name") or "").lower()

        if (search_a in h_title and search_b in a_title) or (search_b in h_title and search_a in a_title):
            h_goals, a_goals = _parse_fotmob_score(match)
            if h_goals is None:
                continue

            h_xg, a_xg = _get_match_xg(match)
            is_team_a_home = search_a in h_title

            if is_team_a_home:
                score_a, score_b = h_goals, a_goals
                xg_a, xg_b = h_xg, a_xg
                venue = f"{team_a} (H) vs {team_b} (A)"
            else:
                score_a, score_b = a_goals, h_goals
                xg_a, xg_b = a_xg, h_xg
                venue = f"{team_a} (A) vs {team_b} (H)"

            h2h_matches.append({
                "date": _format_fotmob_date(match, include_year=True),
                "venue": venue,
                "score_a": score_a,
                "score_b": score_b,
                "xg_a": xg_a,
                "xg_b": xg_b,
                "team_a_name": team_a,
                "team_b_name": team_b,
            })
            if len(h2h_matches) >= 2:
                break

    return h2h_matches


def fetch_epl_injuries(team_name):
    """Fetches FPL bootstrap-static ONCE per run and filters in memory."""
    global _FPL_BOOTSTRAP_CACHE
    fpl_name_map = {
        "Tottenham Hotspur": "Spurs", "Manchester United": "Man Utd", "Manchester City": "Man City",
        "Newcastle United": "Newcastle", "Newcastle Utd": "Newcastle", "Wolverhampton Wanderers": "Wolves",
        "Brighton and Hove Albion": "Brighton", "Nottingham Forest": "Nott'm Forest",
        "Leicester City": "Leicester", "Ipswich Town": "Ipswich", "Hull City": "Hull", "Coventry City": "Coventry"
    }
    fpl_search_name = fpl_name_map.get(team_name, team_name)

    try:
        if _FPL_BOOTSTRAP_CACHE is None:
            url = "https://fantasy.premierleague.com/api/bootstrap-static/"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            _FPL_BOOTSTRAP_CACHE = res.json() if res.status_code == 200 else {}

        if not _FPL_BOOTSTRAP_CACHE:
            return ""

        teams = {t["id"]: t["name"] for t in _FPL_BOOTSTRAP_CACHE.get("teams", [])}
        players = _FPL_BOOTSTRAP_CACHE.get("elements", [])
        injured_players = []

        for player in players:
            status = player.get("status")
            news = player.get("news", "")
            if status in ["i", "d"] or (news and any(w in news.lower() for w in ["injured", "doubt", "suspended"])):
                team_full_name = teams.get(player.get("team"), "")
                if fpl_search_name.lower() in team_full_name.lower():
                    name = f"{player.get('first_name')} {player.get('second_name')}"
                    chance = player.get("chance_of_playing_next_round")
                    chance_str = f" ({chance}% chance)" if chance is not None else ""
                    injured_players.append(f"<li><b>{name}</b>{chance_str}: {news}</li>")

        if not injured_players:
            return ""

        return (
            f"<div style='margin-bottom: 8px; font-size: 11px;'>"
            f"<strong style='color: #c53030;'>🏥 {team_name} Injuries:</strong>"
            f"<ul style='margin: 2px 0 0 15px; padding: 0; color: #4a5568;'>{''.join(injured_players)}</ul></div>"
        )
    except Exception as e:
        print(f"Injury fetch error for {team_name}: {e}")
        return ""


if __name__ == "__main__":
    print("🚀 Testing FotMob EPL Analytics + Per-Match xG Cache...")
    ranks = fetch_epl_xpts_rankings()
    print(f"✅ Loaded xPTS Rankings for {len(ranks)} EPL teams.")
    spurs_metrics = fetch_epl_team_metrics("Tottenham Hotspur")
    print(f"✅ Tottenham Metrics: {spurs_metrics}")
    spurs_form = fetch_epl_xg_form("Tottenham Hotspur")
    print(f"✅ Tottenham Last 5 Matches Found: {len(spurs_form)}")
    for m in spurs_form:
        print(f"   {m['date']} ({m['venue']}) vs {m['opponent']}: {m['result']} {m['scored']}-{m['missed']} | xG: {m['xG']:.2f} - {m['xGA']:.2f}")