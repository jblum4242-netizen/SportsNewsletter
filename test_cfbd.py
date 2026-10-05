import os
import requests
import pandas as pd

CFBD_API_KEY = "LrFNn3N2V22VOBJ3r6a+dmw4iUsD84uV5YZdSbROZQacDHu1f3h2wbciIHRQzQsy"

# 1. Grab your API Key exactly how your main script does
    # Reads the global variable defined at the top of the file, or falls back to env vars
api_key = CFBD_API_KEY if CFBD_API_KEY != "YOUR_ACTUAL_API_KEY_HERE" else os.environ.get("CFBD_API_KEY")

print("✅ Found API Key. Pinging CollegeFootballData...")

headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

# --- THE FIX: Pointing to the active advanced stats endpoint ---
url = "https://api.collegefootballdata.com/stats/season/advanced?year=2026"

res = requests.get(url, headers=headers)
print(f"\n--- API RESPONSE STATUS: {res.status_code} ---")

if res.status_code == 200:
    data = res.json()
    if data:
        # Convert to a flat dictionary to see the exact keys
        flat_df = pd.json_normalize(data)
        print("\n📝 RAW COLUMN NAMES RETURNED BY API:")
        for col in flat_df.columns:
            print(f"  - {col}")
            
        print("\n🔍 SAMPLE OHIO STATE RECORD:")
        osu_data = flat_df[flat_df['team'].astype(str).str.contains("Ohio State", case=False, na=False)]
        if not osu_data.empty:
            print(osu_data.iloc[0].to_dict())
        else:
            print("⚠️ 'Ohio State' not found in the response. Team names might be formatted differently.")
    else:
        print("⚠️ API returned a 200 Success, but the JSON array was totally empty []")
else:
    print(f"❌ API Request Failed. Raw response:\n{res.text}")