"""AcoustID metadata provider."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple
import json
import os
import subprocess
import time
import requests

from dotenv import load_dotenv


def _debug(message: str) -> None:
    if os.getenv("LYRA_DEBUG") == "1":
        print(message)


def fingerprint_file(file_path: Path) -> Optional[Tuple[str, int]]:
    fpcalc = "fpcalc"
    try:
        result = subprocess.run(
            [fpcalc, "-json", str(file_path)],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            _debug(f"AcoustID fpcalc failed: code={result.returncode} stderr={result.stderr.strip()}")
            return None
        data = result.stdout
        if not data:
            _debug("AcoustID fpcalc returned no output")
            return None
        parsed = json.loads(data)
        _debug(f"AcoustID fpcalc ok: duration={parsed.get('duration')} fp_len={len(parsed.get('fingerprint', ''))}")
        return parsed.get("fingerprint"), parsed.get("duration")
    except Exception as exc:
        _debug(f"AcoustID fpcalc exception: {exc}")
        return None


def lookup_fingerprint(fingerprint: str, duration: int) -> Dict:
    api_key = os.getenv("ACOUSTID_API_KEY")
    if not api_key:
        raise RuntimeError("Missing ACOUSTID_API_KEY")

    params = {
        "client": api_key,
        "meta": "recordings+releasegroups+compress",
        "duration": int(duration),
        "fingerprint": fingerprint,
    }

    for attempt in range(1, 4):
        try:
            response = requests.get("https://api.acoustid.org/v2/lookup", params=params, timeout=30)
            response.raise_for_status()
            _debug(f"AcoustID lookup status={response.status_code} attempt={attempt}")
            return response.json()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response else "unknown"
            body = ""
            if exc.response is not None and exc.response.text:
                body = exc.response.text.strip().replace("\n", " ")[:200]
            _debug(f"AcoustID lookup HTTP error: status={status} body={body}")
            time.sleep(2 ** attempt)
        except Exception as exc:
            _debug(f"AcoustID lookup exception: {exc.__class__.__name__}")
            time.sleep(2 ** attempt)

    return {}


if __name__ == "__main__":
    load_dotenv(override=True)
    print("AcoustID provider ready")
