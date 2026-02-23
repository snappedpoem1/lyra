import requests
import json

url = "http://localhost:5000/api/health"

try:
    response = requests.get(url, timeout=5)
    print(f"Status Code: {response.status_code}")
    print("---")
    try:
        data = response.json()
        print("Response JSON:")
        print(json.dumps(data, indent=2))
    except json.JSONDecodeError:
        print("Failed to decode JSON.")
        print("Raw Response Text:")
        print(response.text)
except requests.exceptions.RequestException as e:
    print(f"Request failed: {e}")
