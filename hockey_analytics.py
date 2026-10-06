import pandas as pd
import numpy as np
import requests
import io

# --- TOP-LEVEL MODULE MAP ---
MP_MAP = {
    "anaheim ducks": "ANA", "boston bruins": "BOS", "buffalo sabres": "BUF", "calgary flames": "CGY",
    "carolina hurricanes": "CAR", "chicago blackhawks": "CHI", "colorado avalanche": "COL", 
    "columbus blue jackets": "CBJ", "dallas stars": "DAL", "detroit red wings": "DET", "edmonton oilers": "EDM",
    "florida panthers": "FLA", "los angeles kings": "LAK", "minnesota wild": "MIN", "montreal canadiens": "MTL",
    "nashville predators": "NSH", "new jersey devils": "NJD", "new york islanders": "NYI", "new york rangers": "NYR",
    "ottawa senators": "OTT", "philadelphia flyers": "PHI", "pittsburgh penguins": "PIT", "san jose sharks": "SJS",
    "seattle kraken": "SEA", "st. louis blues": "STL", "tampa bay lightning": "TBL", "toronto maple leafs": "TOR",
    "utah mammoth": "UTA", "utah hockey club": "UTA", "vancouver canucks": "VAN", "vegas golden knights": "VGK", 
    "washington capitals": "WSH", "winnipeg jets": "WPG"
}

def fetch_official_nhl_stats():
    """Fetches official team stats directly from the NHL APIs (Standings + Special Teams)."""
    stats_dict = {}
    
    # Endpoints
    standings_url = "https://api-web.nhle.com/v1/standings/now"
    stats_url = "https://api.nhle.com/stats/rest/en/team/summary?cayenneExp=seasonId=20262027%20and%20gameTypeId=2"
    
    try:
        # 1. Get Standings Data (Record and Goal Differential)
        res_standings = requests.get(standings_url, timeout=10)
        if res_standings.status_code == 200:
            standings = res_standings.json().get('standings', [])
            for team in standings:
                team_name = team.get('teamName', {}).get('default', '').lower()
                if not team_name:
                    continue
                    
                reg_wins = team.get('regulationWins', 0)
                losses = team.get('losses', 0)
                ot_losses = team.get('otLosses', 0)
                    
                stats_dict[team_name] = {
                    'goal_diff': team.get('goalDifferential', 0),
                    'reg_record': f"{reg_wins}-{losses}-{ot_losses}",
                    'pp_pct': 0.0, # Default until stats API populates
                    'pk_pct': 0.0  # Default until stats API populates
                }

        # 2. Get Special Teams Data from the Stats API
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/115.0.0.0 Safari/537.36"}
        res_stats = requests.get(stats_url, headers=headers, timeout=10)
        if res_stats.status_code == 200:
            stats_data = res_stats.json().get('data', [])
            for team in stats_data:
                team_name = team.get('teamFullName', '').lower()
                if team_name in stats_dict:
                    # The NHL API returns these as decimals (e.g. 0.250 for 25%), multiply by 100
                    stats_dict[team_name]['pp_pct'] = round(team.get('powerPlayPct', 0.0) * 100, 1)
                    stats_dict[team_name]['pk_pct'] = round(team.get('penaltyKillPct', 0.0) * 100, 1)

        return stats_dict
    except Exception as e:
        print(f"⚠️ NHL API Error: {e}")
        return {}

def fetch_moneypuck_stats():
    """Fetches live 5v5 advanced stats from MoneyPuck safely."""
    url = "https://moneypuck.com/moneypuck/playerData/seasonSummary/2026/regular/teams.csv"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/115.0.0.0 Safari/537.36"}
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            df = pd.read_csv(io.StringIO(res.text))
            df_5v5 = df[df['situation'] == '5on5'].copy()
            df_5v5['team'] = df_5v5['team'].astype(str).str.upper()
            
            # Base percentages
            if 'corsiPercentage' in df_5v5.columns:
                df_5v5['CF%'] = (pd.to_numeric(df_5v5['corsiPercentage'], errors='coerce') * 100).round(1)
            else:
                df_5v5['CF%'] = '-'
                
            if 'xGoalsPercentage' in df_5v5.columns:
                df_5v5['xGF%'] = (pd.to_numeric(df_5v5['xGoalsPercentage'], errors='coerce') * 100).round(1)
            else:
                df_5v5['xGF%'] = '-'
            
            # 1. High Danger xGF%
            if 'highDangerxGoalsPercentage' in df_5v5.columns:
                df_5v5['HD_xGF%'] = (pd.to_numeric(df_5v5['highDangerxGoalsPercentage'], errors='coerce') * 100).round(1)
            elif 'highDangerxGoalsFor' in df_5v5.columns and 'highDangerxGoalsAgainst' in df_5v5.columns:
                hd_for = pd.to_numeric(df_5v5['highDangerxGoalsFor'], errors='coerce')
                hd_against = pd.to_numeric(df_5v5['highDangerxGoalsAgainst'], errors='coerce')
                hd_total = (hd_for + hd_against).replace(0, np.nan)
                df_5v5['HD_xGF%'] = ((hd_for / hd_total) * 100).round(1)
            else:
                df_5v5['HD_xGF%'] = '-'

            # 2. Shots For & Against Per 60
            if 'shotsOnGoalFor' in df_5v5.columns and 'iceTime' in df_5v5.columns:
                sog_for = pd.to_numeric(df_5v5['shotsOnGoalFor'], errors='coerce')
                sog_against = pd.to_numeric(df_5v5['shotsOnGoalAgainst'], errors='coerce')
                icetime = pd.to_numeric(df_5v5['iceTime'], errors='coerce').replace(0, np.nan)
                
                df_5v5['SF/60'] = ((sog_for / icetime) * 3600).round(1)
                df_5v5['SA/60'] = ((sog_against / icetime) * 3600).round(1)
            else:
                df_5v5['SF/60'] = '-'
                df_5v5['SA/60'] = '-'

            # 3. Calculate PDO Manually
            needed_cols = ['goalsFor', 'shotsOnGoalFor', 'goalsAgainst', 'shotsOnGoalAgainst']
            if all(col in df_5v5.columns for col in needed_cols):
                gf = pd.to_numeric(df_5v5['goalsFor'], errors='coerce')
                sf = pd.to_numeric(df_5v5['shotsOnGoalFor'], errors='coerce').replace(0, np.nan)
                ga = pd.to_numeric(df_5v5['goalsAgainst'], errors='coerce')
                sa = pd.to_numeric(df_5v5['shotsOnGoalAgainst'], errors='coerce').replace(0, np.nan)
                
                sh_pct = gf / sf
                sv_pct = 1 - (ga / sa)
                df_5v5['PDO'] = ((sh_pct + sv_pct) * 100).round(1)
            else:
                df_5v5['PDO'] = '-'

            # 4. Calculate Save % Above Expected Manually
            needed_sv_cols = ['xGoalsAgainst', 'goalsAgainst', 'shotsOnGoalAgainst']
            if all(col in df_5v5.columns for col in needed_sv_cols):
                xga = pd.to_numeric(df_5v5['xGoalsAgainst'], errors='coerce')
                ga = pd.to_numeric(df_5v5['goalsAgainst'], errors='coerce')
                sa = pd.to_numeric(df_5v5['shotsOnGoalAgainst'], errors='coerce').replace(0, np.nan)
                
                df_5v5['Save%_Above_x'] = (((xga - ga) / sa) * 100).round(2)
            else:
                df_5v5['Save%_Above_x'] = '-'
            
            df_5v5 = df_5v5.fillna('-')
            
            return df_5v5.set_index('team').to_dict(orient='index')
        return {}
    except Exception as e:
        print(f"⚠️ MoneyPuck Stats Error: {e}")
        return {}

def build_nhl_matchup_html(away_team, home_team, official_stats, mp_stats):
    """Builds a unified HTML table comparing official API metrics and MoneyPuck models."""
    if not official_stats and not mp_stats:
        return ""
        
    away_clean = away_team.lower().strip()
    home_clean = home_team.lower().strip()
    away_mascot = away_clean.split()[-1]
    home_mascot = home_clean.split()[-1]
    
    # 1. Official NHL API Lookup (matches mascot or full name)
    a_off = next((v for k, v in official_stats.items() if away_mascot in k or k in away_clean), {})
    h_off = next((v for k, v in official_stats.items() if home_mascot in k or k in home_clean), {})

    # 2. MoneyPuck Lookup (using top-level MP_MAP with fuzzy mascot fallback)
    def find_mp_code(team_name, mascot):
        # Direct dictionary match
        if team_name in MP_MAP:
            return MP_MAP[team_name]
        # Match by partial string or mascot
        for full_name, code in MP_MAP.items():
            if mascot in full_name or full_name in team_name:
                return code
        return ""

    a_code = find_mp_code(away_clean, away_mascot)
    h_code = find_mp_code(home_clean, home_mascot)

    a_mp = mp_stats.get(a_code, {})
    h_mp = mp_stats.get(h_code, {})

    html = "<table style='width: 100%; font-size: 11px; text-align: right; border-collapse: collapse; margin-bottom: 12px;'>"
    html += "<tr style='background-color: #1e293b; color: white;'>"
    html += f"<th style='padding: 6px; text-align: left;'>{away_team}</th>"
    html += "<th style='padding: 6px; text-align: center;'>Combined Metrics</th>"
    html += f"<th style='padding: 6px; text-align: right;'>{home_team}</th></tr>"

    def row(cat_name, a_val, h_val, higher_is_better=True, is_pct=False):
        a_color, h_color = "#64748b", "#64748b"
        
        try:
            a_float = float(str(a_val).replace('%', ''))
            h_float = float(str(h_val).replace('%', ''))
            if a_float != h_float:
                if (a_float > h_float and higher_is_better) or (a_float < h_float and not higher_is_better):
                    a_color = "#38a169"
                else:
                    h_color = "#38a169"
        except:
            pass

        disp_a = f"{a_val}%" if is_pct and a_val != '-' else str(a_val)
        disp_h = f"{h_val}%" if is_pct and h_val != '-' else str(h_val)

        return (f"<tr style='border-bottom: 1px solid #e2e8f0; background: #ffffff;'>"
                f"<td style='padding: 5px; text-align: left; color: {a_color}; font-weight: bold;'>{disp_a}</td>"
                f"<td style='padding: 5px; text-align: center; color: #64748b;'>{cat_name}</td>"
                f"<td style='padding: 5px; text-align: right; color: {h_color}; font-weight: bold;'>{disp_h}</td>"
                f"</tr>")

    html += row("Regulation Record (API)", a_off.get('reg_record', '-'), h_off.get('reg_record', '-'), True)
    html += row("Goal Differential (API)", a_off.get('goal_diff', '-'), h_off.get('goal_diff', '-'), True)
    html += row("Power Play (API)", a_off.get('pp_pct', '-'), h_off.get('pp_pct', '-'), True, True)
    html += row("Penalty Kill (API)", a_off.get('pk_pct', '-'), h_off.get('pk_pct', '-'), True, True)
    html += row("PDO (MP)", a_mp.get('PDO', '-'), h_mp.get('PDO', '-'), True)
    html += row("Save % Above Expected (MP)", a_mp.get('Save%_Above_x', '-'), h_mp.get('Save%_Above_x', '-'), True, True)
    html += row("High Danger xGF% (MP)", a_mp.get('HD_xGF%', '-'), h_mp.get('HD_xGF%', '-'), True, True)
    html += row("5v5 Expected Goals (MP)", a_mp.get('xGF%', '-'), h_mp.get('xGF%', '-'), True, True)
    html += row("5v5 Corsi (MP)", a_mp.get('CF%', '-'), h_mp.get('CF%', '-'), True, True)
    html += row("Shots For / 60 (MP)", a_mp.get('SF/60', '-'), h_mp.get('SF/60', '-'), True)
    html += row("Shots Against / 60 (MP)", a_mp.get('SA/60', '-'), h_mp.get('SA/60', '-'), False)

    html += "</table>"
    return html

def fetch_nhl_power_rankings():
    """Scrapes live NHL Power Rankings directly from MoneyPuck's raw HTML rows."""
    import re
    import requests
    print("🏒 Fetching NHL Power Rankings from MoneyPuck...")
    url = "https://moneypuck.com/power.htm"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        
        # Invert MP_MAP to translate abbreviation codes back to full team names
        code_to_name = {v.upper(): k for k, v in MP_MAP.items()}
        # Add 2-letter codes and explicitly handle the 2026 Utah Mammoth rebrand
        code_to_name.update({
            "LA": "los angeles kings", 
            "TB": "tampa bay lightning", 
            "NJ": "new jersey devils",
            "UTA": "utah mammoth" 
        })
        
        # 1. Isolate every table row in the HTML
        rows = re.findall(r'<tr.*?>(.*?)</tr>', res.text, re.IGNORECASE | re.DOTALL)
        
        nhl_ranks = {}
        rank_counter = 1
        
        for row in rows:
            # 2. Look for the first image source inside the row, ignoring the file extension
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', row)
            if img_match:
                # Extract filename without extension (e.g., /logos/nhl/MIN.svg -> MIN)
                code = img_match.group(1).split('/')[-1].split('.')[0].upper()
                
                if code in code_to_name:
                    full_name = code_to_name[code]
                    if full_name not in nhl_ranks:
                        nhl_ranks[full_name] = {"rank": str(rank_counter)}
                        # Store mascot fallback (e.g. "mammoth" or "canadiens")
                        nhl_ranks[full_name.split()[-1]] = {"rank": str(rank_counter)}
                        rank_counter += 1
                        
        return nhl_ranks
    except Exception as e:
        print(f"⚠️ Error fetching NHL Power Rankings: {e}")
        return {}

if __name__ == "__main__":
    import json
    
    print("🏒 Testing Official NHL API Fetcher...")
    nhl_data = fetch_official_nhl_stats()
    print(f"Found official stats for {len(nhl_data)} teams.")
    if nhl_data:
        sample_team = "flyers" if "flyers" in nhl_data else next(iter(nhl_data.keys()))
        print(f"Sample Official ({sample_team}): {json.dumps(nhl_data[sample_team], indent=2)}")

    print("\n📈 Testing MoneyPuck Fetcher...")
    mp_data = fetch_moneypuck_stats()
    print(f"Found MoneyPuck stats for {len(mp_data)} teams.")
    if mp_data:
        sample_mp = "PHI" if "PHI" in mp_data else next(iter(mp_data.keys()))
        print(f"Sample MoneyPuck ({sample_mp}): HD_xGF% {mp_data.get(sample_mp, {}).get('HD_xGF%')} | PDO {mp_data.get(sample_mp, {}).get('PDO')}")

    print("\n🧱 Testing HTML Builder...")
    html_out = build_nhl_matchup_html("Philadelphia Flyers", "New York Rangers", nhl_data, mp_data)
    if html_out:
        print("✅ HTML built successfully!")
        print(html_out[:250] + "...\n[Truncated for readability]")
    else:
        print("❌ HTML build failed or returned empty.")