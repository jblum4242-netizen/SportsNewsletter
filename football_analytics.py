import requests
from bs4 import BeautifulSoup
import datetime

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def fetch_global_stat_category(sport_path, stat_path):
    """Scrapes TeamRankings for traditional PPG and YPG metrics."""
    url = f"https://www.teamrankings.com/{sport_path}/stat/{stat_path}"
    data_map = {}
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            table = soup.find('table')
            if not table: return data_map
            
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 3:
                    rank = cols[0].text.strip()
                    team_raw = cols[1].text.strip().lower()
                    val = cols[2].text.strip()
                    data_map[team_raw] = {"rank": rank, "value": val}
    except Exception as e:
        print(f"⚠️ Error fetching {stat_path}: {e}")
        
    return data_map

def fetch_nfl_epa():
    """Calculates granular passing and rushing EPA using nflreadpy."""
    try:
        import nflreadpy as nfl
        import pandas as pd
    except ImportError:
        print("⚠️ nflreadpy not installed. Run 'pip install nflreadpy pandas'.")
        return {}
        
    print("📊 Downloading raw NFL play-by-play data via nflreadpy...")
    current_year = datetime.datetime.now().year
    
    nfl_mascot_map = {
        'ARI': 'cardinals', 'ATL': 'falcons', 'BAL': 'ravens', 'BUF': 'bills',
        'CAR': 'panthers', 'CHI': 'bears', 'CIN': 'bengals', 'CLE': 'browns',
        'DAL': 'cowboys', 'DEN': 'broncos', 'DET': 'lions', 'GB': 'packers',
        'HOU': 'texans', 'IND': 'colts', 'JAX': 'jaguars', 'KC': 'chiefs',
        'LV': 'raiders', 'LAC': 'chargers', 'LAR': 'rams', 'MIA': 'dolphins',
        'MIN': 'vikings', 'NE': 'patriots', 'NO': 'saints', 'NYG': 'giants',
        'NYJ': 'jets', 'PHI': 'eagles', 'PIT': 'steelers', 'SF': '49ers',
        'SEA': 'seahawks', 'TB': 'buccaneers', 'TEN': 'titans', 'WAS': 'commanders'
    }
    
    try:
        pbp = nfl.load_pbp([current_year])
        pbp = pbp.dropna(subset=['epa'])
        pbp = pbp[pbp['play_type'].isin(['pass', 'run'])]
        
        off_total = pbp.groupby('posteam')['epa'].mean().round(3)
        off_pass = pbp[pbp['play_type'] == 'pass'].groupby('posteam')['epa'].mean().round(3)
        off_rush = pbp[pbp['play_type'] == 'run'].groupby('posteam')['epa'].mean().round(3)
        
        def_total = pbp.groupby('defteam')['epa'].mean().round(3)
        def_pass = pbp[pbp['play_type'] == 'pass'].groupby('defteam')['epa'].mean().round(3)
        def_rush = pbp[pbp['play_type'] == 'run'].groupby('defteam')['epa'].mean().round(3)
        
        off_total_ranks = off_total.rank(ascending=False, method='min')
        off_pass_ranks = off_pass.rank(ascending=False, method='min')
        off_rush_ranks = off_rush.rank(ascending=False, method='min')
        
        def_total_ranks = def_total.rank(ascending=True, method='min')
        def_pass_ranks = def_pass.rank(ascending=True, method='min')
        def_rush_ranks = def_rush.rank(ascending=True, method='min')
        
        epa_map = {}
        for abbr, mascot in nfl_mascot_map.items():
            if abbr in off_total:
                epa_map[mascot] = {
                    "off_total": f"{off_total[abbr]:.2f}",
                    "off_total_rank": f"{int(off_total_ranks[abbr])}",
                    "off_pass": f"{off_pass[abbr]:.2f}",
                    "off_pass_rank": f"{int(off_pass_ranks[abbr])}",
                    "off_rush": f"{off_rush[abbr]:.2f}",
                    "off_rush_rank": f"{int(off_rush_ranks[abbr])}",
                    "def_total": f"{def_total[abbr]:.2f}",
                    "def_total_rank": f"{int(def_total_ranks[abbr])}",
                    "def_pass": f"{def_pass[abbr]:.2f}",
                    "def_pass_rank": f"{int(def_pass_ranks[abbr])}",
                    "def_rush": f"{def_rush[abbr]:.2f}",
                    "def_rush_rank": f"{int(def_rush_ranks[abbr])}",
                }
        return epa_map
    except Exception as e:
        print(f"⚠️ Error calculating NFL EPA with nflreadpy: {e}")
        return {}

def fetch_cfb_epa():
    """Calculates granular passing and rushing EPA using sportsdataverse."""
    try:
        import sportsdataverse as sdv
    except ImportError:
        print("⚠️ sportsdataverse not installed. Run 'pip install sportsdataverse pandas'.")
        return {}
        
    print("📊 Downloading raw CFB play-by-play data via sportsdataverse...")
    current_year = datetime.datetime.now().year
    
    try:
        # Load the data as a pandas dataframe for compatibility with our ranking logic
        pbp = sdv.cfb.load_cfb_pbp(seasons=[current_year], return_as_pandas=True)
        
        # Ensure we only use plays with valid EPA and standard play types
        pbp = pbp.dropna(subset=['EPA'])
        pbp = pbp[pbp['play_type'].isin(['Pass Reception', 'Pass Incompletion', 'Rush', 'Passing Touchdown', 'Rushing Touchdown', 'Sack'])]
        
        # Tag play types for passing and rushing
        pbp['is_pass'] = pbp['play_type'].str.contains('Pass|Sack', case=False)
        pbp['is_rush'] = pbp['play_type'].str.contains('Rush', case=False)
        
        # Offensive splits
        off_total = pbp.groupby('pos_team')['EPA'].mean().round(3)
        off_pass = pbp[pbp['is_pass']].groupby('pos_team')['EPA'].mean().round(3)
        off_rush = pbp[pbp['is_rush']].groupby('pos_team')['EPA'].mean().round(3)
        
        # Defensive splits
        def_total = pbp.groupby('def_pos_team')['EPA'].mean().round(3)
        def_pass = pbp[pbp['is_pass']].groupby('def_pos_team')['EPA'].mean().round(3)
        def_rush = pbp[pbp['is_rush']].groupby('def_pos_team')['EPA'].mean().round(3)
        
        # Rank them 
        off_total_ranks = off_total.rank(ascending=False, method='min')
        off_pass_ranks = off_pass.rank(ascending=False, method='min')
        off_rush_ranks = off_rush.rank(ascending=False, method='min')
        
        def_total_ranks = def_total.rank(ascending=True, method='min')
        def_pass_ranks = def_pass.rank(ascending=True, method='min')
        def_rush_ranks = def_rush.rank(ascending=True, method='min')
        
        epa_map = {}
        for team_name in off_total.index:
            # Clean up team name formatting to make matching easier
            clean_name = str(team_name).lower().replace("state", "st")
            epa_map[clean_name] = {
                "off_total": f"{off_total.get(team_name, 0):.2f}",
                "off_total_rank": f"{int(off_total_ranks.get(team_name, 999))}",
                "off_pass": f"{off_pass.get(team_name, 0):.2f}",
                "off_pass_rank": f"{int(off_pass_ranks.get(team_name, 999))}",
                "off_rush": f"{off_rush.get(team_name, 0):.2f}",
                "off_rush_rank": f"{int(off_rush_ranks.get(team_name, 999))}",
                "def_total": f"{def_total.get(team_name, 0):.2f}",
                "def_total_rank": f"{int(def_total_ranks.get(team_name, 999))}",
                "def_pass": f"{def_pass.get(team_name, 0):.2f}",
                "def_pass_rank": f"{int(def_pass_ranks.get(team_name, 999))}",
                "def_rush": f"{def_rush.get(team_name, 0):.2f}",
                "def_rush_rank": f"{int(def_rush_ranks.get(team_name, 999))}",
            }
        return epa_map
    except Exception as e:
        print(f"⚠️ Error calculating CFB EPA with sportsdataverse: {e}")
        return {}

def fetch_all_league_stats(league):
    """Fetches global leaderboards and EPA metrics."""
    sport_path = "nfl" if league.lower() == "nfl" else "college-football"
    print(f"📊 Fetching global {league.upper()} traditional leaderboards...")
    
    league_stats = {
        "off_ppg": fetch_global_stat_category(sport_path, "points-per-game"),
        "def_ppg": fetch_global_stat_category(sport_path, "opponent-points-per-game"),
        "off_ypg": fetch_global_stat_category(sport_path, "yards-per-game"),
        "def_ypg": fetch_global_stat_category(sport_path, "opponent-yards-per-game")
    }
    
    if league.lower() == "nfl":
        league_stats["epa"] = fetch_nfl_epa()
    else:
        league_stats["epa"] = fetch_cfb_epa()
        
    return league_stats

def build_football_stats_html(team_name, league, global_stats):
    """Generates a compact HTML table block for the team's advanced stats."""
    team_lower = team_name.lower().replace("state", "st")
    mascot = team_name.lower().split()[-1]
    
    matched_tr_key = None
    for tr_key in sorted(global_stats["off_ppg"].keys(), key=len, reverse=True):
        if tr_key == team_lower or f"{tr_key} " in f"{team_lower} ":
            matched_tr_key = tr_key
            break

    if matched_tr_key:
        team_data = {
            "off_ppg": global_stats["off_ppg"].get(matched_tr_key, {"rank": "-", "value": "N/A"}),
            "def_ppg": global_stats["def_ppg"].get(matched_tr_key, {"rank": "-", "value": "N/A"}),
            "off_ypg": global_stats["off_ypg"].get(matched_tr_key, {"rank": "-", "value": "N/A"}),
            "def_ypg": global_stats["def_ypg"].get(matched_tr_key, {"rank": "-", "value": "N/A"})
        }
    else:
        team_data = {k: {"rank": "-", "value": "N/A"} for k in ["off_ppg", "def_ppg", "off_ypg", "def_ypg"]}
    
    if team_data["off_ppg"]["value"] == "N/A" and league.lower() != "nfl":
        return f"<div style='margin-top: 10px; font-size: 11px; color: #a0aec0;'>No FBS leaderboard data available for {team_name}.</div>"

    html = f"<div style='margin-top: 15px; margin-bottom: 5px;'>"
    html += f"<strong style='font-size: 12px; color: #2d3748;'>📊 {team_name} Rankings:</strong>"
    html += f"<table style='width: 100%; font-size: 11px; text-align: center; border-collapse: collapse; margin-top: 4px;'>"
    html += f"<tr style='background-color: #edf2f7; color: #4a5568;'>"
    html += f"<th style='padding: 3px; text-align: left;'>Category</th>"
    html += f"<th style='padding: 3px;'>Value</th>"
    html += f"<th style='padding: 3px;'>Rank</th>"
    html += f"</tr>"
    
    def get_rank_color(rank_str):
        if not str(rank_str).isdigit(): return "#718096"
        rank = int(rank_str)
        if rank <= 12: return "#38a169" 
        if rank >= 25: return "#e53e3e" 
        return "#718096" 

    rows = []
    
    if "epa" in global_stats:
        epa_data = None
        if league.lower() == "nfl":
            epa_data = global_stats["epa"].get(mascot)
        else:
            for epa_key, data in global_stats["epa"].items():
                if epa_key in team_lower or team_lower in epa_key:
                    epa_data = data
                    break
                
        if epa_data:
            rows.extend([
                ("Offense Total (EPA)", {"value": epa_data['off_total'], "rank": epa_data['off_total_rank']}),
                ("Offense Pass (EPA)", {"value": epa_data['off_pass'], "rank": epa_data['off_pass_rank']}),
                ("Offense Rush (EPA)", {"value": epa_data['off_rush'], "rank": epa_data['off_rush_rank']}),
                ("Defense Total (EPA)", {"value": epa_data['def_total'], "rank": epa_data['def_total_rank']}),
                ("Defense Pass (EPA)", {"value": epa_data['def_pass'], "rank": epa_data['def_pass_rank']}),
                ("Defense Rush (EPA)", {"value": epa_data['def_rush'], "rank": epa_data['def_rush_rank']})
            ])

    rows.extend([
        ("Offense (PPG)", team_data['off_ppg']),
        ("Defense (PPG)", team_data['def_ppg']),
        ("Offense (YPG)", team_data['off_ypg']),
        ("Defense (YPG)", team_data['def_ypg'])
    ])
    
    for label, data in rows:
        r_color = get_rank_color(data['rank'])
        html += f"<tr style='border-bottom: 1px solid #e2e8f0;'>"
        html += f"<td style='padding: 3px; text-align: left; font-weight: bold; color: #4a5568;'>{label}</td>"
        html += f"<td style='padding: 3px;'>{data['value']}</td>"
        html += f"<td style='padding: 3px; font-weight: bold; color: {r_color};'>#{data['rank']}</td>"
        html += f"</tr>"
        
    html += "</table></div>"
    return html

# --- TEST BLOCK ---
if __name__ == '__main__':
    print("🚀 Booting up Football Stats Submodule...\n")
    
    nfl_global_stats = fetch_all_league_stats("NFL")
    cfb_global_stats = fetch_all_league_stats("NCAAF")
    
    test_teams = [
        ("Philadelphia Eagles", "NFL", nfl_global_stats),
        ("Chicago Bears", "NFL", nfl_global_stats),
        ("Indiana Hoosiers", "NCAAF", cfb_global_stats),
        ("Ohio State Buckeyes", "NCAAF", cfb_global_stats),
        ("Delaware Blue Hens", "NCAAF", cfb_global_stats) 
    ]
    
    for team, league, global_dict in test_teams:
        html_block = build_football_stats_html(team, league, global_dict)
        print(f"\n--- {team} HTML ---")
        print(html_block)
        
    print("\n✅ Module execution complete.")