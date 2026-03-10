"""Diagnose acquisition tier availability."""
import os
import requests
import sys
from dotenv import load_dotenv

load_dotenv(override=True)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def mark_set(value: str | None) -> str:
    return "Set" if value else "Missing"

print("=== Tier 1: Real-Debrid (via Prowlarr) ===\n")

# Check Prowlarr
prowlarr_url = os.getenv("PROWLARR_URL", "http://localhost:9696")
prowlarr_key = os.getenv("PROWLARR_API_KEY")

print(f"PROWLARR_URL: {prowlarr_url}")
print(f"PROWLARR_API_KEY: {mark_set(prowlarr_key)}")

if prowlarr_key:
    try:
        # Public health endpoint (service reachability)
        health = requests.get(f"{prowlarr_url}/health", timeout=5)
        if health.status_code == 200:
            # Authenticated API endpoint (key validity)
            api = requests.get(
                f"{prowlarr_url}/api/v1/system/status",
                headers={"X-Api-Key": prowlarr_key},
                timeout=5,
            )
            if api.status_code == 200:
                print("Prowlarr connection: OK")
            else:
                print(f"Prowlarr API key check: HTTP {api.status_code}")
        else:
            print(f"Prowlarr connection: HTTP {health.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"Prowlarr connection: Connection refused (is Prowlarr running?)")
    except Exception as e:
        print(f"Prowlarr connection: {e}")
else:
    print("Prowlarr connection: Skipped (no API key)")

# Check Real-Debrid
rd_key = os.getenv("REAL_DEBRID_KEY") or os.getenv("REAL_DEBRID_API_KEY")
print(f"\nREAL_DEBRID_KEY: {mark_set(rd_key)}")

if rd_key:
    try:
        resp = requests.get(
            "https://api.real-debrid.com/rest/1.0/user",
            headers={"Authorization": f"Bearer {rd_key}"},
            timeout=5
        )
        if resp.status_code == 200:
            user = resp.json()
            print(f"Real-Debrid connection: OK (user: {user.get('username')})")
            print(f"Premium days remaining: {user.get('premium', 0)}")
        else:
            print(f"Real-Debrid connection: HTTP {resp.status_code}")
    except Exception as e:
        print(f"Real-Debrid connection: {e}")

print("\n=== Tier 2: Slskd ===\n")

slskd_url = os.getenv("LYRA_PROTOCOL_NODE_URL", "http://localhost:5030")
slskd_user = os.getenv("LYRA_PROTOCOL_NODE_USER")
slskd_pass = os.getenv("LYRA_PROTOCOL_NODE_PASS")

print(f"LYRA_PROTOCOL_NODE_URL: {slskd_url}")
print(f"LYRA_PROTOCOL_NODE_USER: {mark_set(slskd_user)}")
print(f"LYRA_PROTOCOL_NODE_PASS: {mark_set(slskd_pass)}")

try:
    resp = requests.get(f"{slskd_url}/api/v0/application", timeout=5)
    if resp.status_code == 200:
        print(f"Slskd connection: OK (no auth needed)")
    elif resp.status_code == 401:
        print(f"Slskd connection: Running (needs auth)")
    else:
        print(f"Slskd connection: HTTP {resp.status_code}")
except requests.exceptions.ConnectionError:
    print(f"Slskd connection: Connection refused (is Slskd running?)")
except Exception as e:
    print(f"Slskd connection: {e}")

print("\n=== Tier 3: SpotDL ===\n")

import shutil
if shutil.which("spotdl"):
    print("spotdl: Installed")
else:
    try:
        __import__("spotdl")
        print("spotdl: Installed (Python module)")
    except ImportError:
        print("spotdl: Not installed")

print("\n=== Summary ===")
print("Tier 1 requires: Prowlarr running + API key + Real-Debrid key")
print("Tier 2 requires: Slskd running")
print("Tier 3 requires: spotdl installed (pip install spotdl)")
