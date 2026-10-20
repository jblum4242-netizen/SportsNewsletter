import requests
import json

API_KEY = "b6804c0314dde34b6ab248a3b5ea7468ebea43e21972f401c5d3375b39adf44e"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

# Try current season (2027), then fallback to 2026 if preseason ratings aren't published yet
for year in [2027, 2026]:
    url = f"https://kenpom.com/api.php?endpoint=ratings&y={year}"
    print(f"Testing ratings endpoint for {year}: {url}")
    res = requests.get(url, headers=HEADERS, timeout=10)
    print(f"Status: {res.status_code}")
    if res.status_code == 200:
        try:
            data = res.json()
            print(f"Found {len(data)} teams for {year}!")
            # Print sample team keys to check field names
            sample = data[0] if isinstance(data, list) else list(data.values())[0]
            print("\nSample Team Record:")
            print(json.dumps(sample, indent=2))
            break
        except Exception as e:
            print(f"Response not JSON: {res.text[:200]}")
    else:
        print(f"Error {res.status_code}: {res.text[:200]}")