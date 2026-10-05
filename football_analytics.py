import datetime
import io
import os
import re
import requests

# ==========================================
# CONFIGURATION & API KEYS
# ==========================================
CFBD_API_KEY = "LrFNn3N2V22VOBJ3r6a+dmw4iUsD84uV5YZdSbROZQacDHu1f3h2wbciIHRQzQsy"

def fetch_nfl_stats():
    """Calculates Success Rate and YPG via nflreadpy, then overwrites EPA and PPG with nfelo's opponent-adjusted HTML data."""
    try:
        import nflreadpy as nfl
        import pandas as pd
    except ImportError:
        print("⚠️ nflreadpy not installed.")
        return {}
        
    print("📊 Calculating NFL advanced metrics via nflreadpy...")
    import datetime
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
    
    # 1. GENERATE BASE DICTIONARY WITH NFLREADPY (For Success Rate, YPG, and Fallback EPA)
    try:
        pbp = nfl.load_pbp([current_year]).to_pandas()
        pbp_valid = pbp.dropna(subset=['epa', 'play_type'])
        pbp_valid = pbp_valid[pbp_valid['play_type'].isin(['pass', 'run'])]
        
        # Raw EPA calculation
        off_total = pbp_valid.groupby('posteam')['epa'].mean()
        def_total = pbp_valid.groupby('defteam')['epa'].mean()
        
        # --- NEW: Fallback Net EPA (Offense minus Defense EPA allowed) ---
        net_total = off_total.subtract(def_total, fill_value=0.0)

        off_ypg = pbp_valid.groupby(['posteam', 'game_id'])['yards_gained'].sum().groupby(level=0).mean()
        def_ypg = pbp_valid.groupby(['defteam', 'game_id'])['yards_gained'].sum().groupby(level=0).mean()

        if 'success' not in pbp_valid.columns:
            pbp_valid['success'] = (pbp_valid['epa'] > 0).astype(int)
            
        off_success = (pbp_valid.groupby('posteam')['success'].mean() * 100)
        def_success = (pbp_valid.groupby('defteam')['success'].mean() * 100)

        ranks = {
            'off_ypg': off_ypg.rank(ascending=False, method='min'),
            'def_ypg': def_ypg.rank(ascending=True, method='min'),
            'off_success': off_success.rank(ascending=False, method='min'),
            'def_success': def_success.rank(ascending=True, method='min'),
            'net_epa': net_total.rank(ascending=False, method='min')  # <-- NEW: Fallback Rank
        }

        stats_map = {}
        for abbr, mascot in nfl_mascot_map.items():
            if abbr in off_ypg:
                stats_map[mascot] = {
                    "off_ypg": f"{off_ypg.get(abbr, 0):.1f}", "off_ypg_rank": f"{int(ranks['off_ypg'].get(abbr, 99))}",
                    "def_ypg": f"{def_ypg.get(abbr, 0):.1f}", "def_ypg_rank": f"{int(ranks['def_ypg'].get(abbr, 99))}",
                    "off_success": f"{off_success.get(abbr, 0):.1f}%", "off_success_rank": f"{int(ranks['off_success'].get(abbr, 99))}",
                    "def_success": f"{def_success.get(abbr, 0):.1f}%", "def_success_rank": f"{int(ranks['def_success'].get(abbr, 99))}",
                    
                    # --- NEW: Placeholders for Net EPA ---
                    "net_epa": f"{net_total.get(abbr, 0):.2f}",
                    "net_epa_rank": f"{int(ranks['net_epa'].get(abbr, 99))}",
                    
                    # Placeholders for nfelo overrides
                    "off_total": f"{off_total.get(abbr, 0):.2f}", "off_total_rank": "99",
                    "off_pass": "-", "off_pass_rank": "99",
                    "off_rush": "-", "off_rush_rank": "99",
                    "def_total": f"{def_total.get(abbr, 0):.2f}", "def_total_rank": "99",
                    "def_pass": "-", "def_pass_rank": "99",
                    "def_rush": "-", "def_rush_rank": "99",
                    "off_ppg": "-", "off_ppg_rank": "99",
                    "def_ppg": "-", "def_ppg_rank": "99"
                }
    except Exception as e:
        print(f"⚠️ Error calculating NFL metrics natively: {e}")
        return {}

    # 2. OVERWRITE WITH NFELO OPPONENT-ADJUSTED DATA (Scraping)
    try:
        print("🧮 Fetching Opponent-Adjusted EPA and PPG from nfelo HTML...")
        import requests
        import io
        import re
        
        nfelo_url = "https://www.nfeloapp.com/nfl-power-ratings/"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(nfelo_url, headers=headers, timeout=10)
        
        # Regex replacement to extract text from image tags before pandas parses the tables
        html_text = re.sub(r'<img[^>]+alt="([^"]+)"[^>]*>', r'\1', res.text)
        html_text = re.sub(r'<img[^>]+src="[^"]*/([A-Za-z0-9_]+)\.[a-z]{3,4}"[^>]*>', r' \1 ', html_text)
        
        dfs = pd.read_html(io.StringIO(html_text))
        nfelo_df = dfs[0] 
        
        if isinstance(nfelo_df.columns, pd.MultiIndex):
            nfelo_df.columns = ['_'.join(col).strip() for col in nfelo_df.columns.values]
            
        team_col = [c for c in nfelo_df.columns if 'Team' in c][0]
        
        # Identify columns
        off_play_col = [c for c in nfelo_df.columns if 'Offensive' in c and 'Play' in c][0]
        off_pass_col = [c for c in nfelo_df.columns if 'Offensive' in c and 'Pass' in c][0]
        off_rush_col = [c for c in nfelo_df.columns if 'Offensive' in c and 'Rush' in c][0]
        
        def_play_col = [c for c in nfelo_df.columns if 'Defensive' in c and 'Play' in c][0]
        def_pass_col = [c for c in nfelo_df.columns if 'Defensive' in c and 'Pass' in c][0]
        def_rush_col = [c for c in nfelo_df.columns if 'Defensive' in c and 'Rush' in c][0]
        
        ppg_for_col = [c for c in nfelo_df.columns if 'For' in c.split('_') or 'For' in c][0]
        ppg_against_col = [c for c in nfelo_df.columns if 'Against' in c.split('_') or 'Against' in c][0]

        # --- NEW: Identify the Net EPA Play column (the yellow highlighted column) ---
        net_epa_col = next((c for c in nfelo_df.columns if 'Offensive' not in c and 'Defensive' not in c and 'Play' in c and 'EPA' in c), None)
        if not net_epa_col:
            # Fallback calculation if column name changes
            nfelo_df['Net_EPA_Play'] = nfelo_df[off_play_col] - nfelo_df[def_play_col]
            net_epa_col = 'Net_EPA_Play'

        # Calculate ranks natively inside pandas for the nfelo metrics
        nfelo_df['off_tot_rk'] = nfelo_df[off_play_col].rank(ascending=False, method='min')
        nfelo_df['off_pass_rk'] = nfelo_df[off_pass_col].rank(ascending=False, method='min')
        nfelo_df['off_rush_rk'] = nfelo_df[off_rush_col].rank(ascending=False, method='min')
        
        nfelo_df['def_tot_rk'] = nfelo_df[def_play_col].rank(ascending=True, method='min')
        nfelo_df['def_pass_rk'] = nfelo_df[def_pass_col].rank(ascending=True, method='min')
        nfelo_df['def_rush_rk'] = nfelo_df[def_rush_col].rank(ascending=True, method='min')
        
        nfelo_df['off_ppg_rk'] = nfelo_df[ppg_for_col].rank(ascending=False, method='min')
        nfelo_df['def_ppg_rk'] = nfelo_df[ppg_against_col].rank(ascending=True, method='min')

        # --- NEW: Rank Net EPA 1-32 descending ---
        nfelo_df['net_epa_rk'] = nfelo_df[net_epa_col].rank(ascending=False, method='min')

        for idx, row in nfelo_df.iterrows():
            team_str = str(row[team_col]).lower()
            
            for mascot in stats_map.keys():
                if mascot in team_str or mascot[:3] in team_str:
                    stats_map[mascot].update({
                        "off_total": f"{float(row[off_play_col]):.3f}",
                        "off_total_rank": f"{int(row['off_tot_rk'])}",
                        "off_pass": f"{float(row[off_pass_col]):.3f}",
                        "off_pass_rank": f"{int(row['off_pass_rk'])}",
                        "off_rush": f"{float(row[off_rush_col]):.3f}",
                        "off_rush_rank": f"{int(row['off_rush_rk'])}",
                        
                        "def_total": f"{float(row[def_play_col]):.3f}",
                        "def_total_rank": f"{int(row['def_tot_rk'])}",
                        "def_pass": f"{float(row[def_pass_col]):.3f}",
                        "def_pass_rank": f"{int(row['def_pass_rk'])}",
                        "def_rush": f"{float(row[def_rush_col]):.3f}",
                        "def_rush_rank": f"{int(row['def_rush_rk'])}",
                        
                        "off_ppg": f"{float(row[ppg_for_col]):.1f}",
                        "off_ppg_rank": f"{int(row['off_ppg_rk'])}",
                        "def_ppg": f"{float(row[ppg_against_col]):.1f}",
                        "def_ppg_rank": f"{int(row['def_ppg_rk'])}",

                        # --- NEW: Overwrite with nfelo Net EPA & Rank ---
                        "net_epa": f"{float(row[net_epa_col]):.3f}",
                        "net_epa_rank": f"{int(row['net_epa_rk'])}"
                    })
                    break
                    
    except Exception as e:
        print(f"⚠️ Error parsing nfelo HTML overrides: {e}")

    return stats_map

def fetch_cfb_stats():
    """Calculates granular EPA, PPG, and YPG natively via sportsdataverse, then overrides with CFBD Opponent-Adjusted WEPA."""
    try:
        import sportsdataverse as sdv
        import pandas as pd
        import requests
        import datetime
        import os
    except ImportError:
        print("⚠️ Required libraries not installed.")
        return {}
        
    print("📊 Calculating CFB traditional metrics via sportsdataverse...")
    current_year = datetime.datetime.now().year
    
    # Reads global CFBD_API_KEY from top of script, or falls back to environment variable
    api_key = globals().get("CFBD_API_KEY")
    if not api_key or api_key == "YOUR_ACTUAL_API_KEY_HERE":
        api_key = os.environ.get("CFBD_API_KEY")

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

        yards_col = 'yards_gained'
        for col in ['yards_gained', 'statYardage', 'yards', 'yds', 'net_yards', 'yds_gained']:
            if col in pbp.columns:
                yards_col = col
                break

        # --- NATIVE EPA, YARDS & SUCCESS RATE CALCULATION (Safety Fallback) ---
        pbp_valid = pbp.dropna(subset=[epa_col, play_type_col]).copy()
        pbp_valid['is_pass'] = pbp_valid[play_type_col].astype(str).str.contains('Pass|Sack', case=False, na=False)
        pbp_valid['is_rush'] = pbp_valid[play_type_col].astype(str).str.contains('Rush', case=False, na=False)
        pbp_valid = pbp_valid[pbp_valid['is_pass'] | pbp_valid['is_rush']]
        
        off_total = pbp_valid.groupby(pos_team_col)[epa_col].mean().round(3)
        off_pass = pbp_valid[pbp_valid['is_pass']].groupby(pos_team_col)[epa_col].mean().round(3)
        off_rush = pbp_valid[pbp_valid['is_rush']].groupby(pos_team_col)[epa_col].mean().round(3)
        
        def_total = pbp_valid.groupby(def_team_col)[epa_col].mean().round(3)
        def_pass = pbp_valid[pbp_valid['is_pass']].groupby(def_team_col)[epa_col].mean().round(3)
        def_rush = pbp_valid[pbp_valid['is_rush']].groupby(def_team_col)[epa_col].mean().round(3)

        off_ypg = pbp_valid.groupby([pos_team_col, 'game_id'])[yards_col].sum().groupby(level=0).mean().round(1)
        def_ypg = pbp_valid.groupby([def_team_col, 'game_id'])[yards_col].sum().groupby(level=0).mean().round(1)

        if 'success' not in pbp_valid.columns:
            pbp_valid['success'] = (pbp_valid[epa_col] > 0).astype(int)
            
        off_success = (pbp_valid.groupby(pos_team_col)['success'].mean() * 100).round(1)
        def_success = (pbp_valid.groupby(def_team_col)['success'].mean() * 100).round(1)

        # --- PPG CALCULATION (STRICTLY FBS vs FBS GAMES) ---
        home_pts_col = next((c for c in ['home_points', 'home_score', 'homeScore'] if c in sched.columns), 'home_points')
        away_pts_col = next((c for c in ['away_points', 'away_score', 'awayScore'] if c in sched.columns), 'away_points')
        home_team_col = next((c for c in ['home_team', 'homeTeam', 'home_team_name'] if c in sched.columns), 'home_team')
        away_team_col = next((c for c in ['away_team', 'awayTeam', 'away_team_name'] if c in sched.columns), 'away_team')

        home_class_col = next((c for c in sched.columns if c.lower() in ['home_classification', 'home_team_classification', 'home_division']), None)
        away_class_col = next((c for c in sched.columns if c.lower() in ['away_classification', 'away_team_classification', 'away_division']), None)

        sched_played = sched.dropna(subset=[home_pts_col, away_pts_col]).copy()
        
        if home_class_col and away_class_col:
            sched_played['home_is_fbs'] = sched_played[home_class_col].astype(str).str.lower().str.contains('fbs', na=True)
            sched_played['away_is_fbs'] = sched_played[away_class_col].astype(str).str.lower().str.contains('fbs', na=True)
        else:
            sched_played['home_is_fbs'] = True
            sched_played['away_is_fbs'] = True

        sched_fbs = sched_played[sched_played['home_is_fbs'] & sched_played['away_is_fbs']].copy()
        
        home_pts = sched_fbs.groupby(home_team_col)[home_pts_col].sum()
        home_gp = sched_fbs.groupby(home_team_col)['game_id'].count()
        
        away_pts = sched_fbs.groupby(away_team_col)[away_pts_col].sum()
        away_gp = sched_fbs.groupby(away_team_col)['game_id'].count()
        
        tot_pts = home_pts.add(away_pts, fill_value=0)
        tot_gp = home_gp.add(away_gp, fill_value=0)
        
        tot_allowed_home = sched_fbs.groupby(home_team_col)[away_pts_col].sum()
        tot_allowed_away = sched_fbs.groupby(away_team_col)[home_pts_col].sum()
        
        tot_allowed = tot_allowed_home.add(tot_allowed_away, fill_value=0)
        
        valid_teams = tot_gp[tot_gp > 0].index
        off_ppg = (tot_pts[valid_teams] / tot_gp[valid_teams]).round(1)
        def_ppg = (tot_allowed[valid_teams] / tot_gp[valid_teams]).round(1)

        # --- NATIVE RANKINGS ---
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
            'def_ppg': def_ppg.rank(ascending=True, method='min'),
            'off_success': off_success.rank(ascending=False, method='min'),
            'def_success': def_success.rank(ascending=True, method='min')
        }

        # Build initial map with native stats
        stats_map = {}
        for team_name in off_ypg.index:
            clean_name = str(team_name).lower().replace("state", "st")
            t_off_ppg, t_def_ppg = off_ppg.get(team_name, 0.0), def_ppg.get(team_name, 0.0)
            t_off_ppg_rk, t_def_ppg_rk = ranks['off_ppg'].get(team_name, 999), ranks['def_ppg'].get(team_name, 999)
            
            if team_name not in off_ppg:
                for st, val in off_ppg.items():
                    if str(team_name).lower() in str(st).lower() or str(st).lower() in str(team_name).lower():
                        t_off_ppg = val
                        t_def_ppg = def_ppg.get(st, 0.0)
                        t_off_ppg_rk = ranks['off_ppg'].get(st, 999)
                        t_def_ppg_rk = ranks['def_ppg'].get(st, 999)
                        break

            stats_map[clean_name] = {
                "off_ypg": f"{off_ypg.get(team_name, 0):.1f}", "off_ypg_rank": f"{int(ranks['off_ypg'].get(team_name, 999))}",
                "def_ypg": f"{def_ypg.get(team_name, 0):.1f}", "def_ypg_rank": f"{int(ranks['def_ypg'].get(team_name, 999))}",
                "off_ppg": f"{t_off_ppg:.1f}", "off_ppg_rank": f"{int(t_off_ppg_rk)}",
                "def_ppg": f"{t_def_ppg:.1f}", "def_ppg_rank": f"{int(t_def_ppg_rk)}",
                "off_total": f"{off_total.get(team_name, 0):.2f}", "off_total_rank": f"{int(ranks['off_total'].get(team_name, 999))}",
                "off_pass": f"{off_pass.get(team_name, 0):.2f}", "off_pass_rank": f"{int(ranks['off_pass'].get(team_name, 999))}",
                "off_rush": f"{off_rush.get(team_name, 0):.2f}", "off_rush_rank": f"{int(ranks['off_rush'].get(team_name, 999))}",
                "def_total": f"{def_total.get(team_name, 0):.2f}", "def_total_rank": f"{int(ranks['def_total'].get(team_name, 999))}",
                "def_pass": f"{def_pass.get(team_name, 0):.2f}", "def_pass_rank": f"{int(ranks['def_pass'].get(team_name, 999))}",
                "def_rush": f"{def_rush.get(team_name, 0):.2f}", "def_rush_rank": f"{int(ranks['def_rush'].get(team_name, 999))}",
                "off_success": f"{off_success.get(team_name, 0):.1f}%", "off_success_rank": f"{int(ranks['off_success'].get(team_name, 999))}",
                "def_success": f"{def_success.get(team_name, 0):.1f}%", "def_success_rank": f"{int(ranks['def_success'].get(team_name, 999))}"
            }
            
        # --- OVERWRITE WITH CFBD OPPONENT-ADJUSTED METRICS VIA API ---
        if api_key and api_key != "YOUR_ACTUAL_API_KEY_HERE":
            print("🧮 Fetching Opponent-Adjusted stats from CFBD API...")
            headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
            api_url = f"https://api.collegefootballdata.com/stats/season/advanced?year={current_year}"
            res = requests.get(api_url, headers=headers)
            
            if res.status_code == 200:
                cfbd_data = res.json()
                cfbd_df = pd.json_normalize(cfbd_data)
                
                off_tot = 'offense.ppa'
                off_pass = 'offense.passingPlays.ppa'
                off_rush = 'offense.rushingPlays.ppa'
                off_sr = 'offense.successRate'
                
                def_tot = 'defense.ppa'
                def_pass = 'defense.passingPlays.ppa'
                def_rush = 'defense.rushingPlays.ppa'
                def_sr = 'defense.successRate'
                
                cfbd_df['off_tot_rk'] = cfbd_df[off_tot].rank(ascending=False, method='min')
                cfbd_df['off_pass_rk'] = cfbd_df[off_pass].rank(ascending=False, method='min')
                cfbd_df['off_rush_rk'] = cfbd_df[off_rush].rank(ascending=False, method='min')
                cfbd_df['off_sr_rk'] = cfbd_df[off_sr].rank(ascending=False, method='min')
                
                cfbd_df['def_tot_rk'] = cfbd_df[def_tot].rank(ascending=True, method='min')
                cfbd_df['def_pass_rk'] = cfbd_df[def_pass].rank(ascending=True, method='min')
                cfbd_df['def_rush_rk'] = cfbd_df[def_rush].rank(ascending=True, method='min')
                cfbd_df['def_sr_rk'] = cfbd_df[def_sr].rank(ascending=True, method='min')
                
                for idx, row in cfbd_df.iterrows():
                    team_raw = str(row.get('team', '')).lower()
                    team_clean = team_raw.replace("state", "st")
                    
                    target_key = None
                    if team_clean in stats_map:
                        target_key = team_clean
                    elif team_raw in stats_map:
                        target_key = team_raw
                    else:
                        for k in stats_map:
                            if k in team_clean or team_clean in k or k in team_raw or team_raw in k:
                                target_key = k
                                break
                                
                    if target_key:
                        stats_map[target_key]["off_total"] = f"{float(row[off_tot]):.3f}"
                        stats_map[target_key]["off_total_rank"] = f"{int(row['off_tot_rk'])}"
                        stats_map[target_key]["off_pass"] = f"{float(row[off_pass]):.3f}"
                        stats_map[target_key]["off_pass_rank"] = f"{int(row['off_pass_rk'])}"
                        stats_map[target_key]["off_rush"] = f"{float(row[off_rush]):.3f}"
                        stats_map[target_key]["off_rush_rank"] = f"{int(row['off_rush_rk'])}"
                        stats_map[target_key]["off_success"] = f"{float(row[off_sr])*100:.1f}%"
                        stats_map[target_key]["off_success_rank"] = f"{int(row['off_sr_rk'])}"
                        
                        stats_map[target_key]["def_total"] = f"{float(row[def_tot]):.3f}"
                        stats_map[target_key]["def_total_rank"] = f"{int(row['def_tot_rk'])}"
                        stats_map[target_key]["def_pass"] = f"{float(row[def_pass]):.3f}"
                        stats_map[target_key]["def_pass_rank"] = f"{int(row['def_pass_rk'])}"
                        stats_map[target_key]["def_rush"] = f"{float(row[def_rush]):.3f}"
                        stats_map[target_key]["def_rush_rank"] = f"{int(row['def_rush_rk'])}"
                        stats_map[target_key]["def_success"] = f"{float(row[def_sr])*100:.1f}%"
                        stats_map[target_key]["def_success_rank"] = f"{int(row['def_sr_rk'])}"
                        
        return stats_map
    except Exception as e:
        print(f"⚠️ Error calculating CFB metrics: {e}")
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
        for k, v in global_stats.items():
            if k in away_lower or away_lower in k:
                away_data = v
            if k in home_lower or home_lower in k:
                home_data = v
                
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
        ("Offense Pass (Adj EPA)", away_data.get('off_pass', '-'), away_data.get('off_pass_rank', '-'),
                                   home_data.get('off_pass', '-'), home_data.get('off_pass_rank', '-')),
        ("Offense Rush (Adj EPA)", away_data.get('off_rush', '-'), away_data.get('off_rush_rank', '-'),
                                   home_data.get('off_rush', '-'), home_data.get('off_rush_rank', '-')),
        ("Offense Total (Adj EPA)", away_data.get('off_total', '-'), away_data.get('off_total_rank', '-'),
                                    home_data.get('off_total', '-'), home_data.get('off_total_rank', '-')),
        ("Offense Success (%)", away_data.get('off_success', '-'), away_data.get('off_success_rank', '-'),
                                home_data.get('off_success', '-'), home_data.get('off_success_rank', '-')),
        ("DIVIDER", "", "", "", ""),
        ("Defense Pass (Adj EPA)", away_data.get('def_pass', '-'), away_data.get('def_pass_rank', '-'),
                                   home_data.get('def_pass', '-'), home_data.get('def_pass_rank', '-')),
        ("Defense Rush (Adj EPA)", away_data.get('def_rush', '-'), away_data.get('def_rush_rank', '-'),
                                   home_data.get('def_rush', '-'), home_data.get('def_rush_rank', '-')),
        ("Defense Total (Adj EPA)", away_data.get('def_total', '-'), away_data.get('def_total_rank', '-'),
                                    home_data.get('def_total', '-'), home_data.get('def_total_rank', '-')),
        ("Defense Success (%)", away_data.get('def_success', '-'), away_data.get('def_success_rank', '-'),
                                home_data.get('def_success', '-'), home_data.get('def_success_rank', '-')),
        ("DIVIDER", "", "", "", ""),
        ("Scoring (Adj PPG)", away_data.get('off_ppg', '-'), away_data.get('off_ppg_rank', '-'),
                              home_data.get('off_ppg', '-'), home_data.get('off_ppg_rank', '-')),
        ("Opp Scoring (Adj PPG)", away_data.get('def_ppg', '-'), away_data.get('def_ppg_rank', '-'),
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
    
    full_html = "<div style='max-width: 800px; margin: auto;'>"
    for away, home, league, global_dict in test_matchups:
        html_block = build_matchup_stats_html(away, home, league, global_dict)
        full_html += f"<h3 style='font-family: sans-serif; text-align: center;'>{league} Matchup</h3>" + html_block
    full_html += "</div>"
        
    with open("test_matchups.html", "w", encoding="utf-8") as f:
        f.write(full_html)
        
    print("\n✅ Native module execution complete. Open 'test_matchups.html' in your folder to view the visually rendered tables!")