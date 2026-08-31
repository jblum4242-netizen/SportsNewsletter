import smtplib
import datetime
import re
import requests
import xml.etree.ElementTree as ET
import urllib.parse
from bs4 import BeautifulSoup
import unicodedata
import json
import os
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo
from googlenewsdecoder import gnewsdecoder
import subprocess

from epl_analytics import fetch_epl_xg_form, fetch_epl_head_to_head, fetch_epl_injuries, fetch_epl_team_metrics

# --- PERSONAL DATA CREDENTIALS ---
SENDER_EMAIL = "jblum4242@gmail.com"
SENDER_PASSWORD = "lzygskznkqcejpva"

ODDS_API_KEY = "bd71bd6decf946bca84f130770ad0085"

LEAGUE_MAPPING = {
    "NFL": "americanfootball_nfl",
    "NCAAB": "basketball_ncaab",
    "EPL": "soccer_epl",
    "NCAAF": "americanfootball_ncaaf",
    "NBA": "basketball_nba",
    "NHL": "icehockey_nhl",
    "MLB": "baseball_mlb"
}

# --- NEW: Master ESPN API Routing Map ---
ESPN_SPORT_MAP = {
    "nba": "basketball/nba", 
    "nhl": "hockey/nhl", 
    "mlb": "baseball/mlb", 
    "nfl": "football/nfl",
    "epl": "soccer/eng.1"
}


# Master List of Power Conference Schools
POWER_CONFERENCE_SCHOOLS = [
    "Alabama", "Arkansas", "Auburn", "Florida", "Georgia", "Kentucky", "LSU", "Ole Miss", "Mississippi State", "Missouri", "Oklahoma", "South Carolina", "Tennessee", "Texas", "Texas A&M", "Vanderbilt",
    "Illinois", "Indiana", "Iowa", "Maryland", "Michigan", "Michigan State", "Minnesota", "Nebraska", "Northwestern", "Ohio State", "Oregon", "Penn State", "Purdue", "Rutgers", "UCLA", "USC", "Washington", "Wisconsin",
    "Boston College", "California", "Clemson", "Duke", "Florida State", "Georgia Tech", "Louisville", "Miami", "North Carolina", "NC State", "Pittsburgh", "SMU", "Stanford", "Syracuse", "Virginia", "Virginia Tech", "Wake Forest",
    "Arizona", "Arizona State", "Baylor", "BYU", "Cincinnati", "Colorado", "Houston", "Iowa State", "Kansas", "Kansas State", "Oklahoma State", "TCU", "Texas Tech", "UCF", "Utah", "West Virginia"
]

BIG_EAST_HOOPS = [
    "Butler", "UConn", "Connecticut", "Creighton", "DePaul", "Georgetown", "Marquette", "Providence", "St. John's", "Seton Hall", "Villanova", "Xavier"
]

def fetch_live_odds_clean(sport_key):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": ODDS_API_KEY, 
        "regions": "us", 
        "markets": "h2h,spreads", 
        "bookmakers": "fanduel,draftkings,betmgm,caesars", 
        "oddsFormat": "american"
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        # Check quota remaining in response headers
        remaining = res.headers.get("x-requests-remaining")
        if remaining:
            print(f"📊 Odds API quota remaining: {remaining}")
        if res.status_code == 200:
            return res.json()
        else:
            print(f"⚠️ Odds API Error [{sport_key}]: HTTP {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Odds API Connection Error: {e}")
    return []

def get_direct_article_url(google_url):
    """Uses the dedicated decoder package to bypass Google's encrypted tokens, with a polite delay."""
    if not google_url.startswith("https://news.google.com"):
        return google_url
        
    try:
        time.sleep(0.5)
        result = gnewsdecoder(google_url)
        if result.get("status"):
            return result["decoded_url"]
        else:
            print(f"Decoder failed (Rate Limited?): {result.get('message', 'Unknown error')}")
    except Exception as e:
        print(f"Decoder error: {e}")
        
    return google_url
        
def fetch_team_news(search_query, max_articles=3):
    """Fetches news links using Google News RSS, strictly filtering for recency with a fallback."""
    encoded_query = urllib.parse.quote(search_query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    
    # --- UPGRADE: Use a full, modern browser User-Agent to avoid getting flagged as a bot ---
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    articles = []
    fallback_articles = []  # --- STEP 1: Fallback list created ---
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for item in root.findall('./channel/item'):
                title = item.find('title').text
                
                # --- STEP 2: Title cleaning & filtering ---
                title_lower = title.lower()
                generic_phrases = ["official site of the national football league", "nfl.com", "espn", "yahoo sports"]
                if any(bad in title_lower for bad in generic_phrases):
                    continue
                    
                if " - " in title:
                    title = " - ".join(title.split(" - ")[:-1])
                    
                raw_link = item.find('link').text 
                direct_link = get_direct_article_url(raw_link)
                article_obj = {'title': title, 'link': direct_link}
                
                # Always save top valid stories to fallback list
                if len(fallback_articles) < max_articles:
                    fallback_articles.append(article_obj)

                # --- STEP 3: Check age for primary list ---
                pub_date_str = item.find('pubDate').text
                try:
                    pub_dt = datetime.datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=datetime.timezone.utc)
                    age_hours = (now_utc - pub_dt).total_seconds() / 3600
                except:
                    age_hours = 0
                
                # Strict age limit for primary selection
                if age_hours > 72:
                    continue
                    
                articles.append(article_obj)
                
                if len(articles) == max_articles:
                    break
        else:
            # --- UPGRADE: Catch non-200 responses so it doesn't fail silently ---
            print(f"⚠️ HTTP {res.status_code} Error: Google News blocked the request for '{search_query}'.")
            
    except Exception as e:
        print(f"Google Team News Error for {search_query}: {e}")
        
    # --- STEP 4: Fallback check right before returning ---
    if not articles and fallback_articles:
        print(f"ℹ️ No stories within age limit for '{search_query}'. Returning top RSS fallback articles.")
        return fallback_articles
        
    return articles


def fetch_covers_consensus(league):
    consensus_list = []
    league_str = league.lower()
    url = rf'https://contests.covers.com/consensus/topconsensus/{league_str}/overall'
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    matchup_text = cols[0].get_text(separator=" ", strip=True) 
                    consensus_text = cols[2].get_text(separator=" ", strip=True) 
                    tokens = matchup_text.split()
                    percents = consensus_text.replace("%", "").split()
                    if len(tokens) >= 3 and len(percents) >= 2:
                        consensus_list.append({
                            "away_abbr": tokens[1].lower(),
                            "home_abbr": tokens[2].lower(),
                            "away_pct": f"{percents[0]}%",
                            "home_pct": f"{percents[1]}%"
                        })
    except Exception as e:
        print(f"Covers Scraping Error: {e}")
    return consensus_list

def fetch_covers_injuries(team_name, league):
    league_upper = league.upper()
    
    if "NBA" in league_upper:
        sport, lg = "basketball", "nba"
    elif "MLB" in league_upper:
        sport, lg = "baseball", "mlb"
    elif "NHL" in league_upper:
        sport, lg = "hockey", "nhl"
    else:
        return []

    slug = team_name.lower().replace(" ", "-")
    url = f"https://www.covers.com/sport/{sport}/{lg}/teams/main/{slug}/injuries"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    injuries = []
    time.sleep(0.5) 
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            table = soup.find('table')
            
            if table:
                rows = table.find_all('tr')[1:] 
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 3:  
                        player = cols[0].text.strip()
                        pos = cols[1].text.strip()
                        status_raw = cols[2].text.strip()
                        status_lines = [line.strip() for line in status_raw.split('\n') if line.strip()]
                        status_clean = status_lines[0] if status_lines else status_raw
                        status_clean = status_clean.rstrip('(').strip()
                        date_found = ""
                        months_abbrev = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                        
                        for cell in cols:
                            for line in cell.text.split('\n'):
                                line_str = line.strip()
                                if any(m in line_str for m in months_abbrev) and len(line_str) < 25:
                                    date_found = line_str.strip('() ')
                                    break
                            if date_found:
                                break
                                
                        if not date_found:
                            date_found = "Reported"
                        
                        injuries.append({"player": player, "pos": pos, "status": status_clean, "date": date_found})
    except Exception as e:
        print(f"Covers Scraping Error for {team_name}: {e}")
        
    return injuries

def get_live_espn_score(league_name, matchup_str):
    sport_path = ESPN_SPORT_MAP.get(league_name.lower())
    if not sport_path or not matchup_str: return None, "upcoming"
        
    try:
        data = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard", timeout=4).json()
        matchup_lower = matchup_str.lower()
        for event in data.get('events', []):
            if any(team['team']['displayName'].lower() in matchup_lower for team in event['competitions'][0]['competitors']):
                comp = event['competitions'][0]
                espn_state = event['status']['type']['state']
                state_map = {"pre": "upcoming", "in": "in_progress", "post": "completed"}
                derived_status = state_map.get(espn_state, "upcoming")
                detail = event['status']['type']['detail']
                t1, t2 = comp['competitors'][0], comp['competitors'][1]
                score_str = f"🔥 {detail}: {t2['team']['abbreviation']} {t2['score']} @ {t1['team']['abbreviation']} {t1['score']}"
                return score_str, derived_status
    except: pass
    return None, "upcoming"

def fetch_game_previews(away_team, home_team, max_articles=3):
    encoded_query = urllib.parse.quote(f"{away_team} {home_team} game preview")
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    articles = []
    clickbait_phrases = ["how to watch", "where to watch", "what channel", "what time is", "tv schedule"]
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for item in root.findall('./channel/item'):
                title = item.find('title').text
                title_lower = title.lower()
                
                if any(bad in title_lower for bad in clickbait_phrases):
                    continue
                    
                if " - " in title:
                    title = " - ".join(title.split(" - ")[:-1])
                    
                raw_link = item.find('link').text
                direct_link = get_direct_article_url(raw_link)
                
                articles.append({'title': title, 'link': direct_link})
                
                if len(articles) == max_articles:
                    break
    except Exception as e:
        print(f"Google News Fetch Error: {e}")
        
    return articles

def fetch_tv_networks(league):
    sport_path = ESPN_SPORT_MAP.get(league.lower())
    tv_map = {}
    
    if not sport_path: 
        return tv_map
        
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard"
    
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for event in data.get('events', []):
                try:
                    competitors = event['competitions'][0]['competitors']
                    team_a = competitors[0]['team']['name'].lower()
                    team_b = competitors[1]['team']['name'].lower()
                    broadcasts = event['competitions'][0].get('broadcasts', [])
                    networks = []
                    for b in broadcasts:
                        names = b.get('names', [])
                        networks.extend(names)
                    if networks:
                        network_str = ", ".join(networks)
                        tv_map[f"{team_a} vs {team_b}"] = network_str
                except: continue 
    except Exception as e: print(f"ESPN TV API Error: {e}")
    return tv_map

def fetch_mlb_pitcher_data():
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
            for game in dates[0].get("games", []):
                teams = game.get("teams", {})
                away = teams.get("away", {})
                home = teams.get("home", {})
                away_name = away.get("team", {}).get("name", "")
                home_name = home.get("team", {}).get("name", "")
                if "Phillies" in away_name or "Phillies" in home_name:
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
    except Exception as e: print(f"MLB API Error: {e}")
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

def filter_ncaaf_games(odds_games):
    """Filters NCAAF games to strictly include Top 25 matchups and Delaware."""
    url = "http://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
    
    top_25_teams = set()
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for event in data.get('events', []):
                for comp in event.get('competitions', []):
                    for competitor in comp.get('competitors', []):
                        # Only add teams that actually have a Top 25 rank in ESPN's data
                        cur_rank = competitor.get('curatedRank', {}).get('current', 99)
                        if 1 <= cur_rank <= 25:
                            team = competitor.get('team', {})
                            # Store full display name and exact location/nickname
                            if 'displayName' in team:
                                top_25_teams.add(team['displayName'].lower())
                            if 'location' in team and 'nickname' in team:
                                top_25_teams.add(f"{team['location']} {team['nickname']}".lower())
    except Exception as e:
        print(f"⚠️ Could not fetch Top 25 CFB teams: {e}")

    filtered_games = []
    
    for game in odds_games:
        matchup = game.get('matchup', '')
        if ' vs. ' not in matchup:
            continue
            
        away, home = matchup.split(' vs. ')
        away_clean = away.lower().strip()
        home_clean = home.lower().strip()
        
        # 1. ALWAYS include University of Delaware
        if "delaware" in away_clean or "delaware" in home_clean:
            filtered_games.append(game)
            continue
            
        # 2. Match against full team names rather than broad partial words
        is_top_25 = False
        for top_team in top_25_teams:
            if top_team in away_clean or top_team in home_clean or away_clean in top_team or home_clean in top_team:
                is_top_25 = True
                break
                
        if is_top_25:
            filtered_games.append(game)
            
    return filtered_games if filtered_games else odds_games


def fetch_last_5_games(team_name, league):
    league_str = league.lower()
    if league_str == "nba": sport = "basketball"
    elif league_str == "nhl": sport = "hockey"
    else: sport = "baseball"
        
    normalized_name = unicodedata.normalize('NFKD', team_name).encode('ASCII', 'ignore').decode('utf-8')
    team_slug = normalized_name.lower().replace(" ", "-").replace(".", "")
    
    url = f"https://www.covers.com/sport/{sport}/{league_str}/teams/main/{team_slug}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    last_5 = []
    time.sleep(0.5)
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            tables = soup.find_all('table')
            past_results_table = None
            
            for tbl in tables:
                headers_text = [th.text.strip().upper() for th in tbl.find_all('th') if th.text]
                if 'SCORE' in headers_text and ('ATS' in headers_text or 'ML' in headers_text) and 'O/U' in headers_text:
                    past_results_table = tbl
                    break
                    
            if past_results_table:
                rows = past_results_table.find_all('tr')[1:] 
                for row in rows:
                    cols = row.find_all('td')
                    
                    if len(cols) >= 5:
                        raw_date = cols[0].text.strip()
                        if " @ " in raw_date: date_str = raw_date.split(" @ ")[0].strip()
                        elif " vs " in raw_date: date_str = raw_date.split(" vs ")[0].strip()
                        else: date_str = " ".join(raw_date.split()[:2])
                        
                        opponent = cols[1].text.strip()
                        result = cols[2].text.strip()
                        ats = cols[3].text.strip()
                        ou = cols[4].text.strip()
                        
                        last_5.append({"date": date_str, "opp": opponent, "result": result, "ats": ats, "ou": ou})
                        
                        if len(last_5) == 5:
                            break
    except Exception as e:
        print(f"Last 5 Games Scraping Error for {team_name}: {e}")
        
    return last_5

def build_last_5_html(team_name, last_5_data):
    if not last_5_data: return f"<div style='margin-bottom: 8px;'><span style='color: #a0aec0; font-size: 11px;'>No recent data available for {team_name}.</span></div>"
    html = f"<div style='margin-top: 10px; margin-bottom: 10px;'>"
    html += f"<strong style='font-size: 12px; color: #2d3748;'>{team_name} - Last 5:</strong>"
    html += f"<table style='width: 100%; font-size: 11px; text-align: left; border-collapse: collapse; margin-top: 4px;'>"
    html += f"<tr style='background-color: #edf2f7; color: #4a5568;'> <th style='padding: 3px;'>Date</th> <th style='padding: 3px;'>Opp</th> <th style='padding: 3px;'>Score</th> <th style='padding: 3px;'>ATS / ML</th> <th style='padding: 3px;'>O/U</th> </tr>"
    for game in last_5_data:
        html += f"<tr style='border-bottom: 1px solid #e2e8f0;'>"
        html += f"<td style='padding: 3px;'>{game['date']}</td>"
        html += f"<td style='padding: 3px;'>{game['opp']}</td>"
        html += f"<td style='padding: 3px;'>{game['result']}</td>"
        ats_color = "#38a169" if "W" in game['ats'] else "#e53e3e" if "L" in game['ats'] else "#718096"
        html += f"<td style='padding: 3px; color: {ats_color}; font-weight: bold;'>{game['ats']}</td>"
        html += f"<td style='padding: 3px;'>{game['ou']}</td>"
        html += f"</tr>"
    html += "</table></div>"
    return html

def build_xg_form_html(team_name, xg_data, metrics=None):
    if not xg_data:
        return f"<div style='margin-bottom: 8px;'><span style='color: #a0aec0; font-size: 11px;'>No advanced xG data available for {team_name}.</span></div>"
        
    wins = sum(1 for m in xg_data if m['result'].upper() == 'W')
    draws = sum(1 for m in xg_data if m['result'].upper() == 'D')
    losses = sum(1 for m in xg_data if m['result'].upper() == 'L')
    record_str = f" [Record: {wins}-{draws}-{losses}]"
    
    # Optional KenPom badge if metrics are passed
    metrics_str = ""
    if metrics:
        luck_color = "#38a169" if metrics['luck'] >= 0 else "#e53e3e"
        metrics_str = f" | <span style='font-size: 10px; color: #4a5568;'>PPDA Press: <b>{metrics['ppda']:.1f}</b> | xPts Luck: <b style='color: {luck_color};'>{metrics['luck']:+.1f}</b></span>"
        
    html = f"<div style='margin-top: 10px; margin-bottom: 10px;'>"
    html += f"<strong style='font-size: 12px; color: #2d3748;'>{team_name} - Last 5 (Advanced xG):</strong><span style='font-size: 11px; color: #718096; font-weight: bold;'>{record_str}</span>{metrics_str}"
    html += f"<table style='width: 100%; font-size: 11px; text-align: left; border-collapse: collapse; margin-top: 4px;'>"
    html += f"<tr style='background-color: #e6fffa; color: #234e52;'> <th style='padding: 3px;'>Date</th> <th style='padding: 3px;'>Venue</th> <th style='padding: 3px;'>Opp</th> <th style='padding: 3px;'>Result</th> <th style='padding: 3px;'>Score</th> <th style='padding: 3px;'>xG</th> <th style='padding: 3px;'>xGA</th> </tr>"
    
    total_xg = 0.0
    total_xga = 0.0
    count = len(xg_data)
    
    for match in xg_data:
        xg = float(match['xG'])
        xga = float(match['xGA'])
        total_xg += xg
        total_xga += xga
        
        html += f"<tr style='border-bottom: 1px solid #e2e8f0;'>"
        html += f"<td style='padding: 3px;'>{match['date']}</td>"
        html += f"<td style='padding: 3px; font-weight: bold;'>{match['venue']}</td>"
        html += f"<td style='padding: 3px;'>{match['opponent']}</td>"
        
        res = match['result'].upper()
        res_color = "#38a169" if res == "W" else "#e53e3e" if res == "L" else "#718096"
        html += f"<td style='padding: 3px; color: {res_color}; font-weight: bold;'>{res}</td>"
        
        html += f"<td style='padding: 3px;'>{match['scored']}-{match['missed']}</td>"
        
        xg_color = "#38a169" if xg > xga else "#e53e3e"
        html += f"<td style='padding: 3px; font-weight: bold; color: {xg_color};'>{xg:.2f}</td>"
        html += f"<td style='padding: 3px;'>{xga:.2f}</td>"
        html += f"</tr>"
        
    avg_xg = total_xg / count if count > 0 else 0.0
    avg_xga = total_xga / count if count > 0 else 0.0
    net_diff = avg_xg - avg_xga
    net_color = "#38a169" if net_diff >= 0 else "#e53e3e"
    net_str = f"+{net_diff:.2f}" if net_diff > 0 else f"{net_diff:.2f}"
    
    html += f"<tr style='background-color: #f7fafc; font-weight: bold; border-top: 2px solid #cbd5e0;'>"
    html += f"<td colspan='3' style='padding: 4px; color: #4a5568;'>Last 5 Averages (Net: <span style='color: {net_color};'>{net_str}</span>):</td>"
    html += f"<td colspan='2' style='padding: 4px;'></td>"
    html += f"<td style='padding: 4px; color: #2b6cb0;'>{avg_xg:.2f}</td>"
    html += f"<td style='padding: 4px; color: #c53030;'>{avg_xga:.2f}</td>"
    html += f"</tr>"
    
    html += "</table></div>"
    return html


def build_h2h_html(h2h_data):
    if not h2h_data:
        return ""
        
    html = f"<div style='margin-top: 10px; margin-bottom: 12px;'>"
    html += f"<strong style='font-size: 12px; color: #2d3748;'>Last 2 Head-to-Head Meetings:</strong>"
    html += f"<table style='width: 100%; font-size: 11px; text-align: left; border-collapse: collapse; margin-top: 4px;'>"
    html += f"<tr style='background-color: #edf2f7; color: #2d3748;'> <th style='padding: 3px;'>Date</th> <th style='padding: 3px;'>Matchup</th> <th style='padding: 3px;'>Score</th> <th style='padding: 3px;'>xG Split</th> </tr>"
    
    for match in h2h_data:
        html += f"<tr style='border-bottom: 1px solid #e2e8f0;'>"
        html += f"<td style='padding: 3px;'>{match['date']}</td>"
        html += f"<td style='padding: 3px; font-weight: bold;'>{match['venue']}</td>"
        html += f"<td style='padding: 3px;'>{match['score_a']} - {match['score_b']}</td>"
        html += f"<td style='padding: 3px;'>{match['xg_a']:.2f} - {match['xg_b']:.2f}</td>"
        html += f"</tr>"
        
    html += "</table></div>"
    return html

def build_injury_table_html(team_name, injury_data):
    if not injury_data: return ""
    html = f"<div style='margin-top: 10px; margin-bottom: 10px; font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Arial, sans-serif;'>"
    html += f"<strong style='font-size: 12px; color: #e53e3e;'>📋 {team_name} Injuries:</strong>"
    html += f"<table style='width: 100%; font-size: 11px; text-align: left; border-collapse: collapse; margin-top: 4px;'>"
    html += (f"<tr style='background-color: #fff5f5; color: #c53030; font-weight: bold;'>"
             f"  <th style='padding: 4px 3px; border-bottom: 1px solid #fed7d7;'>Player</th>"
             f"  <th style='padding: 4px 3px; border-bottom: 1px solid #fed7d7;'>POS</th>"
             f"  <th style='padding: 4px 3px; border-bottom: 1px solid #fed7d7;'>Status</th>"
             f"  <th style='padding: 4px 3px; border-bottom: 1px solid #fed7d7;'>Date</th></tr>")
    for inj in injury_data:
        player = inj.get('player', 'Unknown Player')
        pos = inj.get('pos', '-') 
        status = inj.get('status', 'No details')
        date = inj.get('date', 'Reported')
        html += f"<tr style='border-bottom: 1px solid #e2e8f0; background-color: #ffffff;'>"
        html += f"  <td style='padding: 5px 3px; color: #2d3748; font-weight: bold;'>{player}</td>"
        html += f"  <td style='padding: 5px 3px; color: #4a5568;'>{pos}</td>"
        html += f"  <td style='padding: 5px 3px; color: #4a5568;'>{status}</td>"
        html += f"  <td style='padding: 5px 3px; color: #718096;'>{date}</td></tr>"
    html += "</table></div>"
    return html

def is_subsequence(abbrev, full_string):
    it = iter(full_string.lower())
    return all(c in it for c in abbrev.lower())

def parse_game_metrics(games, covers_data, tv_data, league):
    parsed_games = []
    if not games or not isinstance(games, list): return parsed_games

    eastern_tz = ZoneInfo("America/New_York")
    now_eastern = datetime.datetime.now(eastern_tz)
    today_date = now_eastern.date()
    
    future_limit = now_eastern + datetime.timedelta(days=7)
        
    for game in games:
        home_team = game.get("home_team", "Home Team")
        away_team = game.get("away_team", "Away Team")
        is_philly = any(p in home_team or p in away_team for p in ["Phili", "76ers", "Phillies", "Flyers"])
        is_phillies_game = any("Philli" in t for t in [home_team, away_team])
        
        pitcher_string = "TBD vs TBD"
        pitcher_logs_html = ""
        
        commence_time_raw = game.get("commence_time")
        formatted_date = datetime.date.today().strftime("%A, %b %d")
        formatted_time = "TBD"
        local_dt_safe = now_eastern 
        
        if commence_time_raw:
            try:
                utc_dt = datetime.datetime.fromisoformat(commence_time_raw.replace("Z", "+00:00"))
                local_dt = utc_dt.astimezone(eastern_tz)
                local_dt_safe = local_dt
                
                if local_dt > future_limit:
                    continue 
                    
                if local_dt.date() != today_date and league.upper() not in ["NFL", "NCAAB", "NCAAF", "EPL"]: 
                    continue  
                
                formatted_date = local_dt.strftime("%A, %b %d")
                formatted_time = local_dt.strftime("%I:%M %p ET")
            except: 
                formatted_time = "Live / Ongoing"
            
        away_pitcher_logs_html = ""
        home_pitcher_logs_html = ""
        if "MLB" in league.upper():
            p_data = fetch_mlb_pitcher_data()
            pitcher_string = p_data["string"]
            away_pitcher_logs_html = build_pitcher_logs_html(p_data["away_pitcher_id"], p_data["away_pitcher_name"], p_data["home_team_name"])
            home_pitcher_logs_html = build_pitcher_logs_html(p_data["home_pitcher_id"], p_data["home_pitcher_name"], p_data["away_team_name"])

        away_cov, home_cov = "50%", "50%"
        for game_split in covers_data:
            if is_subsequence(game_split["away_abbr"], away_team) and is_subsequence(game_split["home_abbr"], home_team):
                away_cov = game_split["away_pct"]
                home_cov = game_split["home_pct"]
                break
            elif is_subsequence(game_split["home_abbr"], away_team) and is_subsequence(game_split["away_abbr"], home_team):
                away_cov = game_split["home_pct"]
                home_cov = game_split["away_pct"]
                break
                
        away_inj_list = fetch_covers_injuries(away_team, league)
        home_inj_list = fetch_covers_injuries(home_team, league)
        away_inj_html = build_injury_table_html(away_team, away_inj_list)
        home_inj_html = build_injury_table_html(home_team, home_inj_list)
        combined_injury_html = away_inj_html + home_inj_html
        if not combined_injury_html:
            combined_injury_html = "<div style='margin-bottom: 10px;'><span style='color: #a0aec0; font-size: 11px;'>No injuries reported.</span></div>"

        network_str = ""
        away_mascot = away_team.split()[-1].lower()
        home_mascot = home_team.split()[-1].lower()
        for t_matchup, net in tv_data.items():
            if away_mascot in t_matchup and home_mascot in t_matchup:
                network_str = net
                break
            
        bookmakers = game.get("bookmakers", [])
        any_book = next((b for b in bookmakers if b.get("key") == "fanduel"), bookmakers[0] if bookmakers else None)
        odds_str = "Lines Off Board"
        if any_book and any_book.get("markets"):
            for market in any_book["markets"]:
                outcomes = market.get("outcomes", [])
                if len(outcomes) >= 2:
                    # Find home/away/draw lines safely without crashing if names mismatch slightly
                    away_line = next((o for o in outcomes if o.get("name") == away_team), None)
                    home_line = next((o for o in outcomes if o.get("name") == home_team), None)
                    draw_line = next((o for o in outcomes if o.get("name", "").lower() in ["draw", "tie"]), None)
                    
                    # Fallback extractions if exact match fails
                    a_disp = f"{away_line.get('name')} ({away_line.get('price')})" if away_line else f"{away_team}"
                    h_disp = f"{home_line.get('name')} ({home_line.get('price')})" if home_line else f"{home_team}"
                    
                    if market.get("key") == "spreads":
                        a_point = f" {away_line.get('point', '')}" if (away_line and away_line.get('point')) else ""
                        h_point = f" {home_line.get('point', '')}" if (home_line and home_line.get('point')) else ""
                        odds_str = f"[{any_book['title']}] {away_line.get('name')}{a_point} ({away_line.get('price')}) | {home_line.get('name')}{h_point} ({home_line.get('price')})"
                        break
                        
                    elif market.get("key") == "h2h" and odds_str == "Lines Off Board":
                        if draw_line:
                            # Beautifully inject the Draw option right into the standard moneyline format!
                            odds_str = f"[{any_book['title']}] {a_disp} | {h_disp} | Draw ({draw_line.get('price')})"
                        else:
                            odds_str = f"[{any_book['title']}] {a_disp} | {h_disp}"

        articles = fetch_game_previews(away_team, home_team)
        query_away = away_team.replace(" ", "+")
        query_home = home_team.replace(" ", "+")
        google_search_url = f"https://www.google.com/search?q={query_away}+vs+{query_home}+news&tbm=nws"
        
        filtered_articles = []
        if articles:
            clickbait_phrases = ["how to watch", "where to watch", "what channel", "what time is", "tv schedule"]
            for art in articles:
                title_lower = art['title'].lower()
                if not any(bad in title_lower for bad in clickbait_phrases):
                    filtered_articles.append(art)
                    
        filtered_articles = filtered_articles[:3]
        if filtered_articles:
            news_html = "<ul style='margin: 0; padding-left: 20px;'>"
            for art in filtered_articles:
                display_title = art['title'][:75] + '...' if len(art['title']) > 75 else art['title']
                news_html += f"<li style='margin-bottom: 6px;'><a href='{art['link']}' target='_blank' style='color: #2b6cb0; text-decoration: none; font-size: 12px;'>{display_title}</a></li>"
            news_html += "</ul>"
            news_html += f"<div style='margin-top: 5px; font-size: 11px;'><a href='{google_search_url}' target='_blank' style='color: #4a5568;'>↳ Search all news for this matchup</a></div>"
        else:
            news_html = f"<span style='color: #a0aec0; font-size: 12px;'>No previews available. <a href='{google_search_url}' target='_blank' style='color: #2b6cb0;'>Search Google</a></span>"

        parsed_games.append({
            "matchup": f"{away_team} vs. {home_team}",
            "commence_time": commence_time_raw,
            "game_datetime": local_dt_safe,
            "league": league, 
            "odds": odds_str,
            "covers": f"{away_team} ({away_cov}) | {home_team} ({home_cov})",
            "philly_priority": is_philly,
            "is_phillies": is_phillies_game,
            "game_date": formatted_date,
            "tv_info": formatted_time,
            "network": network_str,
            "pitchers": pitcher_string,
            "away_pitcher_logs": away_pitcher_logs_html,
            "home_pitcher_logs": home_pitcher_logs_html,
            "injury_html": combined_injury_html,
            "news_html": news_html 
        })
        
    return sorted(parsed_games, key=lambda x: x.get('commence_time', ''))
        
def format_consensus(consensus_str):
    try:
        parts = consensus_str.split("|")
        formatted_parts = []
        for part in parts:
            match = re.search(r"\((\d+)%\)", part)
            if match and int(match.group(1)) >= 75:
                styled_part = f'<span style="color:#e53e3e; font-weight:900; background-color:#ffebeb; border:1px solid #fc8181; padding:2px 6px; border-radius:4px;">🔥 {part.strip()}</span>'
                formatted_parts.append(styled_part)
            else:
                formatted_parts.append(part.strip())
        return " | ".join(formatted_parts)
    except: 
        return consensus_str

##Dynamic HTML Block

def build_dynamic_html():
    eastern_tz = ZoneInfo("America/New_York")
    now_eastern = datetime.datetime.now(eastern_tz)
    
    # ---------------------------------------------------------
    # SMART 24-HOUR CACHE & PRE-COMPILING GAME SLATES 
    # ---------------------------------------------------------
    # Updated to 7 days to capture full weekends
    future_limit = now_eastern + datetime.timedelta(days=7)
    league_slates = {} 
    
    cache_file = "C:\\Users\\jblum\\Python\\SportsNewsletter\\raw_odds_cache.json"
    cached_raw_odds = {}
    cache_is_fresh = False

    if os.path.exists(cache_file):
        try:
            file_age_hours = (time.time() - os.path.getmtime(cache_file)) / 3600
            if file_age_hours < 12:
                with open(cache_file, 'r') as f:
                    cached_raw_odds = json.load(f)
                cache_is_fresh = True
                print(f"📦 [CACHE] Cache file loaded successfully (Age: {file_age_hours:.1f} hrs).")
        except Exception as e:
            print(f"Cache Read Error: {e}")
    
    for league, api_key in LEAGUE_MAPPING.items():
        covers_data = fetch_covers_consensus(league)
        tv_data = fetch_tv_networks(league)
        
        if cache_is_fresh and league in cached_raw_odds:
            raw_odds = cached_raw_odds[league]
            print(f"📦 [CACHE] Using cached odds for {league}.")
        else:
            print(f"🌐 [LIVE] Fetching fresh odds for {league}...")
            raw_odds = fetch_live_odds_clean(api_key)
            cached_raw_odds[league] = raw_odds
        
        parsed_games = parse_game_metrics(raw_odds, covers_data, tv_data, league)
            
        final_display_list = []
        if "MLB" in league.upper():
            final_display_list = [g for g in parsed_games if "Philli" in g.get('matchup', '')]
        elif league.upper() == "NCAAF":
            top_25_and_delaware = filter_ncaaf_games(parsed_games)
            for g in top_25_and_delaware:
                game_time = g.get('game_datetime') 
                if game_time and game_time <= future_limit:
                    final_display_list.append(g)
        elif league.upper() in ["NFL", "NCAAB", "EPL"]:
            for g in parsed_games:
                game_time = g.get('game_datetime') 
                if game_time and game_time <= future_limit:
                    if league.upper() == "NCAAB":
                        away_team, home_team = g['matchup'].split(' vs. ')
                        valid_schools = [s.upper() for s in POWER_CONFERENCE_SCHOOLS] + [s.upper() for s in BIG_EAST_HOOPS]
                        if any(s in away_team.upper() or s in home_team.upper() for s in valid_schools):
                            final_display_list.append(g)
                    else:
                        final_display_list.append(g)
        else:
            final_display_list = parsed_games[:5]
            
        league_slates[league] = final_display_list

    try:
        with open(cache_file, 'w') as f:
            json.dump(cached_raw_odds, f)
    except Exception as e:
        print(f"Cache Write Error: {e}")

    # ---------------------------------------------------------
    # 1. BUILD FAVORITE TEAMS HTML (Tab: News)
    # ---------------------------------------------------------
    FAVORITE_TEAMS = {
        "Philadelphia Eagles": 'Philadelphia Eagles News',
        "Delaware Blue Hens": 'Delaware Blue Hens Football News',
        "UCLA Bruins men's basketball": "UCLA Bruins Men's Basketball News",
        "Tottenham Hotspur": 'Tottenham Hotspur News'
    }
    
    news_html = "<div id='tab-news' class='tab-content'>"
    news_html += f"<div style='background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);'>"
    
    for team_name, search_query in FAVORITE_TEAMS.items():
        articles = fetch_team_news(search_query) 
        encoded_fallback = urllib.parse.quote(search_query)
        google_search_url = f"https://www.google.com/search?q={encoded_fallback}&tbm=nws"
        
        news_html += f"<h4 style='margin: 10px 0 5px 0; color: #2d3748; font-size: 14px;'>{team_name}</h4>"
        if articles:
            news_html += "<ul style='margin: 0; padding-left: 20px; font-size: 12px;'>"
            for art in articles:
                display_title = art['title'][:80] + '...' if len(art['title']) > 80 else art['title']
                news_html += f"<li style='margin-bottom: 4px;'><a href='{art['link']}' target='_blank' style='color: #2b6cb0; text-decoration: none;'>{display_title}</a></li>"
            news_html += "</ul>"
        else:
            news_html += f"<div style='color: #a0aec0; font-size: 12px; padding-left: 5px; font-style: italic;'>No relevant new articles found from the last 72 hours.</div>"
        news_html += f"<div style='margin-top: 5px; margin-bottom: 12px; font-size: 11px; padding-left: 5px;'><a href='{google_search_url}' target='_blank' style='color: #4a5568;'>↳ Search all news for this team</a></div>"
    news_html += "</div></div>"

    # ---------------------------------------------------------
    # 2. BUILD GAME CALENDARS HTML (Tab: Schedule)
    # ---------------------------------------------------------
    all_monitored_games = []
    for league, games in league_slates.items():
        for game in games:
            away_name = game['matchup'].split(' vs. ')[0]
            live_feed, real_status = get_live_espn_score(league, away_name)
            game_time = game.get('game_datetime', now_eastern)
            if real_status == 'completed' and now_eastern < game_time:
                real_status = 'upcoming'
                live_feed = None
                
            game['real_status'] = real_status 
            date_str = game.get('date')
            if not date_str and game.get('game_datetime'):
                date_str = game['game_datetime'].strftime("%A, %b %d")
            elif not date_str:
                date_str = now_eastern.strftime("%A, %b %d")

            all_monitored_games.append({
                "league": league,
                "matchup": game['matchup'],
                "time": game.get('tv_info', 'TBD'),
                "network": game.get('network', ''),
                "game_datetime": game.get('game_datetime', now_eastern),
                "date_header_str": date_str,
                "real_status": real_status,
                "live_feed": live_feed
            })

    def render_calendar_section(games_list, section_title, section_icon, section_color):
        if not games_list: return ""
        games_list.sort(key=lambda x: x['game_datetime'])
        chtml = f"<h3 style='border-bottom: 2px solid {section_color}; padding-bottom: 5px; color: #1a365d; margin-top: 20px;'>{section_icon} {section_title}</h3>"
        chtml += f"<div style='background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);'>"
        chtml += "<table style='width: 100%; font-size: 12px; border-collapse: collapse;'>"
        
        current_date_header = None
        for g in games_list:
            if g['date_header_str'] != current_date_header:
                current_date_header = g['date_header_str']
                chtml += f'<tr style="background-color: #f2f4f7;"><td colspan="3" style="padding: 6px 8px; font-weight: bold; color: #334155; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid #e2e8f0;">📅 {current_date_header}</td></tr>'

            tv_station = f" ({g['network']})" if g['network'] else ""
            matchup_display = f"<span style='color: #e53e3e; font-weight: bold;'>{g['live_feed']}</span>" if (g['real_status'] in ['completed', 'in_progress'] and g['live_feed']) else f"{g['matchup']}<span style='color: #e53e3e; font-weight: bold;'>{tv_station}</span>"
            chtml += f"<tr style='border-bottom: 1px solid #edf2f7;'><td style='padding: 6px 8px; color: #4a5568; font-weight: bold; width: 20%;'>{g['time']}</td><td style='padding: 6px 8px; color: #e53e3e; font-weight: bold; width: 15%;'>[{g['league']}]</td><td style='padding: 6px 8px; color: #2d3748;'>{matchup_display}</td></tr>"
        chtml += "</table></div>"
        return chtml

    schedule_html = "<div id='tab-schedule' class='tab-content'>"
    regular_games = [g for g in all_monitored_games if g['league'].upper() != 'EPL']
    soccer_games = [g for g in all_monitored_games if g['league'].upper() == 'EPL']

    if not regular_games and not soccer_games:
        schedule_html += f"<div style='background: #fff; padding: 15px; border-radius: 8px;'><span style='color: #a0aec0;'>No monitored sports scheduled for the next 7 days.</span></div>"
    else:
        schedule_html += render_calendar_section(regular_games, "Game Calendar", "📅", "#4a5568")
        schedule_html += render_calendar_section(soccer_games, "Soccer Schedule", "⚽", "#38a169")
    schedule_html += "</div>"

    # ---------------------------------------------------------
    # 3. BUILD UPCOMING LEAGUE BOARDS (Dynamic Tabs)
    # ---------------------------------------------------------
    def render_game_block(game, league):
        # [KEEP YOUR EXACT render_game_block CODE HERE]
        block_html = f"<div style='background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);'>"
        main_title = f"{league}: {game['matchup']}"
        away_team, home_team = game['matchup'].split(' vs. ')

        if league.upper() == "EPL":
            away_last_5_data = fetch_epl_xg_form(away_team)
            home_last_5_data = fetch_epl_xg_form(home_team)
            h2h_data = fetch_epl_head_to_head(away_team, home_team)
            away_metrics = fetch_epl_team_metrics(away_team)
            home_metrics = fetch_epl_team_metrics(home_team)
            away_last_5_html = build_xg_form_html(away_team, away_last_5_data, away_metrics)
            home_last_5_html = build_xg_form_html(home_team, home_last_5_data, home_metrics)
            h2h_html = build_h2h_html(h2h_data)
            away_injuries = fetch_epl_injuries(away_team)
            home_injuries = fetch_epl_injuries(home_team)
        else:
            away_last_5_data = fetch_last_5_games(away_team, league)
            home_last_5_data = fetch_last_5_games(home_team, league)
            away_last_5_html = build_last_5_html(away_team, away_last_5_data)
            home_last_5_html = build_last_5_html(home_team, home_last_5_data)
            h2h_html = ""
            away_injuries = ""
            home_injuries = ""
        
        block_html += f"<div style='display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px;'><h4 style='margin: 0; font-size: 16px; color: #2d3748; font-weight: 700; width: 65%;'>{main_title}</h4><div style='text-align: right; min-width: 120px;'><span style='background: #edf2f7; color: #4a5568; font-size: 11px; padding: 4px 8px; border-radius: 4px; font-weight: bold;'>{game['tv_info']}</span>"
        if game.get('network'): block_html += f"<br><span style='color: #e53e3e; font-size: 11px; font-weight: 900; display: inline-block; margin-top: 6px;'>📺 {game.get('network')}</span>"
        block_html += f"</div></div><table style='width: 100%; font-size: 13px; border-collapse: collapse;'><tr><td style='padding: 6px 0; color: #718096; width: 28%;'>FanDuel Lines:</td><td style='font-weight: bold; color: #1a202c;'>{game['odds']}</td></tr>"
        
        if "MLB" in league.upper(): block_html += f"<tr><td style='padding: 6px 0; color: #718096;'>Probable Pitchers:</td><td style='color: #2b6cb0; font-weight: bold;'>⚾ {game.get('pitchers', 'TBD vs TBD')}</td></tr>"
        if league.upper() != "EPL": block_html += f"<tr><td style='padding: 6px 0; color: #718096;'>Covers Consensus:</td><td>{format_consensus(game['covers'])}</td></tr>"
            
        block_html += f"<tr><td style='padding: 6px 0; color: #718096; font-weight: bold; vertical-align: top;'>Global News:</td><td>{game.get('news_html', '')}</td></tr></table>"
        
        if league.upper() != "EPL": block_html += game.get('injury_html', '')
        if league.upper() == "EPL": block_html += away_injuries + away_last_5_html + home_injuries + home_last_5_html
        else:
            block_html += away_last_5_html
            if "MLB" in league.upper() and game.get('away_pitcher_logs'): block_html += game['away_pitcher_logs']
            block_html += home_last_5_html
            if "MLB" in league.upper() and game.get('home_pitcher_logs'): block_html += game['home_pitcher_logs']
            
        block_html += h2h_html
        fd_url = "https://sportsbook.fanduel.com/soccer/english-premier-league" if league.upper() == "EPL" else f"https://sportsbook.fanduel.com/navigation/{league.lower()}"
        block_html += f"<a href='{fd_url}' style='display: block; background-color: #00aeef; color: white; text-align: center; padding: 10px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 13px; margin-top: 15px;'>Open {league} Market on FanDuel App 📲</a></div>"
        return block_html

    boards_html = ""
    dynamic_nav_buttons = ""
    
    for league, games in league_slates.items():
        upcoming_games = [g for g in games if g.get('real_status', 'upcoming') == 'upcoming']
        if not upcoming_games:
            continue 
            
        l_id = league.lower()
        dynamic_nav_buttons += f"<button class='tab-btn' id='btn-{l_id}' onclick=\"switchTab('{l_id}')\">🏆 {league}</button>"
        boards_html += f"<div id='tab-{l_id}' class='tab-content'>"
        for game in upcoming_games:
            boards_html += render_game_block(game, league)
        boards_html += "</div>"

    # ---------------------------------------------------------
    # 4. ASSEMBLE FINAL HTML WITH CSS & JS
    # ---------------------------------------------------------
    final_html = f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f7fafc; padding: 10px 20px; color: #1a202c; margin: 0; }}
            .tab-nav {{ display: flex; gap: 4px; overflow-x: auto; padding-bottom: 0px; border-bottom: 2px solid #cbd5e0; margin-bottom: 20px; white-space: nowrap; }}
            .tab-btn {{ background-color: #edf2f7; border: 1px solid #cbd5e0; border-bottom: none; padding: 12px 16px; border-radius: 8px 8px 0 0; cursor: pointer; font-weight: bold; color: #4a5568; font-size: 14px; margin-bottom: -2px; transition: 0.2s; }}
            .tab-btn:hover {{ background-color: #e2e8f0; }}
            .tab-btn.active {{ background-color: #fff; color: #2b6cb0; border-top: 3px solid #2b6cb0; border-left: 1px solid #cbd5e0; border-right: 1px solid #cbd5e0; border-bottom: 2px solid #fff; padding-top: 10px; z-index: 10; }}
            .tab-content {{ display: none; }}
        </style>
    </head>
    <body>
        <div class="tab-nav">
            <button class="tab-btn" id="btn-schedule" onclick="switchTab('schedule')">📅 Schedule</button>
            <button class="tab-btn" id="btn-news" onclick="switchTab('news')">🦅 Squads News</button>
            {dynamic_nav_buttons}
        </div>
        
        {schedule_html}
        {news_html}
        {boards_html}

        <script>
            function switchTab(tabName) {{
                document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
                document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
                
                const target = document.getElementById('tab-' + tabName);
                const btn = document.getElementById('btn-' + tabName);
                
                if (target) target.style.display = 'block';
                if (btn) btn.classList.add('active');
                
                // Set URL hash so refreshing stays on the same tab
                window.location.hash = tabName;
            }}

            window.addEventListener('DOMContentLoaded', () => {{
                let currentHash = window.location.hash.replace('#', '');
                // Fallback to schedule if hash is empty or invalid
                if (!currentHash || !document.getElementById('tab-' + currentHash)) {{
                    currentHash = 'schedule';
                }}
                switchTab(currentHash);
            }});
        </script>
    </body>
    </html>
    """
    return final_html

##End of Dynamic HTML Block

def push_to_github():
    """Pushes the updated index.html to GitHub Pages automatically."""
    try:
        repo_dir = r"C:\Users\jblum\Python\SportsNewsletter"
        subprocess.run(["git", "-C", repo_dir, "add", "index.html"], check=True)
        subprocess.run(["git", "-C", repo_dir, "commit", "-m", "Daily dashboard update"], check=True)
        subprocess.run(["git", "-C", repo_dir, "push"], check=True)
        print("🚀 [GITHUB] Dashboard pushed successfully to GitHub Pages.")
    except Exception as e:
        print(f"⚠️ [GITHUB] Could not push to GitHub: {e}")

def send_daily_email(html_content):
    """Sends the HTML content via email."""
    eastern_tz = ZoneInfo("America/New_York")
    now_eastern = datetime.datetime.now(eastern_tz)
    today_str = now_eastern.strftime("%B %d, %Y") 
    
    active_recipients = ["jblum4242@gmail.com"] 
    
    if now_eastern.hour >= 17:
        active_recipients.append("ruslana1111@gmail.com")
        
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🚀 Today's Games : {today_str}"
    msg["From"] = SENDER_EMAIL
    msg['To'] = ", ".join(active_recipients)
    msg.attach(MIMEText(html_content, "html"))
    
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, active_recipients, msg.as_string())
        print(f"💰 [SUCCESS] Report dispatched to: {', '.join(active_recipients)}")
        server.quit()
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    # 1. Generate the HTML dashboard once
    html = build_dynamic_html()
    
    # 2. Write the HTML to the local index.html file
    file_path = r"C:\Users\jblum\Python\SportsNewsletter\index.html"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("📝 [LOCAL] Successfully updated index.html.")
    
    # 3. Automatically push the new file to GitHub
    push_to_github()
    
    # 4. Send the exact same HTML out via email
    send_daily_email(html)