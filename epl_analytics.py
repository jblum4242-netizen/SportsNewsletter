import datetime
import json
import os
import sys
from zoneinfo import ZoneInfo
import requests
import pandas as pd

# In-memory session caches so we never hit the network twice in one run
_EPL_LEAGUE_CACHE = None
_FPL_BOOTSTRAP_CACHE = None

def format_understat_name(name):
    """Maps FanDuel/Odds API EPL team names to Understat's exact team titles."""
    name_map = {
        "Manchester United": "Manchester United",
        "Manchester City": "Manchester City",
        "Crystal Palace": "Crystal Palace",
        "West Ham United": "West Ham",
        "Leeds United": "Leeds",
        "Brighton and Hove Albion": "Brighton",
        "Wolverhampton Wanderers": "Wolverhampton Wanderers",
        "Tottenham Hotspur": "Tottenham",
        "Nottingham Forest": "Nottingham Forest",
        "Newcastle United": "Newcastle United",
        "Newcastle Utd": "Newcastle United",
        "Newcastle": "Newcastle United",
        "Ipswich Town": "Ipswich",
        "Leicester City": "Leicester",
        "Luton Town": "Luton",
    }
    if name in name_map:
        return name_map[name]
    return name.replace(" Hotspur", "").replace(" FC", "").replace("AFC ", "").strip()


def _get_epl_master_data():
    """Fetches ALL EPL team & match data in ONE request via Understat's XHR API, with daily JSON caching."""
    global _EPL_LEAGUE_CACHE
    if _EPL_LEAGUE_CACHE is not None:
        return _EPL_LEAGUE_CACHE

    base_dir = os.path.dirname(os.path.abspath(__file__))
    cache_file = os.path.join(base_dir, "epl_stats_cache.json")
    today_str = datetime.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    force_refresh = "--refresh" in sys.argv

    # 1. Check local daily JSON cache first
    cache_data = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
        except Exception:
            pass

    if not force_refresh and cache_data.get("date") == today_str and cache_data.get("data"):
        print("📦 [EPL CACHE] Loaded today's Understat EPL data from local cache.")
        _EPL_LEAGUE_CACHE = cache_data["data"]
        return _EPL_LEAGUE_CACHE

    # 2. Fetch live from Understat's internal XHR endpoint with required 2026 headers
    now = datetime.datetime.now()
    target_season = now.year if now.month >= 8 else now.year - 1

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://understat.com/league/EPL"
    }

    for season in [target_season, target_season - 1]:
        url = f"https://understat.com/getLeagueData/EPL/{season}"
        print(f"⚽ [EPL] Fetching Understat XHR API for {season} season...")
        try:
            # Use cloudscraper if installed to bypass Cloudflare fingerprint checks, else standard requests
            try:
                import cloudscraper
                scraper = cloudscraper.create_scraper()
                res = scraper.get(url, headers=headers, timeout=10)
            except ImportError:
                res = requests.get(url, headers=headers, timeout=10)

            if res.status_code == 200:
                data = res.json()
                if data and data.get("teams"):
                    _EPL_LEAGUE_CACHE = data
                    try:
                        with open(cache_file, "w", encoding="utf-8") as f:
                            json.dump({"date": today_str, "data": data}, f)
                        print(f"💾 [EPL CACHE] Saved fresh Understat EPL metrics for {today_str}.")
                    except Exception:
                        pass
                    return _EPL_LEAGUE_CACHE
        except Exception as e:
            print(f"⚠️ [EPL] Understat connection error for {season}: {e}")

    # 3. Fallback to older cached data if Understat is temporarily unreachable
    if cache_data.get("data"):
        print("⚠️ [EPL] Live Understat fetch failed; falling back to last known cached data.")
        _EPL_LEAGUE_CACHE = cache_data["data"]
        return _EPL_LEAGUE_CACHE

    _EPL_LEAGUE_CACHE = {}
    return _EPL_LEAGUE_CACHE


def fetch_epl_xpts_rankings():
    """Calculates EPL xPTS rankings instantly from the master league payload."""
    data = _get_epl_master_data()
    teams_dict = data.get("teams", {})
    if not teams_dict:
        return {}

    team_xpts = []
    for team_id, t_info in teams_dict.items():
        name = t_info.get("title", "").lower()
        history = t_info.get("history", [])
        total_xpts = sum(float(m.get("xpts", 0)) for m in history)
        team_xpts.append((name, total_xpts))

    team_xpts.sort(key=lambda x: x[1], reverse=True)
    return {name.replace("_", " "): {"rank": str(rank)} for rank, (name, _) in enumerate(team_xpts, 1)}


def fetch_epl_team_metrics(team_name):
    """Calculates season PPDA Pressing & Expected Points Luck directly from the team's history array."""
    data = _get_epl_master_data()
    teams_dict = data.get("teams", {})
    if not teams_dict:
        return None

    search_name = format_understat_name(team_name).lower()
    for _, t_info in teams_dict.items():
        title = t_info.get("title", "").lower()
        if search_name == title or search_name in title or title in search_name:
            history = t_info.get("history", [])
            if not history:
                return None

            pts = sum(float(m.get("pts", 0)) for m in history)
            xpts = sum(float(m.get("xpts", 0.0)) for m in history)
            
            # Aggregate season PPDA from match history
            att_passes = sum(float(m.get("ppda", {}).get("att", 0)) for m in history)
            def_actions = sum(float(m.get("ppda", {}).get("def", 0)) for m in history)
            ppda_ratio = (att_passes / def_actions) if def_actions > 0 else 0.0

            opp_passes = sum(float(m.get("ppda_allowed", {}).get("att", 0)) for m in history)
            opp_def = sum(float(m.get("ppda_allowed", {}).get("def", 0)) for m in history)
            ppda_allowed_ratio = (opp_passes / opp_def) if opp_def > 0 else 0.0

            return {
                "ppda": ppda_ratio,
                "ppda_allowed": ppda_allowed_ratio,
                "pts": pts,
                "xpts": xpts,
                "luck": pts - xpts
            }
    return None


def fetch_epl_xg_form(team_name):
    """Extracts last 5 completed matches for a team from the master 'dates' list."""
    data = _get_epl_master_data()
    dates_list = data.get("dates", [])
    if not dates_list:
        return []

    search_name = format_understat_name(team_name).lower()
    completed = [
        m for m in dates_list
        if m.get("isResult") and (
            search_name in m.get("h", {}).get("title", "").lower() or
            search_name in m.get("a", {}).get("title", "").lower()
        )
    ]

    if not completed:
        return []

    last_5 = completed[-5:][::-1]
    team_results = []

    for match in last_5:
        h_team = match["h"]["title"]
        a_team = match["a"]["title"]
        is_home = search_name in h_team.lower()

        goals = match["goals"]
        xg_data = match["xG"]
        raw_date = match.get("datetime", "")
        try:
            formatted_date = datetime.datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S").strftime("%b %d")
        except ValueError:
            formatted_date = raw_date[:10]

        if is_home:
            opponent, venue = a_team, "H"
            scored, conceded = int(goals["h"]), int(goals["a"])
            xG, xGA = float(xg_data["h"]), float(xg_data["a"])
        else:
            opponent, venue = h_team, "A"
            scored, conceded = int(goals["a"]), int(goals["h"])
            xG, xGA = float(xg_data["a"]), float(xg_data["h"])

        result = "W" if scored > conceded else "L" if scored < conceded else "D"
        team_results.append({
            "date": formatted_date, "venue": venue, "opponent": opponent,
            "result": result, "scored": scored, "missed": conceded,
            "xG": xG, "xGA": xGA
        })

    return team_results


def fetch_epl_head_to_head(team_a, team_b):
    """Finds completed H2H matches from the master 'dates' list without extra API calls."""
    data = _get_epl_master_data()
    dates_list = data.get("dates", [])
    if not dates_list:
        return []

    search_a = format_understat_name(team_a).lower()
    search_b = format_understat_name(team_b).lower()

    h2h_matches = []
    for match in reversed(dates_list):
        if not match.get("isResult"):
            continue
        h_title = match.get("h", {}).get("title", "").lower()
        a_title = match.get("a", {}).get("title", "").lower()

        if (search_a in h_title and search_b in a_title) or (search_b in h_title and search_a in a_title):
            is_team_a_home = search_a in h_title
            goals, xg_data = match["goals"], match["xG"]
            raw_date = match.get("datetime", "")
            try:
                formatted_date = datetime.datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S").strftime("%b %d, %Y")
            except ValueError:
                formatted_date = raw_date[:10]

            if is_team_a_home:
                score_a, score_b = int(goals["h"]), int(goals["a"])
                xg_a, xg_b = float(xg_data["h"]), float(xg_data["a"])
                venue = f"{team_a} (H) vs {team_b} (A)"
            else:
                score_a, score_b = int(goals["a"]), int(goals["h"])
                xg_a, xg_b = float(xg_data["a"]), float(xg_data["h"])
                venue = f"{team_a} (A) vs {team_b} (H)"

            h2h_matches.append({
                "date": formatted_date, "venue": venue,
                "score_a": score_a, "score_b": score_b,
                "xg_a": xg_a, "xg_b": xg_b,
                "team_a_name": team_a, "team_b_name": team_b
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
    print("🚀 Testing new Understat XHR API & Caching...")
    ranks = fetch_epl_xpts_rankings()
    print(f"✅ Loaded xPTS Rankings for {len(ranks)} EPL teams.")
    spurs_form = fetch_epl_xg_form("Tottenham Hotspur")
    spurs_metrics = fetch_epl_team_metrics("Tottenham Hotspur")
    print(f"✅ Tottenham Last 5 Matches Found: {len(spurs_form)}")
    print(f"✅ Tottenham Metrics: {spurs_metrics}")