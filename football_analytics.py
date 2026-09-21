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
        print("⚠️ nflreadpy not installed. Run 'pip install nflreadpy pandas pyarrow'.")
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
        pbp = nfl.load_pbp([current_year]).to_pandas()
        
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
        pbp = sdv.cfb.load_cfb_pbp(seasons=[current_year], return_as_pandas=True)
        
        epa_col = 'EPA' if 'EPA' in pbp.columns else 'epa'
        pos_team_col = 'pos_team' if 'pos_team' in pbp.columns else 'posteam'
        def_team_col = 'def_pos_team' if 'def_pos_team' in pbp.columns else 'defteam'
        
        play_type_col = 'play_type' if 'play_type' in pbp.columns else 'type_text'
        if play_type_col not in pbp.columns:
            play_type_col = [c for c in pbp.columns if 'type' in c.lower()][0]

        pbp = pbp.dropna(subset=[epa_col, play_type_col])
        pbp['is_pass'] = pbp[play_type_col].astype(str).str.contains('Pass|Sack', case=False, na=False)
        pbp['is_rush'] = pbp[play_type_col].astype(str).str.contains('Rush', case=False, na=False)
        pbp = pbp[pbp['is_pass'] | pbp['is_rush']]
        
        off_total = pbp.groupby(pos_team_col)[epa_col].mean().round(3)
        off_pass = pbp[pbp['is_pass']].groupby(pos_team_col)[epa_col].mean().round(3)
        off_rush = pbp[pbp['is_rush']].groupby(pos_team_col)[epa_col].mean().round(3)
        
        def_total = pbp.groupby(def_team_col)[epa_col].mean().round(3)
        def_pass = pbp[pbp['is_pass']].groupby(def_team_col)[epa_col].mean().round(3)
        def_rush = pbp[pbp['is_rush']].groupby(def_team_col)[epa_col].mean().round(3)
        
        off_total_ranks = off_total.rank(ascending=False, method='min')
        off_pass_ranks = off_pass.rank(ascending=False, method='min')
        off_rush_ranks = off_rush.rank(ascending=False, method='min')
        
        def_total_ranks = def_total.rank(ascending=True, method='min')
        def_pass_ranks = def_pass.rank(ascending=True, method='min')
        def_rush_ranks = def_rush.rank(ascending=True, method='min')
        
        epa_map = {}
        for team_name in off_total.index:
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

def extract_team_metrics(team_name, league, global_stats):
    """Extracts and structures team metrics into a flat dict."""
    team_lower = team_name.lower().replace("state", "st")
    mascot = team_name.lower().split()[-1]
    
    matched_tr = None
    for k in sorted(global_stats["off_ppg"].keys(), key=len, reverse=True):
        if k == team_lower or f"{k} " in f"{team_lower} ":
            matched_tr = k
            break
            
    tr_data = {
        "off_ppg": global_stats["off_ppg"].get(matched_tr, {"rank": "-", "value": "N/A"}),
        "def_ppg": global_stats["def_ppg"].get(matched_tr, {"rank": "-", "value": "N/A"}),
        "off_ypg": global_stats["off_ypg"].get(matched_tr, {"rank": "-", "value": "N/A"}),
        "def_ypg": global_stats["def_ypg"].get(matched_tr, {"rank": "-", "value": "N/A"})
    }

    epa_data = None
    if "epa" in global_stats:
        if league.lower() == "nfl":
            epa_data = global_stats["epa"].get(mascot)
        else:
            for k, data in global_stats["epa"].items():
                if k in team_lower or team_lower in k:
                    epa_data = data
                    break

    return {"tr": tr_data, "epa": epa_data}

def build_matchup_stats_html(away_team, home_team, league, global_stats):
    """Builds a compact, 2-column side-by-side matchup table."""
    away_data = extract_team_metrics(away_team, league, global_stats)
    home_data = extract_team_metrics(home_team, league, global_stats)
    
    if away_data["tr"]["off_ppg"]["value"] == "N/A" and home_data["tr"]["off_ppg"]["value"] == "N/A":
        return ""

    def get_rank_color(rank_str):
        if not str(rank_str).isdigit(): return "#718096"
        rank = int(rank_str)
        
        if league.upper() == "NFL":
            # 32 teams: Top 12 green, Bottom 8 red
            if rank <= 12: return "#2e7d32" 
            if rank >= 25: return "#c62828" 
        else:
            # 138 FBS teams: Top 30 green, Bottom 39 red
            if rank <= 30: return "#2e7d32"
            if rank >= 100: return "#c62828"
            
        return "#4a5568"

    rows = []
    has_epa = away_data["epa"] or home_data["epa"]
    
    if has_epa:
        a_epa = away_data["epa"] or {}
        h_epa = home_data["epa"] or {}
        rows.extend([
            ("Offense Pass (EPA)", a_epa.get('off_pass', '-'), a_epa.get('off_pass_rank', '-'),
                                   h_epa.get('off_pass', '-'), h_epa.get('off_pass_rank', '-')),
            ("Offense Rush (EPA)", a_epa.get('off_rush', '-'), a_epa.get('off_rush_rank', '-'),
                                   h_epa.get('off_rush', '-'), h_epa.get('off_rush_rank', '-')),
            ("Offense Total (EPA)", a_epa.get('off_total', '-'), a_epa.get('off_total_rank', '-'),
                                    h_epa.get('off_total', '-'), h_epa.get('off_total_rank', '-')),
            ("DIVIDER", "", "", "", ""),
            ("Defense Pass (EPA)", a_epa.get('def_pass', '-'), a_epa.get('def_pass_rank', '-'),
                                   h_epa.get('def_pass', '-'), h_epa.get('def_pass_rank', '-')),
            ("Defense Rush (EPA)", a_epa.get('def_rush', '-'), a_epa.get('def_rush_rank', '-'),
                                   h_epa.get('def_rush', '-'), h_epa.get('def_rush_rank', '-')),
            ("Defense Total (EPA)", a_epa.get('def_total', '-'), a_epa.get('def_total_rank', '-'),
                                    h_epa.get('def_total', '-'), h_epa.get('def_total_rank', '-')),
            ("DIVIDER", "", "", "", "")
        ])

    rows.extend([
        ("Scoring (PPG)", away_data["tr"]["off_ppg"]["value"], away_data["tr"]["off_ppg"]["rank"],
                          home_data["tr"]["off_ppg"]["value"], home_data["tr"]["off_ppg"]["rank"]),
        ("Opp Scoring (PPG)", away_data["tr"]["def_ppg"]["value"], away_data["tr"]["def_ppg"]["rank"],
                              home_data["tr"]["def_ppg"]["value"], home_data["tr"]["def_ppg"]["rank"]),
        ("Total Yards (YPG)", away_data["tr"]["off_ypg"]["value"], away_data["tr"]["off_ypg"]["rank"],
                              home_data["tr"]["off_ypg"]["value"], home_data["tr"]["off_ypg"]["rank"]),
        ("Opp Yards (YPG)", away_data["tr"]["def_ypg"]["value"], away_data["tr"]["def_ypg"]["rank"],
                            home_data["tr"]["def_ypg"]["value"], home_data["tr"]["def_ypg"]["rank"])
    ])

    html = f"""
    <div style="margin: 12px 0 8px 0; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
        <table style="width: 100%; border-collapse: collapse; font-size: 11px; text-align: center;">
            <thead>
                <tr style="background-color: #2d3748; color: #ffffff;">
                    <th style="padding: 6px 8px; width: 35%; text-align: left;">{away_team}</th>
                    <th style="padding: 6px 4px; width: 30%; color: #cbd5e0; font-weight: normal;">Category</th>
                    <th style="padding: 6px 8px; width: 35%; text-align: right;">{home_team}</th>
                </tr>
            </thead>
            <tbody>
    """

    for label, a_val, a_rk, h_val, h_rk in rows:
        if label == "DIVIDER":
            html += '<tr style="background-color: #edf2f7; height: 3px;"><td colspan="3"></td></tr>'
            continue

        a_col = get_rank_color(a_rk)
        h_col = get_rank_color(h_rk)

        a_cell = f"<strong style='color:{a_col};'>#{a_rk}</strong> ({a_val})" if str(a_rk).isdigit() else f"({a_val})"
        h_cell = f"({h_val}) <strong style='color:{h_col};'>#{h_rk}</strong>" if str(h_rk).isdigit() else f"({h_val})"

        html += f"""
        <tr style="border-bottom: 1px solid #edf2f7;">
            <td style="padding: 4px 8px; text-align: left;">{a_cell}</td>
            <td style="padding: 4px 4px; color: #718096; font-size: 10px;">{label}</td>
            <td style="padding: 4px 8px; text-align: right;">{h_cell}</td>
        </tr>
        """

    html += "</tbody></table></div>"
    return html

# --- TEST BLOCK ---
if __name__ == '__main__':
    print("🚀 Booting up Football Stats Submodule...\n")
    
    nfl_global_stats = fetch_all_league_stats("NFL")
    cfb_global_stats = fetch_all_league_stats("NCAAF")
    
    test_matchups = [
        ("Philadelphia Eagles", "Chicago Bears", "NFL", nfl_global_stats),
        ("Indiana Hoosiers", "Ohio State Buckeyes", "NCAAF", cfb_global_stats)
    ]
    
    for away, home, league, global_dict in test_matchups:
        html_block = build_matchup_stats_html(away, home, league, global_dict)
        print(f"\n--- {away} vs {home} ---")
        print(html_block)
        
    print("\n✅ Module execution complete.")