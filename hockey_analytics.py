import pandas as pd
import requests
import io

def fetch_official_nhl_stats():
    """Fetches official team stats directly from the NHL web API."""
    stats_dict = {}
    # Bypassing the wrapper to hit the official NHL endpoint directly
    url = "https://api-web.nhle.com/v1/standings/now"
    
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            standings = res.json().get('standings', [])
            for team in standings:
                # The NHL API provides team names like "Flyers" in teamName.default
                team_name = team.get('teamName', {}).get('default', '').lower()
                if not team_name:
                    continue
                    
                # Build the Regulation Record string
                reg_wins = team.get('regulationWins', 0)
                losses = team.get('losses', 0)
                ot_losses = team.get('otLosses', 0)
                    
                stats_dict[team_name] = {
                    'goal_diff': team.get('goalDifferential', 0),
                    'pp_pct': team.get('powerPlayPctg', 0.0),
                    'pk_pct': team.get('penaltyKillPctg', 0.0),
                    'reg_record': f"{reg_wins}-{losses}-{ot_losses}"
                }
        return stats_dict
    except Exception as e:
        print(f"⚠️ NHL API Error: {e}")
        return {}

def fetch_moneypuck_stats():
    """Fetches live 5v5 advanced stats from MoneyPuck using a masked User-Agent."""
    url = "https://moneypuck.com/moneypuck/playerData/seasonSummary/2026/regular/teams.csv"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/115.0.0.0 Safari/537.36"}
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            df = pd.read_csv(io.StringIO(res.text))
            df_5v5 = df[df['situation'] == '5on5'].copy()
            
            df_5v5['team'] = df_5v5['team'].str.upper()
            
            # Grab the pre-calculated percentages and format them for display
            df_5v5['CF%'] = (df_5v5['corsiPercentage'] * 100).round(1)
            df_5v5['xGF%'] = (df_5v5['xGoalsPercentage'] * 100).round(1)
            
            # Add the new Advanced Metrics
            df_5v5['PDO'] = (df_5v5['pdo'] * 100).round(1)
            df_5v5['Save%_Above_x'] = (df_5v5['savePctAboveExpected'] * 100).round(2)
            df_5v5['HD_xGF%'] = (df_5v5['highDangerxGoalsPercentage'] * 100).round(1)
            df_5v5['SF/60'] = ((df_5v5['shotsOnGoalFor'] / df_5v5['icetime']) * 60).round(1)
            df_5v5['SA/60'] = ((df_5v5['shotsOnGoalAgainst'] / df_5v5['icetime']) * 60).round(1)
            
            return df_5v5.set_index('team').to_dict(orient='index')
        return {}
    except Exception as e:
        print(f"⚠️ MoneyPuck Stats Error: {e}")
        return {}

def build_nhl_matchup_html(away_team, home_team, official_stats, mp_stats):
    """Builds a unified HTML table comparing official API metrics and MoneyPuck models."""
    if not official_stats:
        return ""
        
    # 1. Match Official Stats (using mascot)
    away_mascot = away_team.lower().split()[-1]
    home_mascot = home_team.lower().split()[-1]
    
    a_off = next((v for k, v in official_stats.items() if away_mascot in k), {})
    h_off = next((v for k, v in official_stats.items() if home_mascot in k), {})

    # 2. Match MoneyPuck Stats (Requires 3-letter abbreviations)
    mp_map = {
        "anaheim ducks": "ANA", "boston bruins": "BOS", "buffalo sabres": "BUF", "calgary flames": "CGY",
        "carolina hurricanes": "CAR", "chicago blackhawks": "CHI", "colorado avalanche": "COL", 
        "columbus blue jackets": "CBJ", "dallas stars": "DAL", "detroit red wings": "DET", "edmonton oilers": "EDM",
        "florida panthers": "FLA", "los angeles kings": "LAK", "minnesota wild": "MIN", "montreal canadiens": "MTL",
        "nashville predators": "NSH", "new jersey devils": "NJD", "new york islanders": "NYI", "new york rangers": "NYR",
        "ottawa senators": "OTT", "philadelphia flyers": "PHI", "pittsburgh penguins": "PIT", "san jose sharks": "SJS",
        "seattle kraken": "SEA", "st. louis blues": "STL", "tampa bay lightning": "TBL", "toronto maple leafs": "TOR",
        "utah hockey club": "UTA", "vancouver canucks": "VAN", "vegas golden knights": "VGK", "washington capitals": "WSH",
        "winnipeg jets": "WPG"
    }
    
    a_mp = mp_stats.get(mp_map.get(away_team.lower(), ""), {})
    h_mp = mp_stats.get(mp_map.get(home_team.lower(), ""), {})

    # 3. Build the HTML Table
    html = f"<table style='width: 100%; font-size: 11px; text-align: right; border-collapse: collapse; margin-bottom: 12px;'>"
    html += f"<tr style='background-color: #1e293b; color: white;'>"
    html += f"<th style='padding: 6px; text-align: left;'>{away_team}</th>"
    html += f"<th style='padding: 6px; text-align: center;'>Combined Metrics</th>"
    html += f"<th style='padding: 6px; text-align: right;'>{home_team}</th></tr>"

    def row(cat_name, a_val, h_val, higher_is_better=True, is_pct=False):
        a_color, h_color = "#64748b", "#64748b"
        
        try:
            a_float = float(str(a_val).replace('%', ''))
            h_float = float(str(h_val).replace('%', ''))
            if a_float != h_float:
                if (a_float > h_float and higher_is_better) or (a_float < h_float and not higher_is_better):
                    a_color = "#38a169" # Green
                else:
                    h_color = "#38a169" # Green
        except: pass

        disp_a = f"{a_val}%" if is_pct and a_val != '-' else str(a_val)
        disp_h = f"{h_val}%" if is_pct and h_val != '-' else str(h_val)

        return (f"<tr style='border-bottom: 1px solid #e2e8f0; background: #ffffff;'>"
                f"<td style='padding: 5px; text-align: left; color: {a_color}; font-weight: bold;'>{disp_a}</td>"
                f"<td style='padding: 5px; text-align: center; color: #64748b;'>{cat_name}</td>"
                f"<td style='padding: 5px; text-align: right; color: {h_color}; font-weight: bold;'>{disp_h}</td>"
                f"</tr>")

    # Inject Data Rows
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

if __name__ == "__main__":
    import json
    
    print("🏒 Testing Official NHL API Fetcher...")
    nhl_data = fetch_official_nhl_stats()
    print(f"Found official stats for {len(nhl_data)} teams.")
    if nhl_data:
        # Grab a sample team (e.g., flyers) if it exists, otherwise grab the first one
        sample_team = "flyers" if "flyers" in nhl_data else next(iter(nhl_data.keys()))
        print(f"Sample Official ({sample_team}): {json.dumps(nhl_data[sample_team], indent=2)}")

    print("\n📈 Testing MoneyPuck Fetcher...")
    mp_data = fetch_moneypuck_stats()
    print(f"Found MoneyPuck stats for {len(mp_data)} teams.")
    if mp_data:
        sample_mp = "PHI" if "PHI" in mp_data else next(iter(mp_data.keys()))
        print(f"Sample MoneyPuck ({sample_mp}): HD_xGF% {mp_data[sample_mp].get('HD_xGF%')} | PDO {mp_data[sample_mp].get('PDO')}")

    print("\n🧱 Testing HTML Builder...")
    html_out = build_nhl_matchup_html("Philadelphia Flyers", "New York Rangers", nhl_data, mp_data)
    if html_out:
        print("✅ HTML built successfully!")
        print(html_out[:250] + "...\n[Truncated for readability]")
    else:
        print("❌ HTML build failed or returned empty.")