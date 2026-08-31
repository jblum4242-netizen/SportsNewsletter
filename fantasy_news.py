import requests
import json
import os
import time
import datetime
import urllib.parse
import xml.etree.ElementTree as ET
from googlenewsdecoder import gnewsdecoder

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo


def get_direct_article_url(google_url):
    """Uses the dedicated decoder package to bypass Google's encrypted tokens."""
    if not google_url.startswith("https://news.google.com"):
        return google_url
        
    try:
        time.sleep(0.5)
        result = gnewsdecoder(google_url)
        if result.get("status"):
            return result["decoded_url"]
    except Exception as e:
        print(f"Decoder error: {e}")
        
    return google_url

def fetch_player_news(player_name, max_articles=2):
    """Fetches recent news links for a specific fantasy player using Google News RSS."""
    search_query = f"{player_name} NFL news"
    encoded_query = urllib.parse.quote(search_query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    articles = []
    
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for item in root.findall('./channel/item'):
                # Check how old the article is
                pub_date_str = item.find('pubDate').text
                try:
                    pub_dt = datetime.datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=datetime.timezone.utc)
                    age_hours = (now_utc - pub_dt).total_seconds() / 3600
                except:
                    age_hours = 0
                
                # Only grab extremely fresh news (last 48 hours)
                if age_hours > 24:
                    continue
                    
                title = item.find('title').text
                title_lower = title.lower()
                
                # --- NEW: Filter out generic homepage titles ---
                generic_phrases = [
                    "official site of the national football league", 
                    "nfl.com", 
                    "espn", 
                    "yahoo sports",
                    "cbssports.com"
                ]
                if any(bad in title_lower for bad in generic_phrases):
                    continue
                    
                if " - " in title:
                    title = " - ".join(title.split(" - ")[:-1])
                    
                raw_link = item.find('link').text 
                direct_link = get_direct_article_url(raw_link)
                
                articles.append({'title': title, 'link': direct_link})
                
                if len(articles) == max_articles:
                    break
    except Exception as e:
        print(f"News fetch error for {player_name}: {e}")
        
    return articles

def fetch_sleeper_alerts(username, season="2026"):
    """Pulls a user's Sleeper roster, tags IR/Taxi players & team abbreviations (with FantasyCalc fallback), sorts by value, identifies free agents, and fetches news."""
    print(f"🔍 Locating Sleeper Account for: {username}...")
    
    # --- HELPER FUNCTION: Clean Names ---
    def normalize_name(name):
        if not name: return ""
        name = name.lower().strip()
        for char in [".", ",", "'", "’", "-"]: 
            name = name.replace(char, "")
        suffixes = [" jr", " sr", " ii", " iii", " iv"]
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)].strip()
        return name
    # ---------------------------------------

    # 1. Get internal Sleeper User ID
    user_res = requests.get(f"https://api.sleeper.app/v1/user/{username}").json()
    if not user_res:
        print("❌ Could not find Sleeper user.")
        return {}, [], {}, {}, {}
    user_id = user_res["user_id"]
    
    # 2. Get NFL League ID for current season
    leagues = requests.get(f"https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/{season}").json()
    if not leagues:
        print(f"❌ No active leagues found for {season}.")
        return {}, [], {}, {}, {}
    league_id = leagues[0]["league_id"] 
    print(f"🏆 Found League: {leagues[0]['name']}")
    
    # 3. Get all rosters in the league
    rosters = requests.get(f"https://api.sleeper.app/v1/league/{league_id}/rosters").json()
    my_roster = next((r for r in rosters if r["owner_id"] == user_id), None)
    if not my_roster:
        print("❌ Could not find your roster in this league.")
        return {}, [], {}, {}, {}
    
    # Extract IDs and isolate IR / Taxi slots for tagging
    reserve_ids = set(str(pid) for pid in (my_roster.get("reserve") or []))
    taxi_ids = set(str(pid) for pid in (my_roster.get("taxi") or []))
    
    raw_ids = (my_roster.get("players") or []) + (my_roster.get("reserve") or []) + (my_roster.get("taxi") or [])
    player_ids = list(dict.fromkeys([str(pid) for pid in raw_ids]))
    print(f"📋 Found {len(player_ids)} players on your roster. Fetching names...")
    
    # 4. Load master player cache
    cache_file = os.path.join(os.path.dirname(__file__), "sleeper_players.json")
    
    if not os.path.exists(cache_file):
        print("⏳ Downloading master player dictionary (this only happens once)...")
        players_data = requests.get("https://api.sleeper.app/v1/players/nfl").json()
        with open(cache_file, "w") as f:
            json.dump(players_data, f)
    else:
        with open(cache_file, "r") as f:
            players_data = json.load(f)

    # --- FETCH DYNASTY RANKINGS & BUILD RANK + TEAM MAPS ---
    print("📈 Fetching live Dynasty Rankings from FantasyCalc...")
    value_map = {}
    rank_map = {}
    fc_team_map = {} # Secondary fallback lookup dictionary
    
    try:
        url = "https://api.fantasycalc.com/values/current?isDynasty=true&numQbs=1&numTeams=12&ppr=1"
        response = requests.get(url, timeout=15)
        response.raise_for_status() 
        
        rankings_data = response.json()
        player_list = rankings_data if isinstance(rankings_data, list) else rankings_data.get('players', [])
        
        for rank_num, player in enumerate(player_list, start=1):
            player_dict = player.get('player', player)
            name = player_dict.get('name')
            value = player.get('value', 0)
            
            # Extract team code from FantasyCalc as backup
            fc_team = player_dict.get('mflTeam') or player_dict.get('maybeTeam') or player_dict.get('team') or ""
            
            if name:
                clean_name = normalize_name(name)
                value_map[clean_name] = value 
                rank_map[clean_name] = rank_num
                if fc_team:
                    fc_team_map[clean_name] = fc_team.upper()

        print("✅ Rankings and team fallbacks loaded from FantasyCalc!")
    except Exception as e:
        print(f"⚠️ Failed to sort roster by value, continuing with default order. Error: {e}")

    # Map raw Sleeper IDs to real player names, positions, teams, and designations (T / IR)
    my_players_info = []
    for pid in player_ids:
        if pid in players_data and players_data[pid].get("full_name"):
            p_name = players_data[pid]["full_name"]
            p_pos = players_data[pid].get("position", "OTHER")
            
            # Check Sleeper first; fall back to FantasyCalc if Sleeper team is empty
            p_team = players_data[pid].get("team") or fc_team_map.get(normalize_name(p_name), "")
            
            p_tag = ""
            if pid in taxi_ids:
                p_tag = "(T)"
            elif pid in reserve_ids:
                p_tag = "(IR)"
                
            my_players_info.append((p_name, p_pos, p_team, p_tag))
            
    # Sort Sleeper roster using value map
    my_players_info = sorted(
        my_players_info, 
        key=lambda x: value_map.get(normalize_name(x[0]), 0), 
        reverse=True
    )

    # --- GROUP ROSTER BY POSITION ---
    roster_by_pos = {"QB": [], "RB": [], "WR": [], "TE": []}
    for p_name, p_pos, p_team, p_tag in my_players_info:
        item = (p_name, p_team, p_tag)
        if p_pos in roster_by_pos:
            roster_by_pos[p_pos].append(item)
        else:
            roster_by_pos.setdefault("OTHER", []).append(item)

    my_players = [info[0] for info in my_players_info]

    # --- IDENTIFY TOP 5 AVAILABLE FREE AGENTS ---
    top_additions = []
    try:
        all_rostered_ids = set()
        for r in rosters:
            for slot in ["players", "reserve", "taxi"]:
                if r.get(slot):
                    all_rostered_ids.update([str(pid) for pid in r[slot]])

        all_rostered_names_clean = {
            normalize_name(players_data.get(pid, {}).get("full_name", ""))
            for pid in all_rostered_ids
            if players_data.get(pid, {}).get("full_name")
        }

        unique_free_agents_dict = {}
        for pid, pinfo in players_data.items():
            pid_str = str(pid)
            full_name = pinfo.get("full_name")
            pos = pinfo.get("position")
            
            if pid_str not in all_rostered_ids and full_name:
                clean_name = normalize_name(full_name)
                
                # Check Sleeper team first; fall back to FantasyCalc if Sleeper team is empty
                team = pinfo.get("team") or fc_team_map.get(clean_name, "")
                
                if clean_name not in all_rostered_names_clean and pos in ["QB", "RB", "WR", "TE"]:
                    if clean_name not in unique_free_agents_dict:
                        unique_free_agents_dict[clean_name] = (full_name, pos, team) 
                        
        unique_free_agents = list(unique_free_agents_dict.values())

        sorted_free_agents = sorted(
            unique_free_agents,
            key=lambda x: value_map.get(normalize_name(x[0]), 0),
            reverse=True
        )
        
        top_additions = sorted_free_agents[:5]
        print(f"💡 Identified Top 5 Available Free Agents: {[fa[0] for fa in top_additions]}")
    except Exception as e:
        print(f"⚠️ Failed to calculate free agent additions. Error: {e}")
    
    # --- FETCH NEWS FOR TOP 5 FREE AGENTS ---
    fa_news = {}
    if top_additions:
        print("\n📰 Scanning for recent news on Top 5 Free Agents...")
        for fa_name, fa_pos, fa_team in top_additions:
            news_items = fetch_player_news(fa_name, max_articles=2)
            if news_items:
                print(f"  ✅ Found news for FA: {fa_name}")
                fa_news[fa_name] = news_items
            else:
                print(f"  - No recent news for FA: {fa_name}")

    # --- FETCH NEWS FOR ROSTERED PLAYERS ---
    roster_news = {}
    print("\n📰 Scanning for recent news on your key players...")
    
    for player_name in my_players[:27]: 
        news_items = fetch_player_news(player_name, max_articles=2)
        if news_items:
            print(f"  ✅ Found news for {player_name}")
            roster_news[player_name] = news_items
        else:
            print(f"  - No recent news for {player_name}")
            
    return roster_news, top_additions, fa_news, rank_map, roster_by_pos


# --- EMAIL CREDENTIALS ---
SENDER_EMAIL = "jblum4242@gmail.com"
SENDER_PASSWORD = "lzygskznkqcejpva"  # Your 16-letter App Password
RECEIVER_EMAIL = "jblum4242@gmail.com"

def build_fantasy_news_html(news_data, top_additions, fa_news, rank_map, roster_by_pos):
    """Converts fantasy roster news, positional roster breakdown (with T/IR & team tags), and top FA news into styled HTML."""
    if not news_data and not top_additions:
        return ""

    def get_clean_key(name):
        clean = name.lower().strip()
        for char in [".", ",", "'", "’", "-"]:
            clean = clean.replace(char, "")
        for suffix in [" jr", " sr", " ii", " iii", " iv"]:
            if clean.endswith(suffix):
                clean = clean[:-len(suffix)].strip()
        return clean

    html = "<h3 style='border-bottom: 2px solid #e53e3e; padding-bottom: 5px; color: #1a365d; margin-top: 20px;'>🚨 Dynasty Roster Alerts</h3>"

    # --- TOP 5 AVAILABLE FREE AGENTS CARD ---
    if top_additions:
        html += "<div style='background: #edf2f7; border: 1px solid #cbd5e0; border-radius: 8px; padding: 15px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);'>"
        html += "<h4 style='margin: 0 0 10px 0; color: #2b6cb0; font-size: 14px;'>💡 Top 5 Available Free Agents</h4>"
        html += "<ul style='margin: 0; padding-left: 20px; font-size: 13px; color: #2d3748;'>"
        
        for fa_player, fa_pos, fa_team in top_additions:
            fa_rank = rank_map.get(get_clean_key(fa_player))
            rank_str = f" <span style='color: #718096; font-size: 11px; font-weight: normal;'>(#{fa_rank})</span>" if fa_rank else " <span style='color: #a0aec0; font-size: 11px;'>(Unranked)</span>"
            team_str = f" <span style='color: #4a5568; font-size: 11px; font-weight: normal;'>({fa_team})</span>" if fa_team else ""
            
            # Displays: Evan Engram (TE) (#316) (JAX)
            html += f"<li style='margin-bottom: 6px; font-weight: bold;'>{fa_player} <span style='color: #4a5568; font-weight: normal;'>({fa_pos})</span>{rank_str}{team_str}"
            
            if fa_player in fa_news and fa_news[fa_player]:
                html += "<ul style='margin: 4px 0 6px 0; padding-left: 18px; font-weight: normal; font-size: 12px;'>"
                for art in fa_news[fa_player]:
                    display_title = art['title'][:80] + '...' if len(art['title']) > 80 else art['title']
                    html += f"<li style='margin-bottom: 3px;'><a href='{art['link']}' target='_blank' style='color: #2b6cb0; text-decoration: none;'>{display_title}</a></li>"
                html += "</ul>"
            html += "</li>"
            
        html += "</ul></div>"

    # --- POSITIONAL ROSTER SUMMARY CARD (WITH T/IR & NFL TEAM TAGS) ---
    if roster_by_pos:
        html += "<div style='background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);'>"
        html += "<h4 style='margin: 0 0 10px 0; color: #1a365d; font-size: 14px;'>📋 Current Roster Breakdown</h4>"
        html += "<div style='font-size: 12px; color: #2d3748; line-height: 1.6;'>"
        
        for pos in ["QB", "RB", "WR", "TE"]:
            players = roster_by_pos.get(pos, [])
            if players:
                formatted_players = []
                for p_name, p_team, p_tag in players:
                    p_rank = rank_map.get(get_clean_key(p_name))
                    rank_txt = f"#{p_rank}" if p_rank else "Unranked"
                    
                    tag_display = ""
                    if p_tag == "(T)":
                        tag_display = " <span style='color: #d69e2e; font-weight: bold;'>(T)</span>"
                    elif p_tag == "(IR)":
                        tag_display = " <span style='color: #e53e3e; font-weight: bold;'>(IR)</span>"
                        
                    team_display = f" <span style='color: #4a5568;'>({p_team})</span>" if p_team else ""
                        
                    # Displays: Trevor Lawrence (#80) (JAX) or Ty Simpson (T) (#251) (LAR)
                    formatted_players.append(f"<strong>{p_name}</strong>{tag_display} <span style='color: #718096;'>({rank_txt})</span>{team_display}")
                
                player_str = ", ".join(formatted_players)
                html += f"<p style='margin: 4px 0;'><strong>{pos}s:</strong> {player_str}</p>"
                
        html += "</div></div>"

    # --- SLEEPER DYNASTY NEWS FEED ---
    html += "<div style='background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 20px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);'>"
    html += "<div style='background: #1a365d; color: #ffffff; padding: 10px 15px; font-weight: bold; font-size: 14px;'>⚡ Sleeper Dynasty News Feed</div>"
    html += "<div style='padding: 15px;'>"

    for player, articles in news_data.items():
        player_rank = rank_map.get(get_clean_key(player))
        rank_display = f" <span style='color: #718096; font-size: 12px; font-weight: normal;'>(#{player_rank})</span>" if player_rank else ""
        
        html += f"<h4 style='margin: 10px 0 5px 0; color: #2d3748; font-size: 14px;'>🏈 {player}{rank_display}</h4>"
        html += "<ul style='margin: 0; padding-left: 20px; font-size: 12px;'>"
        for art in articles:
            display_title = art['title'][:80] + '...' if len(art['title']) > 80 else art['title']
            html += f"<li style='margin-bottom: 6px;'><a href='{art['link']}' target='_blank' style='color: #2b6cb0; text-decoration: none;'>{display_title}</a></li>"
        html += "</ul>"

    html += "</div></div>"
    return html


def send_fantasy_email(username):
    """Fetches fantasy alerts, formats them into HTML, and dispatches an email dynamically based on time."""
    # 1. Unpack all 5 variables from fetch_sleeper_alerts
    news_data, top_additions, fa_news, rank_map, roster_by_pos = fetch_sleeper_alerts(username)
    
    if not news_data and not top_additions:
        print("ℹ️ No recent news or additions found. Skipping email.")
        return
        
    # 2. Convert news and additions to HTML
    html_content = build_fantasy_news_html(news_data, top_additions, fa_news, rank_map, roster_by_pos)
    
    # 3. Determine Time & Build Email Wrapper
    eastern_tz = ZoneInfo("America/New_York")
    now_eastern = datetime.datetime.now(eastern_tz)
    today_str = now_eastern.strftime("%B %d, %Y")
    
    full_email_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f7fafc; padding: 20px; color: #1a202c;">
        {html_content}
    </body>
    </html>
    """
    
    # --- DYNAMIC RECIPIENT LOGIC ---
    active_recipients = ["jblum4242@gmail.com"] 
    
    # For the 8:05 PM run, the hour is 20 (which is >= 17)
    if now_eastern.hour >= 17:
        active_recipients.append("ruslana1111@gmail.com")
        print("🌙 Evening run detected: Adding Ruslana to the recipient list.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🚨 Dynasty Roster Alerts : {today_str}"
    msg["From"] = SENDER_EMAIL
    
    # Join the array into a comma-separated string for the visible email header
    msg["To"] = ", ".join(active_recipients) 
    
    msg.attach(MIMEText(full_email_html, "html"))
    
    # 4. Send email via SMTP
    if not SENDER_PASSWORD:
        print("❌ Error: GMAIL_APP_PASSWORD environment variable is not set.")
        return

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        
        # Pass the list of recipients directly to the sendmail function
        server.sendmail(SENDER_EMAIL, active_recipients, msg.as_string())
        
        print(f"📧 [SUCCESS] Dynasty news report dispatched to: {', '.join(active_recipients)}")
        server.quit()
    except Exception as e:
        print(f"❌ Email Error: {e}")


# --- TEST BLOCK ---
# This block ONLY runs if you execute this specific file directly.
# It will be ignored if you import this file into bet.py later!
if __name__ == '__main__':
    username = "GreatBlumbino"  # Replace with your actual Sleeper username
    
    print("🚀 Booting up Fantasy News Submodule...\n")
    
    # Send the fantasy news email directly!
    send_fantasy_email(username)