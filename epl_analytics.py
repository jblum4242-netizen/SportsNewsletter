import requests
import pandas as pd
from understatapi import UnderstatClient
from datetime import datetime

def format_understat_name(name):
    """Cleans and maps EPL team names to match Understat's exact database slugs."""
    name_map = {
        "Manchester United": "Manchester_United",
        "Manchester City": "Manchester_City",
        "Crystal Palace": "Crystal_Palace",
        "West Ham United": "West_Ham",
        "Leeds United": "Leeds",
        "Brighton and Hove Albion": "Brighton",
        "Wolverhampton Wanderers": "Wolverhampton",
        "Tottenham Hotspur": "Tottenham",
        "Nottingham Forest": "Nottingham_Forest",
        "Newcastle United": "Newcastle_United",
        "Newcastle Utd": "Newcastle_United",
        "Newcastle": "Newcastle_United",
        "Hull City": "Hull",
        "Coventry City": "Coventry",
        "Ipswich Town": "Ipswich",
        "Leicester City": "Leicester",
        "Luton Town": "Luton",
        "Cardiff City": "Cardiff",
        "Swansea City": "Swansea"
    }
    
    if name in name_map:
        return name_map[name]
        
    clean_name = name.replace(" Hotspur", "").replace(" FC", "").replace("AFC ", "")
    return clean_name.strip().replace(" ", "_")

def fetch_epl_xg_form(team_name):
    search_name = format_understat_name(team_name)
    display_name = search_name.replace("_", " ")
    
    current_year = str(datetime.now().year)
    previous_year = str(int(current_year) - 1)
    
    try:
        with UnderstatClient() as understat:
            for season in [current_year, previous_year]:
                try:
                    raw_data = understat.team(team=search_name).get_match_data(season=season)
                    
                    if not raw_data:
                        continue
                        
                    df = pd.DataFrame(raw_data)
                    
                    if 'isResult' in df.columns:
                        completed = df[df['isResult'] == True].copy()
                    else:
                        completed = df.copy()
                        
                    if not completed.empty:
                        # Grab last 5 and reverse so the most recent match is at the top
                        last_5 = completed.tail(5).iloc[::-1]
                        team_results = []
                        
                        for _, match in last_5.iterrows():
                            h_team = match['h']['title']
                            a_team = match['a']['title']
                            is_home = display_name.lower() in h_team.lower()
                            
                            goals = match['goals']
                            xg_data = match['xG']
                            
                            raw_date = match.get('datetime', '')
                            try:
                                date_obj = datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S")
                                formatted_date = date_obj.strftime("%b %d")
                            except ValueError:
                                formatted_date = raw_date[:10]
                            
                            if is_home:
                                opponent = a_team
                                venue = "H"
                                scored = int(goals['h'])
                                conceded = int(goals['a'])
                                xG = float(xg_data['h'])
                                xGA = float(xg_data['a'])
                            else:
                                opponent = h_team
                                venue = "A"
                                scored = int(goals['a'])
                                conceded = int(goals['h'])
                                xG = float(xg_data['a'])
                                xGA = float(xg_data['h'])
                                
                            if scored > conceded:
                                result = "W"
                            elif scored < conceded:
                                result = "L"
                            else:
                                result = "D"
                                
                            team_results.append({
                                'date': formatted_date,
                                'venue': venue,
                                'opponent': opponent,
                                'result': result,
                                'scored': scored,
                                'missed': conceded,
                                'xG': xG,
                                'xGA': xGA
                            })
                            
                        return team_results
                        
                except Exception:
                    continue
                    
        return []
        
    except Exception:
        return []


def fetch_epl_head_to_head(team_a, team_b):
    """Finds the last 2 head-to-head matches between team_a and team_b quietly."""
    search_a = format_understat_name(team_a)
    search_b = format_understat_name(team_b)
    
    current_year = str(datetime.now().year)
    previous_year = str(int(current_year) - 1)
    
    try:
        with UnderstatClient() as understat:
            raw_data = understat.team(team=search_a).get_match_data(season=current_year)
            if not raw_data:
                raw_data = understat.team(team=search_a).get_match_data(season=previous_year)
                
            if not raw_data:
                return []
                
            df = pd.DataFrame(raw_data)
            completed = df[df['isResult'] == True].copy() if 'isResult' in df.columns else df.copy()
            
            h2h_matches = []
            
            for _, match in completed.iloc[::-1].iterrows():
                h_team = match['h']['title'].lower()
                a_team = match['a']['title'].lower()
                
                if search_b.lower().replace("_", " ") in h_team or search_b.lower().replace("_", " ") in a_team:
                    is_team_a_home = search_a.lower().replace("_", " ") in h_team
                    
                    goals = match['goals']
                    xg_data = match['xG']
                    
                    raw_date = match.get('datetime', '')
                    try:
                        date_obj = datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S")
                        formatted_date = date_obj.strftime("%b %d, %Y")
                    except ValueError:
                        formatted_date = raw_date[:10]
                    
                    if is_team_a_home:
                        score_a = int(goals['h'])
                        score_b = int(goals['a'])
                        xg_a = float(xg_data['h'])
                        xg_b = float(xg_data['a'])
                        venue = f"{team_a} (H) vs {team_b} (A)"
                    else:
                        score_a = int(goals['a'])
                        score_b = int(goals['h'])
                        xg_a = float(xg_data['a'])
                        xg_b = float(xg_data['h'])
                        venue = f"{team_a} (A) vs {team_b} (H)"
                        
                    h2h_matches.append({
                        'date': formatted_date,
                        'venue': venue,
                        'score_a': score_a,
                        'score_b': score_b,
                        'xg_a': xg_a,
                        'xg_b': xg_b,
                        'team_a_name': team_a,
                        'team_b_name': team_b
                    })
                    
                    if len(h2h_matches) >= 2:
                        break
                        
            return h2h_matches
            
    except Exception:
        return []


def fetch_epl_team_metrics(team_name):
    """Pulls KenPom-style season metrics (PPDA Pressing & Expected Points Luck)."""
    search_name = format_understat_name(team_name)
    current_year = str(datetime.now().year)
    previous_year = str(int(current_year) - 1)
    
    try:
        with UnderstatClient() as understat:
            for season in [current_year, previous_year]:
                try:
                    stats_data = understat.team(team=search_name).get_team_data(season=season)
                    if not stats_data:
                        continue
                        
                    ppda_att = float(stats_data.get('ppda', {}).get('att', 0))
                    ppda_def = float(stats_data.get('ppda', {}).get('def', 0))
                    pts = float(stats_data.get('pts', 0))
                    xpts = float(stats_data.get('xpts', 0.0))
                    luck_diff = pts - xpts
                    
                    return {
                        'ppda': ppda_att,
                        'ppda_allowed': ppda_def,
                        'pts': pts,
                        'xpts': xpts,
                        'luck': luck_diff
                    }
                except Exception:
                    continue
        return None
    except Exception:
        return None


def fetch_epl_injuries(team_name):
    """Fetches and formats injuries specifically for a single team. Returns empty string if none."""
    
    # Map the incoming FanDuel name directly to the exact FPL database name
    fpl_name_map = {
        "Tottenham Hotspur": "Spurs",
        "Manchester United": "Man Utd",
        "Manchester City": "Man City",
        "Newcastle United": "Newcastle",
        "Newcastle Utd": "Newcastle",
        "Wolverhampton Wanderers": "Wolves",
        "Brighton and Hove Albion": "Brighton",
        "Nottingham Forest": "Nott'm Forest",
        "Leicester City": "Leicester",
        "Ipswich Town": "Ipswich",
        "Hull City": "Hull",
        "Coventry City": "Coventry"
    }
    
    fpl_search_name = fpl_name_map.get(team_name, team_name)
    
    try:
        url = "https://fantasy.premierleague.com/api/bootstrap-static/"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return ""
            
        data = response.json()
        teams = {t['id']: t['name'] for t in data.get('teams', [])}
        players = data.get('elements', [])
        
        injured_players = []
        
        for player in players:
            status = player.get('status')
            news = player.get('news', '')
            
            # Check for injured or doubtful statuses
            if status in ['i', 'd'] or (news and ('injured' in news.lower() or 'doubt' in news.lower() or 'suspended' in news.lower())):
                team_id = player.get('team')
                team_full_name = teams.get(team_id, '')
                
                # Check if the mapped FPL name is in the FPL database name
                if fpl_search_name.lower() in team_full_name.lower():
                    name = f"{player.get('first_name')} {player.get('second_name')}"
                    chance = player.get('chance_of_playing_next_round')
                    chance_str = f" ({chance}% chance)" if chance is not None else ""
                    injured_players.append(f"<li><b>{name}</b>{chance_str}: {news}</li>")
                    
        # Return an empty string if no injuries exist so it doesn't clutter the UI
        if not injured_players:
            return ""
            
        html = f"<div style='margin-bottom: 8px; font-size: 11px;'>"
        html += f"<strong style='color: #c53030;'>🏥 {team_name} Injuries:</strong>"
        html += f"<ul style='margin: 2px 0 0 15px; padding: 0; color: #4a5568;'>"
        html += "".join(injured_players)
        html += f"</ul></div>"
        return html
        
    except Exception as e:
        print(f"Injury fetch error for {team_name}: {e}")
        return ""