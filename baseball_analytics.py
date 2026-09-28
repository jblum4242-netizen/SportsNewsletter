import requests
import datetime
from zoneinfo import ZoneInfo

def fetch_mlb_pitcher_data(away_team, home_team):
    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today_date}&hydrate=probablePitcher"
    payload = {
        "string": "TBD vs TBD", "away_pitcher_id": None, "away_pitcher_name": None,
        "home_pitcher_id": None, "home_pitcher_name": None, "away_team_name": None, "home_team_name": None
    }
    
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            dates = res.json().get("dates", [])
            if not dates: return payload
            
            away_mascot = away_team.split()[-1].lower()
            home_mascot = home_team.split()[-1].lower()

            for game in dates[0].get("games", []):
                teams = game.get("teams", {})
                away = teams.get("away", {})
                home = teams.get("home", {})
                away_name = away.get("team", {}).get("name", "")
                home_name = home.get("team", {}).get("name", "")
                
                # Dynamically match the two teams provided by the Odds API
                if away_mascot in away_name.lower() and home_mascot in home_name.lower():
                    away_p = away.get("probablePitcher", {})
                    home_p = home.get("probablePitcher", {})
                    payload["string"] = f"{away_p.get('fullName', 'TBD')} vs {home_p.get('fullName', 'TBD')}"
                    payload["away_pitcher_id"] = away_p.get("id")
                    payload["away_pitcher_name"] = away_p.get("fullName")
                    payload["home_pitcher_id"] = home_p.get("id")
                    payload["home_pitcher_name"] = home_p.get("fullName")
                    payload["away_team_name"] = away_name
                    payload["home_team_name"] = home_name
                    return payload
    except Exception as e: 
        print(f"MLB API Error: {e}")
    return payload

def build_pitcher_logs_html(pitcher_id, pitcher_name, opponent_name):
    if not pitcher_id: return ""
    current_year = datetime.datetime.now().year
    url = f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats?stats=gameLog&group=pitching&season={current_year}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            stats = res.json().get("stats", [])
            if not stats: return ""
            splits = stats[0].get("splits", [])
            if not splits: return ""
            splits.reverse() 
            last_5 = splits[:5]
            last_vs_opp = next((s for s in splits if opponent_name in s.get("opponent", {}).get("name", "")), None)
            
            log_html = f"<div style='margin-top: 15px; font-size: 13px;'><b style='color:#e53e3e;'>⚾ {pitcher_name}</b> - Last 5 Starts:</div>"
            log_html += "<table style='width: 100%; font-size: 11px; border-collapse: collapse; text-align: center; margin-top: 5px; margin-bottom: 10px;'>"
            log_html += "<tr style='background-color: #edf2f7; font-weight: bold;'><td>Date</td><td>Opp</td><td>IP</td><td>H</td><td>ER</td><td>SO</td><td>BB</td></tr>"
            
            def format_row(s):
                date = s.get("date", "")[5:]
                opp = s.get("opponent", {}).get("name", "").split()[-1]
                is_home = s.get("isHome", False)
                opp_display = f"vs {opp}" if is_home else f"@ {opp}"
                st = s.get("stat", {})
                ip = st.get("inningsPitched", "0.0")
                h = st.get("hits", 0)
                er = st.get("earnedRuns", 0)
                so = st.get("strikeOuts", 0)
                bb = st.get("baseOnBalls", 0)
                return f"<tr style='border-bottom: 1px solid #e2e8f0;'><td style='padding: 6px;'>{date}</td><td>{opp_display}</td><td>{ip}</td><td>{h}</td><td>{er}</td><td>{so}</td><td>{bb}</td></tr>"

            for s in last_5: log_html += format_row(s)
            log_html += "</table>"
            if last_vs_opp:
                opp_short = opponent_name.split()[-1]
                log_html += f"<div style='font-size: 12px;'><b style='color:#e53e3e;'>Last vs {opp_short}:</b></div>"
                log_html += "<table style='width: 100%; font-size: 11px; border-collapse: collapse; text-align: center; margin-top: 5px; margin-bottom: 10px;'>"
                log_html += "<tr style='background-color: #edf2f7; font-weight: bold;'><td>Date</td><td>Opp</td><td>IP</td><td>H</td><td>ER</td><td>SO</td><td>BB</td></tr>"
                log_html += format_row(last_vs_opp)
                log_html += "</table>"
            return log_html
    except Exception as e: print(f"Error fetching logs: {e}")
    return ""

def fetch_mlb_7_day_schedule():
    eastern_tz = ZoneInfo("America/New_York")
    now_eastern = datetime.datetime.now(eastern_tz)
    today_str = now_eastern.strftime("%Y-%m-%d")
    next_week_str = (now_eastern + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    
    # Removed teamId=143 so it grabs the entire MLB playoff slate
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={today_str}&endDate={next_week_str}&hydrate=broadcasts"
    
    schedule_list = []
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            dates = res.json().get("dates", [])
            for d in dates:
                for game in d.get("games", []):
                    game_time_raw = game.get("gameDate")
                    utc_dt = datetime.datetime.fromisoformat(game_time_raw.replace("Z", "+00:00"))
                    local_dt = utc_dt.astimezone(eastern_tz)
                    
                    away = game.get("teams", {}).get("away", {}).get("team", {}).get("name", "Unknown")
                    home = game.get("teams", {}).get("home", {}).get("team", {}).get("name", "Unknown")
                    
                    network = ""
                    broadcasts = game.get("broadcasts", [])
                    tv_list = [b.get("name") for b in broadcasts if b.get("isNational") or "NBC Sports" in b.get("name", "")]
                    if tv_list:
                        network = tv_list[0]
                    
                    schedule_list.append({
                        "league": "MLB",
                        "matchup": f"{away} vs. {home}",
                        "time": local_dt.strftime("%I:%M %p ET"),
                        "network": network,
                        "game_datetime": local_dt,
                        "date_header_str": local_dt.strftime("%A, %b %d"),
                        "real_status": "upcoming",
                        "live_feed": None
                    })
    except Exception as e:
        print(f"MLB Schedule Error: {e}")
        
    return schedule_list