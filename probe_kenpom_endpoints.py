import requests
import json

API_KEY = "b6804c0314dde34b6ab248a3b5ea7468ebea43e21972f401c5d3375b39adf44e"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

endpoints_to_test = [
    "misc-stats",
    "miscellaneous-stats",
    "miscellaneous_stats",
    "miscstats"
]

print("🔍 Probing KenPom secondary endpoints for 2027...\n")

for ep in endpoints_to_test:
    url = f"https://kenpom.com/api.php?endpoint={ep}&y=2027"
    res = requests.get(url, headers=HEADERS, timeout=10)
    print(f"Endpoint '{ep}': HTTP {res.status_code}")
    if res.status_code == 200:
        try:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                print(f"  -> SUCCESS! Returned {len(data)} records.")
                print(f"  -> Field keys: {list(data[0].keys())[:12]}")
                # Print Duke or first record sample
                sample = next((t for t in data if t.get("TeamName") == "Duke"), data[0])
                print(f"  -> Sample values for {sample.get('TeamName')}:")
                print(json.dumps(sample, indent=2))
        except Exception as e:
            print(f"  -> Response parsing issue: {e}")
    print("-" * 50)