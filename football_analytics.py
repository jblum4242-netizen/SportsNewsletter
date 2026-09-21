import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def fetch_global_stat_category(sport_path, stat_path):
    """
    Scrapes TeamRankings for a specific stat and returns {mascot: (value, rank)}.
    Used for CFB since DVOA is an NFL metric.
    """
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
                    team_full = cols[1].text.strip().lower()
                    val = cols[2].text.strip()
                    
                    mascot = team_full.split()[-1]
                    data_map[mascot] = {"rank": rank, "value": val}
    except Exception as e:
        print(f"⚠️ Error fetching {stat_path}: {e}")
        
    return data_map

def fetch_nfl_dvoa():
    """
    Scrapes FTN Fantasy for NFL DVOA rankings.
    Returns {mascot: {"total_rank": X, "total_dvoa": Y, "off_dvoa": Z, "def_dvoa": A}}
    """
    url = "https://ftnfantasy.com/stats/nfl/team-total-dvoa"
    dvoa_map = {}
    
    print("📊 Fetching NFL DVOA from FTN Fantasy...")
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            table = soup.find('table')
            if not table: return dvoa_map
            
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 5:
                    # FTN columns typically: Rank, Team, Total DVOA, Off DVOA, Def DVOA, ST DVOA
                    rank = cols[0].text.strip()
                    team_name = cols[1].text.strip().lower()
                    total_dvoa = cols[2].text.strip()
                    off_dvoa = cols[3].text.strip()
                    def_dvoa = cols[4].text.strip()
                    
                    mascot = team_name.split()[-1]
                    dvoa_map[mascot] = {
                        "rank": rank,
                        "total": total_dvoa,
                        "offense": off_dvoa,
                        "defense": def_dvoa
                    }
    except Exception as e:
        print(f"⚠️ Error fetching FTN DVOA: {e}")
        
    return dvoa_map

def fetch_all_league_stats(league):
    """Routes the fetching logic based on the league."""
    if league.lower() == "nfl":
        return fetch_nfl_dvoa()
    else:
        print("📊 Fetching global CFB leaderboards...")
        return {
            "off_ppg": fetch_global_stat_category("ncf", "points-per-game"),
            "def_ppg": fetch_global_stat_category("ncf", "opponent-points-per-game"),
            "off_ypg": fetch_global_stat_category("ncf", "yards-per-game"),
            "def_ypg": fetch_global_stat_category("ncf", "opponent-yards-per-game")
        }

def build_football_stats_html(team_name, league, global_stats):
    """Generates a compact HTML table block for the team's advanced stats."""
    mascot = team_name.lower().split()[-1]
    
    html = f"<div style='margin-top: 15px; margin-bottom: 5px;'>"
    html += f"<strong style='font-size: 12px; color: #2d3748;'>📊 {team_name} Rankings:</strong>"
    html += f"<table style='width: 100%; font-size: 11px; text-align: center; border-collapse: collapse; margin-top: 4px;'>"
    
    html += f"<tr style='background-color: #edf2f7; color: #4a5568;'>"
    html += f"<th style='padding: 3px; text-align: left;'>Category</th>"
    html += f"<th style='padding: 3px;'>Value</th>"
    
    # NFL uses FTN DVOA
    if league.lower() == "nfl":
        team_data = global_stats.get(mascot)
        if not team_data:
            return f"<div style='margin-top: 10px; font-size: 11px; color: #a0aec0;'>No DVOA data available for {team_name}.</div>"
            
        html += f"</tr>"
        
        # DVOA rows
        rows = [
            ("Total DVOA", team_data['total'], f"#{team_data['rank']}"),
            ("Offense DVOA", team_data['offense'], "-"),
            ("Defense DVOA", team_data['defense'], "-")
        ]
        
        for label, val, rank in rows:
            html += f"<tr style='border-bottom: 1px solid #e2e8f0;'>"
            html += f"<td style='padding: 3px; text-align: left; font-weight: bold; color: #4a5568;'>{label}</td>"
            html += f"<td style='padding: 3px;'>{val}</td>"
            if rank != "-":
                html += f"<td style='padding: 3px; font-weight: bold; color: #2b6cb0;'>{rank}</td>"
            html += f"</tr>"

    # CFB uses TeamRankings PPG/YPG
    else:
        team_data = {
            "off_ppg": global_stats["off_ppg"].get(mascot, {"rank": "-", "value": "N/A"}),
            "def_ppg": global_stats["def_ppg"].get(mascot, {"rank": "-", "value": "N/A"}),
            "off_ypg": global_stats["off_ypg"].get(mascot, {"rank": "-", "value": "N/A"}),
            "def_ypg": global_stats["def_ypg"].get(mascot, {"rank": "-", "value": "N/A"})
        }
        
        if team_data["off_ppg"]["value"] == "N/A":
            return f"<div style='margin-top: 10px; font-size: 11px; color: #a0aec0;'>No FBS stat data available for {team_name}.</div>"
            
        html += f"<th style='padding: 3px;'>Rank</th>"
        html += f"</tr>"
        
        def get_rank_color(rank_str):
            if not rank_str.isdigit(): return "#718096"
            rank = int(rank_str)
            if rank <= 12: return "#38a169" 
            if rank >= 25: return "#e53e3e" 
            return "#718096" 

        rows = [
            ("Offense (PPG)", team_data['off_ppg']),
            ("Defense (PPG)", team_data['def_ppg']),
            ("Offense (YPG)", team_data['off_ypg']),
            ("Defense (YPG)", team_data['def_ypg'])
        ]
        
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
        ("Delaware Blue Hens", "NCAAF", cfb_global_stats) 
    ]
    
    for team, league, global_dict in test_teams:
        html_block = build_football_stats_html(team, league, global_dict)
        print(f"\n--- {team} HTML ---")
        print(html_block)
        
    print("\n✅ Module execution complete.")