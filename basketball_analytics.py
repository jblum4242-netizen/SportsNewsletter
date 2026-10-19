import datetime
import io
import json
import os
import re
import sys
from zoneinfo import ZoneInfo
import pandas as pd
import requests

# ==========================================
# CONFIGURATION & TEAM CROSSWALKS
# ==========================================
NBA_MASCOT_MAP = {
    "hawks": "atlanta hawks", "celtics": "boston celtics", "nets": "brooklyn nets",
    "hornets": "charlotte hornets", "bulls": "chicago bulls", "cavaliers": "cleveland cavaliers",
    "mavericks": "dallas mavericks", "nuggets": "denver nuggets", "pistons": "detroit pistons",
    "warriors": "golden state warriors", "rockets": "houston rockets", "pacers": "indiana pacers",
    "clippers": "los angeles clippers", "lakers": "los angeles lakers", "grizzlies": "memphis grizzlies",
    "heat": "miami heat", "bucks": "milwaukee bucks", "timberwolves": "minnesota timberwolves",
    "pelicans": "new orleans pelicans", "knicks": "new york knicks", "thunder": "oklahoma city thunder",
    "magic": "orlando magic", "76ers": "philadelphia 76ers", "suns": "phoenix suns",
    "blazers": "portland trail blazers", "kings": "sacramento kings", "spurs": "san antonio spurs",
    "raptors": "toronto raptors", "jazz": "utah jazz", "wizards": "washington wizards"
}

# Maps Odds API full names ("UCLA Bruins") to BartTorvik/KenPom school names ("ucla")
NCAAB_ALIASES = {
    "uconn": "connecticut", "connecticut": "connecticut",
    "ole miss": "mississippi", "nc state": "north carolina st.",
    "pittsburgh": "pitt", "smu": "southern methodist",
    "tcu": "texas christian", "ucf": "central florida",
    "byu": "brigham young", "lsu": "louisiana st.",
    "st. john's": "st. john's", "miami": "miami fl",
    "usc": "USC", "ucla": "ucla", "penn state": "penn st.",
    "ohio state": "ohio st.", "michigan state": "michigan st.",
    "iowa state": "iowa st.", "kansas state": "kansas st.",
    "oklahoma state": "oklahoma st.", "mississippi state": "mississippi st.",
    "florida state": "florida st.", "arizona state": "arizona st."
}


def _clean_team_key(name):
    s = str(name).replace("*", "").lower().strip()
    return re.sub(r"\s+", " ", s)


# ==========================================
# 1. NBA ADVANCED METRICS (Basketball-Reference)
# ==========================================
def fetch_nba_stats():
    """Fetches NBA Efficiency, Pace, Four Factors, Shooting & Style splits from Basketball-Reference."""
    now = datetime.datetime.now()
    target_season = now.year + 1 if now.month >= 10 else now.year
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}

    for season in [target_season, target_season - 1]:
        url = f"https://www.basketball-reference.com/leagues/NBA_{season}.html"
        print(f"🏀 [NBA] Fetching Advanced & Four Factors data for {season-1}-{str(season)[-2:]} season...")
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code != 200:
                continue

            # Uncomment hidden B-Ref tables if needed
            clean_html = res.text.replace("<!--", "").replace("-->", "")
            soup_tables = pd.read_html(io.StringIO(clean_html))

            adv_df = None
            team_pg_df = None
            opp_pg_df = None

            for df in soup_tables:
                cols_str = " ".join([str(c) for c in df.columns])
                if "ORtg" in cols_str and "DRtg" in cols_str and "Pace" in cols_str:
                    adv_df = df.copy()
                elif "3P%" in cols_str and "2P%" in cols_str and "AST" in cols_str and "FG" in cols_str:
                    # First table with 3P%/2P% is Team Per Game, second is Opponent Per Game
                    if team_pg_df is None:
                        team_pg_df = df.copy()
                    elif opp_pg_df is None:
                        opp_pg_df = df.copy()

            if adv_df is None:
                continue

            # Flatten MultiIndex on Advanced Table
            if isinstance(adv_df.columns, pd.MultiIndex):
                flat_cols = []
                for col in adv_df.columns.values:
                    top, bot = str(col[0]), str(col[1])
                    if "Offense" in top:
                        flat_cols.append(f"Off_{bot}")
                    elif "Defense" in top:
                        flat_cols.append(f"Def_{bot}")
                    else:
                        flat_cols.append(bot)
                adv_df.columns = flat_cols

            adv_df = adv_df[adv_df["Team"].notna()].copy()
            adv_df = adv_df[~adv_df["Team"].astype(str).str.contains("Average|Team|Division", case=False)].copy()
            adv_df["W"] = pd.to_numeric(adv_df.get("W", 0), errors="coerce").fillna(0)
            adv_df["L"] = pd.to_numeric(adv_df.get("L", 0), errors="coerce").fillna(0)

            # If current season hasn't tipped off yet (0 games played), fall back to prior season
            if (adv_df["W"].sum() + adv_df["L"].sum()) == 0 and season == target_season:
                print(f"ℹ️ [NBA] {season} has 0 games played yet. Loading {season-1} baseline stats...")
                continue

            adv_df["clean_team"] = adv_df["Team"].apply(_clean_team_key)

            # Map optional shooting & style splits from Per-Game tables
            if team_pg_df is not None and opp_pg_df is not None:
                team_pg_df = team_pg_df[team_pg_df["Team"].notna()].copy()
                opp_pg_df = opp_pg_df[opp_pg_df["Team"].notna()].copy()
                team_pg_df["clean_team"] = team_pg_df["Team"].apply(_clean_team_key)
                opp_pg_df["clean_team"] = opp_pg_df["Team"].apply(_clean_team_key)

                for c in ["FG", "FGA", "3PA", "3P%", "2P%", "FT%", "AST"]:
                    if c in team_pg_df.columns:
                        team_pg_df[c] = pd.to_numeric(team_pg_df[c], errors="coerce")
                    if c in opp_pg_df.columns:
                        opp_pg_df[c] = pd.to_numeric(opp_pg_df[c], errors="coerce")

                team_pg_df["Off_3P%"] = team_pg_df["3P%"] * 100.0
                team_pg_df["Off_2P%"] = team_pg_df["2P%"] * 100.0
                team_pg_df["Off_FT%"] = team_pg_df["FT%"] * 100.0
                team_pg_df["Off_AFGM"] = (team_pg_df["AST"] / team_pg_df["FG"]) * 100.0
                team_pg_df["Off_3PAr"] = (team_pg_df["3PA"] / team_pg_df["FGA"]) * 100.0

                opp_pg_df["Def_3P%"] = opp_pg_df["3P%"] * 100.0
                opp_pg_df["Def_2P%"] = opp_pg_df["2P%"] * 100.0
                opp_pg_df["Def_FT%"] = opp_pg_df["FT%"] * 100.0
                opp_pg_df["Def_AFGM"] = (opp_pg_df["AST"] / opp_pg_df["FG"]) * 100.0
                opp_pg_df["Def_3PAr"] = (opp_pg_df["3PA"] / opp_pg_df["FGA"]) * 100.0

                adv_df = adv_df.merge(
                    team_pg_df[["clean_team", "Off_3P%", "Off_2P%", "Off_FT%", "Off_AFGM", "Off_3PAr"]],
                    on="clean_team", how="left"
                ).merge(
                    opp_pg_df[["clean_team", "Def_3P%", "Def_2P%", "Def_FT%", "Def_AFGM", "Def_3PAr"]],
                    on="clean_team", how="left"
                )

            # Standardize numeric columns
            e_fg_off = next((c for c in adv_df.columns if "Off" in c and "eFG" in c), "eFG%")
            tov_off = next((c for c in adv_df.columns if "Off" in c and "TOV" in c), "TOV%")
            orb_off = next((c for c in adv_df.columns if "Off" in c and "ORB" in c), "ORB%")
            ftr_off = next((c for c in adv_df.columns if "Off" in c and "FT/FGA" in c), "FTr")

            e_fg_def = next((c for c in adv_df.columns if "Def" in c and "eFG" in c), e_fg_off)
            tov_def = next((c for c in adv_df.columns if "Def" in c and "TOV" in c), tov_off)
            drb_def = next((c for c in adv_df.columns if "Def" in c and "DRB" in c), "DRB%")
            ftr_def = next((c for c in adv_df.columns if "Def" in c and "FT/FGA" in c), ftr_off)

            for col in ["ORtg", "DRtg", "NRtg", "Pace", "SOS", e_fg_off, tov_off, orb_off, ftr_off, e_fg_def, tov_def, drb_def, ftr_def]:
                if col in adv_df.columns:
                    adv_df[col] = pd.to_numeric(adv_df[col], errors="coerce")

            # Convert decimal percentages (0.542 -> 54.2) and DRB% -> Opp ORB% Allowed
            adv_df["off_efg_val"] = adv_df[e_fg_off] * 100.0
            adv_df["def_efg_val"] = adv_df[e_fg_def] * 100.0
            adv_df["off_ftr_val"] = adv_df[ftr_off] * 100.0
            adv_df["def_ftr_val"] = adv_df[ftr_def] * 100.0
            adv_df["off_orb_val"] = adv_df[orb_off]
            adv_df["def_orb_val"] = 100.0 - adv_df[drb_def]  # Opponent ORB% allowed (KenPom convention)

            # Calculate Ranks (1-30)
            adv_df["rank"] = adv_df["NRtg"].rank(ascending=False, method="min")
            adv_df["adj_oe_rk"] = adv_df["ORtg"].rank(ascending=False, method="min")
            adv_df["adj_de_rk"] = adv_df["DRtg"].rank(ascending=True, method="min")
            adv_df["tempo_rk"] = adv_df["Pace"].rank(ascending=False, method="min")
            adv_df["sos_rk"] = adv_df["SOS"].rank(ascending=False, method="min")

            adv_df["off_efg_rk"] = adv_df["off_efg_val"].rank(ascending=False, method="min")
            adv_df["def_efg_rk"] = adv_df["def_efg_val"].rank(ascending=True, method="min")
            adv_df["off_tov_rk"] = adv_df[tov_off].rank(ascending=True, method="min")   # Lower Off TOV% is better
            adv_df["def_tov_rk"] = adv_df[tov_def].rank(ascending=False, method="min")  # Higher Forced TOV% is better
            adv_df["off_orb_rk"] = adv_df["off_orb_val"].rank(ascending=False, method="min")
            adv_df["def_orb_rk"] = adv_df["def_orb_val"].rank(ascending=True, method="min")
            adv_df["off_ftr_rk"] = adv_df["off_ftr_val"].rank(ascending=False, method="min")
            adv_df["def_ftr_rk"] = adv_df["def_ftr_val"].rank(ascending=True, method="min")

            for split_col, asc in [
                ("Off_3P%", False), ("Def_3P%", True),
                ("Off_2P%", False), ("Def_2P%", True),
                ("Off_FT%", False), ("Def_FT%", True),
                ("Off_3PAr", False), ("Def_3PAr", True),
                ("Off_AFGM", False), ("Def_AFGM", True),
            ]:
                if split_col in adv_df.columns:
                    adv_df[f"{split_col}_rk"] = adv_df[split_col].rank(ascending=asc, method="min")

            stats_map = {}
            for _, row in adv_df.iterrows():
                t_key = row["clean_team"]
                mascot = t_key.split()[-1]
                entry = {
                    "rank": f"{int(row['rank'])}",
                    "net_rtg": f"{row['NRtg']:+.1f}",
                    "adj_oe": f"{row['ORtg']:.1f}", "adj_oe_rk": f"{int(row['adj_oe_rk'])}",
                    "adj_de": f"{row['DRtg']:.1f}", "adj_de_rk": f"{int(row['adj_de_rk'])}",
                    "tempo": f"{row['Pace']:.1f}", "tempo_rk": f"{int(row['tempo_rk'])}",
                    "sos": f"{row['SOS']:+.2f}", "sos_rk": f"{int(row['sos_rk'])}",
                    "off_efg": f"{row['off_efg_val']:.1f}", "off_efg_rk": f"{int(row['off_efg_rk'])}",
                    "def_efg": f"{row['def_efg_val']:.1f}", "def_efg_rk": f"{int(row['def_efg_rk'])}",
                    "off_tov": f"{row[tov_off]:.1f}", "off_tov_rk": f"{int(row['off_tov_rk'])}",
                    "def_tov": f"{row[tov_def]:.1f}", "def_tov_rk": f"{int(row['def_tov_rk'])}",
                    "off_orb": f"{row['off_orb_val']:.1f}", "off_orb_rk": f"{int(row['off_orb_rk'])}",
                    "def_orb": f"{row['def_orb_val']:.1f}", "def_orb_rk": f"{int(row['def_orb_rk'])}",
                    "off_ftr": f"{row['off_ftr_val']:.1f}", "off_ftr_rk": f"{int(row['off_ftr_rk'])}",
                    "def_ftr": f"{row['def_ftr_val']:.1f}", "def_ftr_rk": f"{int(row['def_ftr_rk'])}",
                    "off_3p": f"{row.get('Off_3P%', 0):.1f}" if pd.notna(row.get("Off_3P%")) else "-",
                    "off_3p_rk": f"{int(row['Off_3P%_rk'])}" if pd.notna(row.get("Off_3P%_rk")) else "-",
                    "def_3p": f"{row.get('Def_3P%', 0):.1f}" if pd.notna(row.get("Def_3P%")) else "-",
                    "def_3p_rk": f"{int(row['Def_3P%_rk'])}" if pd.notna(row.get("Def_3P%_rk")) else "-",
                    "off_2p": f"{row.get('Off_2P%', 0):.1f}" if pd.notna(row.get("Off_2P%")) else "-",
                    "off_2p_rk": f"{int(row['Off_2P%_rk'])}" if pd.notna(row.get("Off_2P%_rk")) else "-",
                    "def_2p": f"{row.get('Def_2P%', 0):.1f}" if pd.notna(row.get("Def_2P%")) else "-",
                    "def_2p_rk": f"{int(row['Def_2P%_rk'])}" if pd.notna(row.get("Def_2P%_rk")) else "-",
                    "off_ft": f"{row.get('Off_FT%', 0):.1f}" if pd.notna(row.get("Off_FT%")) else "-",
                    "off_ft_rk": f"{int(row['Off_FT%_rk'])}" if pd.notna(row.get("Off_FT%_rk")) else "-",
                    "def_ft": f"{row.get('Def_FT%', 0):.1f}" if pd.notna(row.get("Def_FT%")) else "-",
                    "def_ft_rk": f"{int(row['Def_FT%_rk'])}" if pd.notna(row.get("Def_FT%_rk")) else "-",
                    "off_3par": f"{row.get('Off_3PAr', 0):.1f}" if pd.notna(row.get("Off_3PAr")) else "-",
                    "off_3par_rk": f"{int(row['Off_3PAr_rk'])}" if pd.notna(row.get("Off_3PAr_rk")) else "-",
                    "def_3par": f"{row.get('Def_3PAr', 0):.1f}" if pd.notna(row.get("Def_3PAr")) else "-",
                    "def_3par_rk": f"{int(row['Def_3PAr_rk'])}" if pd.notna(row.get("Def_3PAr_rk")) else "-",
                    "off_afgm": f"{row.get('Off_AFGM', 0):.1f}" if pd.notna(row.get("Off_AFGM")) else "-",
                    "off_afgm_rk": f"{int(row['Off_AFGM_rk'])}" if pd.notna(row.get("Off_AFGM_rk")) else "-",
                    "def_afgm": f"{row.get('Def_AFGM', 0):.1f}" if pd.notna(row.get("Def_AFGM")) else "-",
                    "def_afgm_rk": f"{int(row['Def_AFGM_rk'])}" if pd.notna(row.get("Def_AFGM_rk")) else "-",
                }
                stats_map[t_key] = entry
                stats_map[mascot] = entry

            print(f"✅ [NBA] Successfully parsed {len(adv_df)} NBA teams (Season {season}).")
            return stats_map

        except Exception as e:
            print(f"⚠️ [NBA] Error fetching season {season}: {e}")

    return {}


# ==========================================
# 2. NCAAB KENPOM-STYLE METRICS (BartTorvik CSVs)
# ==========================================
def fetch_ncaab_stats():
    """Fetches D-I Adjusted Efficiency, Tempo, Four Factors, and Style Splits from BartTorvik CSVs."""
    now = datetime.datetime.now()
    target_season = now.year + 1 if now.month >= 10 else now.year
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}

    for season in [target_season, target_season - 1]:
        trank_url = f"https://barttorvik.com/{season}_team_results.csv"
        ff_url = f"https://barttorvik.com/{season}_fffinal.csv"
        print(f"🏀 [NCAAB] Fetching T-Rank & Four Factors CSVs for {season}...")

        try:
            res_trank = requests.get(trank_url, headers=headers, timeout=15)
            res_ff = requests.get(ff_url, headers=headers, timeout=15)

            if res_trank.status_code != 200 or len(res_trank.text) < 500:
                continue

            trank_df = pd.read_csv(io.StringIO(res_trank.text))
            if len(trank_df) < 100:
                continue

            # Identify core T-Rank columns dynamically
            cols_lower = {c.lower().strip(): c for c in trank_df.columns}
            team_col = cols_lower.get("team", trank_df.columns[1])
            rk_col = cols_lower.get("rank", trank_df.columns[0])
            oe_col = cols_lower.get("adjoe", trank_df.columns[4])
            oe_rk_col = cols_lower.get("oe rank", trank_df.columns[5])
            de_col = cols_lower.get("adjde", trank_df.columns[6])
            de_rk_col = cols_lower.get("de rank", trank_df.columns[7])
            tempo_col = next((c for k, c in cols_lower.items() if "adjt" in k or "tempo" in k), trank_df.columns[-1])
            sos_col = next((c for k, c in cols_lower.items() if k in ["sos", "ov_cur_sos", "barthag"]), trank_df.columns[8])

            for c in [rk_col, oe_col, oe_rk_col, de_col, de_rk_col, tempo_col, sos_col]:
                trank_df[c] = pd.to_numeric(trank_df[c], errors="coerce")

            trank_df["tempo_rk"] = trank_df[tempo_col].rank(ascending=False, method="min")
            trank_df["sos_rk"] = trank_df[sos_col].rank(ascending=False, method="min")

            stats_map = {}
            for _, row in trank_df.iterrows():
                t_name = _clean_team_key(row[team_col])
                if not t_name or pd.isna(row[oe_col]):
                    continue
                net_eff = float(row[oe_col]) - float(row[de_col])
                stats_map[t_name] = {
                    "rank": f"{int(row[rk_col])}" if pd.notna(row[rk_col]) else "999",
                    "net_rtg": f"{net_eff:+.1f}",
                    "adj_oe": f"{float(row[oe_col]):.1f}", "adj_oe_rk": f"{int(row[oe_rk_col])}" if pd.notna(row[oe_rk_col]) else "-",
                    "adj_de": f"{float(row[de_col]):.1f}", "adj_de_rk": f"{int(row[de_rk_col])}" if pd.notna(row[de_rk_col]) else "-",
                    "tempo": f"{float(row[tempo_col]):.1f}" if pd.notna(row[tempo_col]) else "-",
                    "tempo_rk": f"{int(row['tempo_rk'])}" if pd.notna(row["tempo_rk"]) else "-",
                    "sos": f"{float(row[sos_col]):.2f}" if pd.notna(row[sos_col]) else "-",
                    "sos_rk": f"{int(row['sos_rk'])}" if pd.notna(row["sos_rk"]) else "-",
                    # Default placeholders before merging fffinal.csv
                    "off_efg": "-", "off_efg_rk": "-", "def_efg": "-", "def_efg_rk": "-",
                    "off_tov": "-", "off_tov_rk": "-", "def_tov": "-", "def_tov_rk": "-",
                    "off_orb": "-", "off_orb_rk": "-", "def_orb": "-", "def_orb_rk": "-",
                    "off_ftr": "-", "off_ftr_rk": "-", "def_ftr": "-", "def_ftr_rk": "-",
                    "off_3p": "-", "off_3p_rk": "-", "def_3p": "-", "def_3p_rk": "-",
                    "off_2p": "-", "off_2p_rk": "-", "def_2p": "-", "def_2p_rk": "-",
                    "off_ft": "-", "off_ft_rk": "-", "def_ft": "-", "def_ft_rk": "-",
                    "off_3par": "-", "off_3par_rk": "-", "def_3par": "-", "def_3par_rk": "-",
                    "off_afgm": "-", "off_afgm_rk": "-", "def_afgm": "-", "def_afgm_rk": "-",
                }

            # Merge Four Factors & Shooting Splits from {year}_fffinal.csv
            if res_ff.status_code == 200 and len(res_ff.text) > 500:
                ff_df = pd.read_csv(io.StringIO(res_ff.text))
                # fffinal.csv pairs each stat column with its national rank column immediately after it:
                # 0:TeamName, 1:eFG%, 2:rk, 3:eFG% Def, 4:rk, 5:FTR, 6:rk, 7:FTR Def, 8:rk,
                # 9:OR%, 10:rk, 11:DR%, 12:rk, 13:TO%, 14:rk, 15:TO% Def, 16:rk,
                # 17:3P%, 18:rk, 19:3pD%, 20:rk, 21:2p%, 22:rk, 23:2pD%, 24:rk,
                # 25:FT%, 26:rk, 27:FT% Def, 28:rk, 29:3P rate, 30:rk, 31:3P rate D, 32:rk,
                # 33:arate, 34:rk, 35:arate D, 36:rk
                if ff_df.shape[1] >= 35:
                    for _, frow in ff_df.iterrows():
                        ft_name = _clean_team_key(frow.iloc[0])
                        if ft_name in stats_map:
                            def _v(idx):
                                val = pd.to_numeric(frow.iloc[idx], errors="coerce")
                                return f"{val:.1f}" if pd.notna(val) else "-"
                            def _r(idx):
                                rk = pd.to_numeric(frow.iloc[idx], errors="coerce")
                                return f"{int(rk)}" if pd.notna(rk) else "-"

                            # Convert Defensive Rebound % (col 11) to Opp ORB% Allowed (100 - DR%) for KenPom parity
                            drb_val = pd.to_numeric(frow.iloc[11], errors="coerce")
                            opp_orb_str = f"{(100.0 - drb_val):.1f}" if pd.notna(drb_val) else "-"

                            stats_map[ft_name].update({
                                "off_efg": _v(1), "off_efg_rk": _r(2),
                                "def_efg": _v(3), "def_efg_rk": _r(4),
                                "off_ftr": _v(5), "off_ftr_rk": _r(6),
                                "def_ftr": _v(7), "def_ftr_rk": _r(8),
                                "off_orb": _v(9), "off_orb_rk": _r(10),
                                "def_orb": opp_orb_str, "def_orb_rk": _r(12),
                                "off_tov": _v(13), "off_tov_rk": _r(14),
                                "def_tov": _v(15), "def_tov_rk": _r(16),
                                "off_3p": _v(17), "off_3p_rk": _r(18),
                                "def_3p": _v(19), "def_3p_rk": _r(20),
                                "off_2p": _v(21), "off_2p_rk": _r(22),
                                "def_2p": _v(23), "def_2p_rk": _r(24),
                                "off_ft": _v(25), "off_ft_rk": _r(26),
                                "def_ft": _v(27), "def_ft_rk": _r(28),
                                "off_3par": _v(29), "off_3par_rk": _r(30),
                                "def_3par": _v(31), "def_3par_rk": _r(32),
                                "off_afgm": _v(33), "off_afgm_rk": _r(34),
                                "def_afgm": _v(35), "def_afgm_rk": _r(36),
                            })

            print(f"✅ [NCAAB] Successfully parsed {len(stats_map)} D-I teams (Season {season}).")
            return stats_map

        except Exception as e:
            print(f"⚠️ [NCAAB] Error fetching BartTorvik CSVs for {season}: {e}")

    return {}


# ==========================================
# 3. DAILY CACHE ROUTER
# ==========================================
def fetch_all_basketball_stats(league):
    """Router for NBA and NCAAB metrics with daily JSON caching."""
    league_key = league.upper()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cache_file = os.path.join(base_dir, "basketball_stats_cache.json")
    today_str = datetime.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    force_refresh = "--refresh" in sys.argv

    cache_data = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
        except Exception as e:
            print(f"⚠️ Basketball stats cache read error: {e}")

    if not force_refresh and cache_data.get("date") == today_str and cache_data.get(league_key):
        print(f"📦 [BASKETBALL CACHE] Loaded today's {league_key} metrics from cache.")
        return cache_data[league_key]

    fresh_stats = fetch_nba_stats() if league_key == "NBA" else fetch_ncaab_stats()

    if fresh_stats:
        if cache_data.get("date") != today_str:
            cache_data = {"date": today_str}
        cache_data[league_key] = fresh_stats
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f)
            print(f"💾 [BASKETBALL CACHE] Saved fresh {league_key} metrics for {today_str}.")
        except Exception as e:
            print(f"⚠️ Basketball stats cache write error: {e}")
        return fresh_stats
    elif cache_data.get(league_key):
        print(f"⚠️ Live {league_key} fetch failed; falling back to cached stats.")
        return cache_data[league_key]

    return {}


# ==========================================
# 4. KENPOM SCOUTING REPORT HTML BUILDER
# ==========================================
def _lookup_team_stats(team_name, league, global_stats):
    t_clean = _clean_team_key(re.sub(r"^\(\d+\)\s*", "", team_name))
    if not global_stats:
        return {}

    if league.upper() == "NBA":
        mascot = t_clean.split()[-1]
        return global_stats.get(t_clean) or global_stats.get(mascot) or {}

    # NCAAB Matching (Strip mascot from Odds API name, e.g. "UCLA Bruins" -> "ucla")
    for alias_k, torvik_v in NCAAB_ALIASES.items():
        if t_clean.startswith(alias_k):
            hit = global_stats.get(torvik_v.lower())
            if hit:
                return hit

    # Try exact match, then prefix words without mascot
    if t_clean in global_stats:
        return global_stats[t_clean]

    words = t_clean.split()
    for i in range(len(words) - 1, 0, -1):
        candidate = " ".join(words[:i])
        candidate_st = candidate.replace("state", "st.")
        if candidate in global_stats:
            return global_stats[candidate]
        if candidate_st in global_stats:
            return global_stats[candidate_st]

    return {}


def build_basketball_matchup_html(away_team, home_team, league, global_stats):
    """Renders a KenPom-style Scouting Report table with Offense/Defense splits and percentile color cells."""
    away_data = _lookup_team_stats(away_team, league, global_stats)
    home_data = _lookup_team_stats(home_team, league, global_stats)

    if not away_data and not home_data:
        return ""

    max_teams = 30 if league.upper() == "NBA" else 364

    def kp_cell(val, rk_str, neutral=False):
        """Builds a KenPom-styled heatmap cell: blue bold value + subscript rank."""
        if not val or val == "-" or not str(rk_str).isdigit():
            return f"<td style='padding: 4px 6px; color: #94a3b8;'>-</td>"

        rk = int(rk_str)
        pct = rk / max_teams

        if neutral:
            # Tempo / 3PA style cells use soft blue shading like KenPom
            bg = "#dbeafe" if pct <= 0.25 else "#e0e7ff" if pct >= 0.75 else "#f8fafc"
        else:
            # Green-to-Red 5-tier heatmap based on national percentile
            if pct <= 0.15:
                bg = "#bbf7d0"      # Deep KenPom Green (Top 15%)
            elif pct <= 0.35:
                bg = "#dcfce7"      # Soft Green (Top 35%)
            elif pct <= 0.65:
                bg = "#f8fafc"      # Neutral Middle
            elif pct <= 0.85:
                bg = "#fee2e2"      # Soft Red (Bottom 35%)
            else:
                bg = "#fecaca"      # Deep KenPom Red (Bottom 15%)

        return (
            f"<td style='background-color: {bg}; padding: 4px 6px; border: 1px solid #ffffff; border-radius: 3px;'>"
            f"<span style='color: #1d4ed8; font-weight: 700; font-size: 11px;'>{val}</span> "
            f"<span style='color: #334155; font-size: 9px; font-weight: 600;'>{rk}</span>"
            f"</td>"
        )

    def section_banner(title):
        return (
            f"<tr style='background-color: #e2e8f0; border-top: 1px solid #94a3b8; border-bottom: 1px solid #94a3b8;'>"
            f"<td colspan='5' style='padding: 3px 6px; font-weight: 700; font-size: 10px; color: #0f172a; text-align: center; letter-spacing: 0.4px;'>{title}</td>"
            f"</tr>"
        )

    def dual_row(label, key_prefix, neutral=False):
        a_off = kp_cell(away_data.get(f"off_{key_prefix}", "-"), away_data.get(f"off_{key_prefix}_rk", "-"), neutral)
        a_def = kp_cell(away_data.get(f"def_{key_prefix}", "-"), away_data.get(f"def_{key_prefix}_rk", "-"), neutral)
        h_off = kp_cell(home_data.get(f"off_{key_prefix}", "-"), home_data.get(f"off_{key_prefix}_rk", "-"), neutral)
        h_def = kp_cell(home_data.get(f"def_{key_prefix}", "-"), home_data.get(f"def_{key_prefix}_rk", "-"), neutral)
        return (
            f"<tr style='border-bottom: 1px solid #f1f5f9;'>"
            f"{a_off}{a_def}"
            f"<td style='padding: 4px 6px; font-weight: 600; color: #1e293b; font-size: 11px; background: #ffffff;'>{label}</td>"
            f"{h_off}{h_def}"
            f"</tr>"
        )

    # Top Efficiency Row
    a_oe = kp_cell(away_data.get("adj_oe", "-"), away_data.get("adj_oe_rk", "-"))
    a_de = kp_cell(away_data.get("adj_de", "-"), away_data.get("adj_de_rk", "-"))
    h_oe = kp_cell(home_data.get("adj_oe", "-"), home_data.get("adj_oe_rk", "-"))
    h_de = kp_cell(home_data.get("adj_de", "-"), home_data.get("adj_de_rk", "-"))

    # Spanning Tempo Row (Centered across Off/Def like KenPom)
    a_tempo_val, a_tempo_rk = away_data.get("tempo", "-"), away_data.get("tempo_rk", "-")
    h_tempo_val, h_tempo_rk = home_data.get("tempo", "-"), home_data.get("tempo_rk", "-")

    eff_label = "Adj. Efficiency" if league.upper() == "NCAAB" else "Off / Def Rating"
    tempo_label = "Adj. Tempo" if league.upper() == "NCAAB" else "Pace (Poss/48m)"

    html = f"""
    <div style="margin: 14px 0 10px 0; border: 1px solid #cbd5e1; border-radius: 8px; overflow: hidden; background: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
        <div style="background: #f8fafc; padding: 6px 10px; text-align: center; border-bottom: 1px solid #cbd5e1; font-weight: 800; font-size: 12px; color: #0f172a;">
            🏀 Scouting Report ({'D-I Adjusted' if league.upper() == 'NCAAB' else 'Per 100 Possessions'})
        </div>
        <table style="width: 100%; border-collapse: collapse; text-align: center; font-size: 11px;">
            <thead>
                <tr style="background-color: #0f172a; color: #ffffff;">
                    <th colspan="2" style="padding: 6px; width: 34%; border-right: 1px solid #334155;">{away_team} ({away_data.get('net_rtg', '-')})</th>
                    <th style="padding: 6px; width: 32%; color: #94a3b8; font-weight: 600;">Category</th>
                    <th colspan="2" style="padding: 6px; width: 34%; border-left: 1px solid #334155;">{home_team} ({home_data.get('net_rtg', '-')})</th>
                </tr>
                <tr style="background-color: #f1f5f9; color: #1d4ed8; font-size: 10px; font-weight: 700; border-bottom: 1px solid #cbd5e1;">
                    <th style="padding: 4px; width: 17%;">Offense</th>
                    <th style="padding: 4px; width: 17%;">Defense</th>
                    <th style="padding: 4px; width: 32%; color: #475569;">Metric</th>
                    <th style="padding: 4px; width: 17%;">Offense</th>
                    <th style="padding: 4px; width: 17%;">Defense</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    {a_oe}{a_de}
                    <td style="padding: 4px 6px; font-weight: 700; color: #0f172a;">{eff_label}</td>
                    {h_oe}{h_de}
                </tr>
                <tr>
                    <td colspan="2" style="background-color: #e0e7ff; padding: 4px; border: 1px solid #ffffff;">
                        <span style="color: #1d4ed8; font-weight: 700;">{a_tempo_val}</span>
                        <span style="color: #334155; font-size: 9px; font-weight: 600;">{a_tempo_rk}</span>
                    </td>
                    <td style="padding: 4px 6px; font-weight: 600; color: #1e293b;">{tempo_label}</td>
                    <td colspan="2" style="background-color: #e0e7ff; padding: 4px; border: 1px solid #ffffff;">
                        <span style="color: #1d4ed8; font-weight: 700;">{h_tempo_val}</span>
                        <span style="color: #334155; font-size: 9px; font-weight: 600;">{h_tempo_rk}</span>
                    </td>
                </tr>
                {section_banner("Four Factors")}
                {dual_row("Effective FG%:", "efg")}
                {dual_row("Turnover %:", "tov")}
                {dual_row("Off. Reb. %:", "orb")}
                {dual_row("FTA/FGA:", "ftr")}
                {section_banner("Miscellaneous Shooting Splits")}
                {dual_row("3P%:", "3p")}
                {dual_row("2P%:", "2p")}
                {dual_row("FT%:", "ft")}
                {section_banner("Style Components")}
                {dual_row("3PA/FGA:", "3par", neutral=True)}
                {dual_row("A/FGM (Ast%):", "afgm", neutral=True)}
                {section_banner("Strength of Schedule")}
                <tr>
                    <td colspan="2" style="background-color: #f8fafc; padding: 4px;">
                        <span style="color: #1d4ed8; font-weight: 700;">{away_data.get('sos', '-')}</span>
                        <span style="color: #334155; font-size: 9px; font-weight: 600;">{away_data.get('sos_rk', '-')}</span>
                    </td>
                    <td style="padding: 4px 6px; font-weight: 600; color: #1e293b;">Overall SOS:</td>
                    <td colspan="2" style="background-color: #f8fafc; padding: 4px;">
                        <span style="color: #1d4ed8; font-weight: 700;">{home_data.get('sos', '-')}</span>
                        <span style="color: #334155; font-size: 9px; font-weight: 600;">{home_data.get('sos_rk', '-')}</span>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
    """
    return html


# --- STANDALONE TEST BLOCK ---
if __name__ == "__main__":
    print("🚀 Booting up KenPom-Style Basketball Analytics Module...\n")
    nba_stats = fetch_all_basketball_stats("NBA")
    ncaab_stats = fetch_all_basketball_stats("NCAAB")

    test_html = "<div style='max-width: 720px; margin: 20px auto;'>"
    test_html += build_basketball_matchup_html("Philadelphia 76ers", "Boston Celtics", "NBA", nba_stats)
    test_html += build_basketball_matchup_html("UCLA Bruins", "Duke Blue Devils", "NCAAB", ncaab_stats)
    test_html += "</div>"

    with open("test_basketball.html", "w", encoding="utf-8") as f:
        f.write(test_html)
    print("\n✅ Saved 'test_basketball.html'! Open it in your browser to preview the KenPom Scouting Report cards.")