import datetime

def fetch_nfl_stats():
    """Calculates granular EPA, PPG, and YPG directly from nflreadpy."""
    try:
        import nflreadpy as nfl
        import pandas as pd
    except ImportError:
        print("⚠️ nflreadpy not installed. Run 'pip install nflreadpy pandas pyarrow'.")
        return {}
        
    print("📊 Calculating NFL advanced and traditional metrics via nflreadpy...")
    current_year = datetime.datetime.now().year
    
    nfl_mascot_map = {
        'ARI': 'cardinals', 'ATL': 'falcons', 'BAL': 'ravens', 'BUF': 'bills',
        'CAR': 'panthers', 'CHI': 'bears', 'CIN': 'bengals', 'CLE': 'browns',
        'DAL': 'cowboys', 'DEN': 'broncos', 'DET': 'lions', 'GB': 'packers',
        'HOU': 'texans', 'IND': 'colts', 'JAX': 'jaguars', 'KC': 'chiefs',
        'LV': 'raiders', 'LAC': 'chargers', 'LA': 'rams', 'MIA': 'dolphins',
        'MIN': 'vikings', 'NE': 'patriots', 'NO': 'saints', 'NYG': 'giants',
        'NYJ': 'jets', 'PHI': 'eagles', 'PIT': 'steelers', 'SF': '49ers',
        'SEA': 'seahawks', 'TB': 'buccaneers', 'TEN': 'titans', 'WAS': 'commanders'
    }
    
    try:
        pbp = nfl.load_pbp([current_year]).to_pandas()
        sched = nfl.load_schedules([current_year]).to_pandas()
        
        # --- EPA & YARDS CALCULATION ---
        pbp_valid = pbp.dropna(subset=['epa', 'play_type'])
        pbp_valid = pbp_valid[pbp_valid['play_type'].isin(['pass', 'run'])]
        
        off_total = pbp_valid.groupby('posteam')['epa'].mean().round(3)
        off_pass = pbp_valid[pbp_valid['play_type'] == 'pass'].groupby('posteam')['epa'].mean().round(3)
        off_rush = pbp_valid[pbp_valid['play_type'] == 'run'].groupby('posteam')['epa'].mean().round(3)
        
        def_total = pbp_valid.groupby('defteam')['epa'].mean().round(3)
        def_pass = pbp_valid[pbp_valid['play_type'] == 'pass'].groupby('defteam')['epa'].mean().round(3)
        def_rush = pbp_valid[pbp_valid['play_type'] == 'run'].groupby('defteam')['epa'].mean().round(3)

        off_ypg = pbp_valid.groupby(['posteam', 'game_id'])['yards_gained'].sum().groupby(level=0).mean().round(1)
        def_ypg = pbp_valid.groupby(['defteam', 'game_id'])['yards_gained'].sum().groupby(level=0).mean().round(1)

        # --- PPG CALCULATION ---
        sched_played = sched.dropna(subset=['home_score', 'away_score'])
        
        home_pts = sched_played.groupby('home_team')['home_score'].sum()
        away_pts = sched_played.groupby('away_team')['away_score'].sum()
        home_gp = sched_played.groupby('home_team')['game_id'].count()
        away_gp = sched_played.groupby('away_team')['game_id'].count()
        
        tot_pts = home_pts.add(away_pts, fill_value=0)
        tot_gp = home_gp.add(away_gp, fill_value=0)
        tot_allowed = sched_played.groupby('home_team')['away_score'].sum().add(sched_played.groupby('away_team')['home_score'].sum(), fill_value=0)
        
        off_ppg = (tot_pts / tot_gp).round(1)
        def_ppg = (tot_allowed / tot_gp).round(1)

        # --- RANKINGS ---
        ranks = {
            'off_total': off_total.rank(ascending=False, method='min'),
            'off_pass': off_pass.rank(ascending=False, method='min'),
            'off_rush': off_rush.rank(ascending=False, method='min'),
            'def_total': def_total.rank(ascending=True, method='min'),
            'def_pass': def_pass.rank(ascending=True, method='min'),
            'def_rush': def_rush.rank(ascending=True, method='min'),
            'off_ypg': off_ypg.rank(ascending=False, method='min'),
            'def_ypg': def_ypg.rank(ascending=True, method='min'),
            'off_ppg': off_ppg.rank(ascending=False, method='min'),
            'def_ppg': def_ppg.rank(ascending=True, method='min')
        }

        stats_map = {}
        for abbr, mascot in nfl_mascot_map.items():
            if abbr in off_total:
                stats_map[mascot] = {
                    "off_total": f"{off_total.get(abbr, 0):.2f}", "off_total_rank": f"{int(ranks['off_total'].get(abbr, 99))}",
                    "off_pass": f"{off_pass.get(abbr, 0):.2f}", "off_pass_rank": f"{int(ranks['off_pass'].get(abbr, 99))}",
                    "off_rush": f"{off_rush.get(abbr, 0):.2f}", "off_rush_rank": f"{int(ranks['off_rush'].get(abbr, 99))}",
                    "def_total": f"{def_total.get(abbr, 0):.2f}", "def_total_rank": f"{int(ranks['def_total'].get(abbr, 99))}",
                    "def_pass": f"{def_pass.get(abbr, 0):.2f}", "def_pass_rank": f"{int(ranks['def_pass'].get(abbr, 99))}",
                    "def_rush": f"{def_rush.get(abbr, 0):.2f}", "def_rush_rank": f"{int(ranks['def_rush'].get(abbr, 99))}",
                    "off_ypg": f"{off_ypg.get(abbr, 0):.1f}", "off_ypg_rank": f"{int(ranks['off_ypg'].get(abbr, 99))}",
                    "def_ypg": f"{def_ypg.get(abbr, 0):.1f}", "def_ypg_rank": f"{int(ranks['def_ypg'].get(abbr, 99))}",
                    "off_ppg": f"{off_ppg.get(abbr, 0):.1f}", "off_ppg_rank": f"{int(ranks['off_ppg'].get(abbr, 99))}",
                    "def_ppg": f"{def_ppg.get(abbr, 0):.1f}", "def_ppg_rank": f"{int(ranks['def_ppg'].get(abbr, 99))}",
                }
        return stats_map
    except Exception as e:
        print(f"⚠️ Error calculating NFL metrics natively: {e}")
        return {}

def fetch_cfb_stats():
    """Calculates granular EPA, PPG, and YPG directly from sportsdataverse."""
    try:
        import sportsdataverse as sdv
    except ImportError:
        print("⚠️ sportsdataverse not installed. Run 'pip install sportsdataverse pandas'.")
        return {}
        
    print("📊 Calculating CFB advanced and traditional metrics via sportsdataverse...")
    current_year = datetime.datetime.now().year
    
    try:
        pbp = sdv.cfb.load_cfb_pbp(seasons=[current_year], return_as_pandas=True)
        sched = sdv.cfb.load_cfb_schedule(seasons=[current_year], return_as_pandas=True)
        
        # --- DYNAMIC COLUMN MAPPING ---
        epa_col = 'EPA' if 'EPA' in pbp.columns else 'epa'
        pos_team_col = 'pos_team' if 'pos_team' in pbp.columns else 'posteam'
        def_team_col = 'def_pos_team' if 'def_pos_team' in pbp.columns else 'defteam'
        
        play_type_col = 'play_type' if 'play_type' in pbp.columns else 'type_text'
        if play_type_col not in pbp.columns:
            play_type_col = [c for c in pbp.columns if 'type' in c.lower()][0]

        # Dynamically hunt for the yards column (handles both ESPN and CFBD formats)
        yards_col = 'yards_gained'
        for col in ['yards_gained', 'statYardage', 'yards', 'yds', 'net_yards', 'yds_gained']:
            if col in pbp.columns:
                yards_col = col
                break

        # --- EPA & YARDS CALCULATION ---
        pbp_valid = pbp.dropna(subset=[epa_col, play_type_col])
        pbp_valid['is_pass'] = pbp_valid[play_type_col].astype(str).str.contains('Pass|Sack', case=False, na=False)
        pbp_valid['is_rush'] = pbp_valid[play_type_col].astype(str).str.contains('Rush', case=False, na=False)
        pbp_valid = pbp_valid[pbp_valid['is_pass'] | pbp_valid['is_rush']]
        
        off_total = pbp_valid.groupby(pos_team_col)[epa_col].mean().round(3)
        off_pass = pbp_valid[pbp_valid['is_pass']].groupby(pos_team_col)[epa_col].mean().round(3)
        off_rush = pbp_valid[pbp_valid['is_rush']].groupby(pos_team_col)[epa_col].mean().round(3)
        
        def_total = pbp_valid.groupby(def_team_col)[epa_col].mean().round(3)
        def_pass = pbp_valid[pbp_valid['is_pass']].groupby(def_team_col)[epa_col].mean().round(3)
        def_rush = pbp_valid[pbp_valid['is_rush']].groupby(def_team_col)[epa_col].mean().round(3)

        # Aggregate Yards Per Game
        off_ypg = pbp_valid.groupby([pos_team_col, 'game_id'])[yards_col].sum().groupby(level=0).mean().round(1)
        def_ypg = pbp_valid.groupby([def_team_col, 'game_id'])[yards_col].sum().groupby(level=0).mean().round(1)

        # --- PPG CALCULATION ---
        # Dynamically hunt for scoring columns
        home_pts_col = 'home_points' if 'home_points' in sched.columns else 'home_score'
        away_pts_col = 'away_points' if 'away_points' in sched.columns else 'away_score'
        
        sched_played = sched.dropna(subset=[home_pts_col, away_pts_col])
        
        home_pts = sched_played.groupby('home_team')[home_pts_col].sum()
        away_pts = sched_played.groupby('away_team')[away_pts_col].sum()
        home_gp = sched_played.groupby('home_team')['game_id'].count()
        away_gp = sched_played.groupby('away_team')['game_id'].count()
        
        tot_pts = home_pts.add(away_pts, fill_value=0)
        tot_gp = home_gp.add(away_gp, fill_value=0)
        tot_allowed = sched_played.groupby('home_team')[away_pts_col].sum().add(sched_played.groupby('away_team')[home_pts_col].sum(), fill_value=0)
        
        off_ppg = (tot_pts / tot_gp).round(1)
        def_ppg = (tot_allowed / tot_gp).round(1)

        # --- RANKINGS ---
        ranks = {
            'off_total': off_total.rank(ascending=False, method='min'),
            'off_pass': off_pass.rank(ascending=False, method='min'),
            'off_rush': off_rush.rank(ascending=False, method='min'),
            'def_total': def_total.rank(ascending=True, method='min'),
            'def_pass': def_pass.rank(ascending=True, method='min'),
            'def_rush': def_rush.rank(ascending=True, method='min'),
            'off_ypg': off_ypg.rank(ascending=False, method='min'),
            'def_ypg': def_ypg.rank(ascending=True, method='min'),
            'off_ppg': off_ppg.rank(ascending=False, method='min'),
            'def_ppg': def_ppg.rank(ascending=True, method='min')
        }

        stats_map = {}
        for team_name in off_total.index:
            clean_name = str(team_name).lower().replace("state", "st")
            stats_map[clean_name] = {
                "off_total": f"{off_total.get(team_name, 0):.2f}", "off_total_rank": f"{int(ranks['off_total'].get(team_name, 999))}",
                "off_pass": f"{off_pass.get(team_name, 0):.2f}", "off_pass_rank": f"{int(ranks['off_pass'].get(team_name, 999))}",
                "off_rush": f"{off_rush.get(team_name, 0):.2f}", "off_rush_rank": f"{int(ranks['off_rush'].get(team_name, 999))}",
                "def_total": f"{def_total.get(team_name, 0):.2f}", "def_total_rank": f"{int(ranks['def_total'].get(team_name, 999))}",
                "def_pass": f"{def_pass.get(team_name, 0):.2f}", "def_pass_rank": f"{int(ranks['def_pass'].get(team_name, 999))}",
                "def_rush": f"{def_rush.get(team_name, 0):.2f}", "def_rush_rank": f"{int(ranks['def_rush'].get(team_name, 999))}",
                "off_ypg": f"{off_ypg.get(team_name, 0):.1f}", "off_ypg_rank": f"{int(ranks['off_ypg'].get(team_name, 999))}",
                "def_ypg": f"{def_ypg.get(team_name, 0):.1f}", "def_ypg_rank": f"{int(ranks['def_ypg'].get(team_name, 999))}",
                "off_ppg": f"{off_ppg.get(team_name, 0):.1f}", "off_ppg_rank": f"{int(ranks['off_ppg'].get(team_name, 999))}",
                "def_ppg": f"{def_ppg.get(team_name, 0):.1f}", "def_ppg_rank": f"{int(ranks['def_ppg'].get(team_name, 999))}",
            }
        return stats_map
    except Exception as e:
        print(f"⚠️ Error calculating CFB metrics natively: {e}")
        return {}


def fetch_all_league_stats(league):
    """Router for master stat building."""
    if league.lower() == "nfl":
        return fetch_nfl_stats()
    return fetch_cfb_stats()

def build_matchup_stats_html(away_team, home_team, league, global_stats):
    """Builds a compact, 2-column side-by-side matchup table."""
    away_lower = away_team.lower().replace("state", "st")
    home_lower = home_team.lower().replace("state", "st")
    
    away_data = {}
    home_data = {}

    if league.upper() == "NFL":
        away_data = global_stats.get(away_lower.split()[-1], {})
        home_data = global_stats.get(home_lower.split()[-1], {})
    else:
        # CFB requires fuzzy matching (e.g. mapping "indiana hoosiers" to "indiana")
        for k, v in global_stats.items():
            if k in away_lower or away_lower in k:
                away_data = v
            if k in home_lower or home_lower in k:
                home_data = v
                
    # Matchup card suppression fallback
    if not away_data and not home_data:
        return ""

    def get_rank_color(rank_str):
        if not str(rank_str).isdigit(): return "#718096"
        rank = int(rank_str)
        if league.upper() == "NFL":
            if rank <= 12: return "#2e7d32" 
            if rank >= 25: return "#c62828" 
        else:
            if rank <= 30: return "#2e7d32"
            if rank >= 100: return "#c62828"
        return "#4a5568"

    rows = [
        ("Offense Pass (EPA)", away_data.get('off_pass', '-'), away_data.get('off_pass_rank', '-'),
                               home_data.get('off_pass', '-'), home_data.get('off_pass_rank', '-')),
        ("Offense Rush (EPA)", away_data.get('off_rush', '-'), away_data.get('off_rush_rank', '-'),
                               home_data.get('off_rush', '-'), home_data.get('off_rush_rank', '-')),
        ("Offense Total (EPA)", away_data.get('off_total', '-'), away_data.get('off_total_rank', '-'),
                                home_data.get('off_total', '-'), home_data.get('off_total_rank', '-')),
        ("DIVIDER", "", "", "", ""),
        ("Defense Pass (EPA)", away_data.get('def_pass', '-'), away_data.get('def_pass_rank', '-'),
                               home_data.get('def_pass', '-'), home_data.get('def_pass_rank', '-')),
        ("Defense Rush (EPA)", away_data.get('def_rush', '-'), away_data.get('def_rush_rank', '-'),
                               home_data.get('def_rush', '-'), home_data.get('def_rush_rank', '-')),
        ("Defense Total (EPA)", away_data.get('def_total', '-'), away_data.get('def_total_rank', '-'),
                                home_data.get('def_total', '-'), home_data.get('def_total_rank', '-')),
        ("DIVIDER", "", "", "", ""),
        ("Scoring (PPG)", away_data.get('off_ppg', '-'), away_data.get('off_ppg_rank', '-'),
                          home_data.get('off_ppg', '-'), home_data.get('off_ppg_rank', '-')),
        ("Opp Scoring (PPG)", away_data.get('def_ppg', '-'), away_data.get('def_ppg_rank', '-'),
                              home_data.get('def_ppg', '-'), home_data.get('def_ppg_rank', '-')),
        ("Total Yards (YPG)", away_data.get('off_ypg', '-'), away_data.get('off_ypg_rank', '-'),
                              home_data.get('off_ypg', '-'), home_data.get('off_ypg_rank', '-')),
        ("Opp Yards (YPG)", away_data.get('def_ypg', '-'), away_data.get('def_ypg_rank', '-'),
                            home_data.get('def_ypg', '-'), home_data.get('def_ypg_rank', '-'))
    ]

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
    print("🚀 Booting up Native Football Stats Module...\n")
    
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
        
    print("\n✅ Native module execution complete.")