"""
The Hunter - Accelerated Acquisition Engine

Merges Prowlarr indexer search with Real-Debrid instant downloads.
"Instant Gratification" mode for cached torrents.

Workflow:
1. Scout identifies targets
2. Hunter searches Prowlarr
3. Magnet links sent to Real-Debrid
4. Cached torrents = instant HTTPS download
5. Auto-integration to library

Author: Lyra Oracle v9.0
"""

import os
import logging
import requests
<<<<<<< HEAD
import sqlite3
import re
import tempfile
from typing import Optional, List, Dict
from datetime import datetime
=======
import re
from typing import Optional, List, Dict
>>>>>>> fc77b41 (Update workspace state and diagnostics)
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import xml.etree.ElementTree as ET

from oracle.config import get_connection, DOWNLOADS_FOLDER

logger = logging.getLogger(__name__)

# API Configuration
PROWLARR_URL = os.getenv("PROWLARR_URL", "http://localhost:9696")
PROWLARR_API_KEY = os.getenv("PROWLARR_API_KEY", "")
REALDEBRID_API_KEY = os.getenv("REALDEBRID_API_KEY", "") or os.getenv("REAL_DEBRID_KEY", "")
REALDEBRID_BASE_URL = "https://api.real-debrid.com/rest/1.0"
<<<<<<< HEAD
=======
PROWLARR_COOLDOWN_SECONDS = int(os.getenv("LYRA_PROWLARR_COOLDOWN_SECONDS", "300") or "300")
_PROWLARR_DOWN_UNTIL = 0.0
>>>>>>> fc77b41 (Update workspace state and diagnostics)


def _read_local_prowlarr_api_key() -> str:
    """Best-effort read of local Prowlarr API key from config.xml."""
    repo_root = Path(__file__).resolve().parents[1]
    paths = [
        repo_root / "Lyra_Oracle_System" / "config" / "prowlarr" / "config.xml",
        Path("C:/ProgramData/Prowlarr/config.xml"),
        Path(os.getenv("LOCALAPPDATA", "")) / "Prowlarr" / "config.xml",
        Path(os.getenv("APPDATA", "")) / "Prowlarr" / "config.xml",
    ]
    for path in paths:
        if not str(path) or not path.exists():
            continue
        try:
            root = ET.parse(path).getroot()
            key_node = root.find("ApiKey")
            if key_node is not None and key_node.text:
                return key_node.text.strip()
        except Exception:
            continue
    return ""


class Hunter:
    """The Accelerator - Prowlarr + Real-Debrid integration."""
    
    def __init__(self):
        self.conn = get_connection()
        self.session = requests.Session()
        
        # Real-Debrid auth
        if REALDEBRID_API_KEY:
            self.session.headers.update({
                "Authorization": f"Bearer {REALDEBRID_API_KEY}"
            })
    
    def hunt(
        self,
        query: str,
        prefer_cached: bool = True,
        quality_preference: str = "FLAC"
    ) -> List[Dict]:
        """
        Hunt for a release across indexers.
        
        Args:
            query: Search query (artist + title)
            prefer_cached: Prioritize Real-Debrid cached torrents
            quality_preference: FLAC, MP3-320, MP3-V0
        
        Returns:
            List of acquisition targets with priority scores
        """
        logger.info(f"🎯 HUNTER: Acquiring [{query}]")
        
        # Phase 1: Search Prowlarr
        prowlarr_results = self._search_prowlarr(query)
        logger.info(f"  → Prowlarr: {len(prowlarr_results)} results")
        
        if not prowlarr_results:
            logger.warning("  ⚠️  No results from Prowlarr")
            return []
        
        # Phase 2: Check Real-Debrid cache status
        targets = []
        for result in prowlarr_results:
            raw_magnet = result.get("magnetUrl") or ""
            raw_download = result.get("downloadUrl") or ""

            # Normalise: classify URLs as magnet links vs HTTP download URLs
            magnet_url = ""
            download_url = ""

            for url in (raw_magnet, raw_download):
                if not url or url == "None":
                    continue
                if url.startswith("magnet:"):
                    magnet_url = magnet_url or url
                elif url.startswith("http"):
                    download_url = download_url or url

            # Last resort: extract magnet from guid / infoUrl fields
            if not magnet_url:
                for fallback_field in ("guid", "infoUrl", "commentUrl"):
                    val = result.get(fallback_field, "") or ""
                    if val.startswith("magnet:"):
                        magnet_url = val
                        break

            if not magnet_url and not download_url:
                continue

            # Check if cached (instant download) — only works with magnet hashes
            is_cached = False
            rd_link = None

            if REALDEBRID_API_KEY and magnet_url.startswith("magnet:"):
                is_cached, rd_link = self._check_realdebrid_cache(magnet_url)
            elif REALDEBRID_API_KEY and download_url:
                # Try to extract hash from guid for cache check
                guid = result.get("guid", "")
                hash_match = re.search(r"[a-fA-F0-9]{40}", guid)
                if hash_match:
                    fake_magnet = f"magnet:?xt=urn:btih:{hash_match.group(0)}"
                    is_cached, rd_link = self._check_realdebrid_cache(fake_magnet)

            # Calculate priority
            priority = self._calculate_priority(
                result,
                is_cached,
                quality_preference
            )

            targets.append({
                "title": result.get("title"),
                "size": result.get("size"),
                "seeders": result.get("seeders", 0),
                "indexer": result.get("indexer"),
                "magnet": magnet_url,
                "download_url": download_url,
                "is_cached": is_cached,
                "rd_link": rd_link,
                "priority": priority,
                "quality": self._detect_quality(result.get("title", ""))
            })
        
        # Sort by priority first, seeders as tiebreaker
        targets.sort(key=lambda x: (x["priority"], x.get("seeders", 0)), reverse=True)
        
        logger.info(f"  → {len(targets)} targets ranked (top seeders: {targets[0].get('seeders', 0) if targets else 'n/a'})")
        if targets and targets[0]["is_cached"]:
            logger.info(f"  ⚡ CACHED torrent available! Instant download ready.")
        
        return targets
    
    def acquire(self, target: Dict) -> Dict:
        """
        Execute acquisition of a target.
        
        Args:
            target: Target dict from hunt()
        
        Returns:
            Acquisition status
        """
        logger.info(f"📥 HUNTER: Acquiring [{target['title']}]")

        if target.get("is_cached") and target.get("rd_link"):
            # Instant download via Real-Debrid
            return self._download_from_realdebrid(target)
        elif target.get("magnet") and target["magnet"].startswith("magnet:"):
            # Real magnet link → addMagnet
            return self._add_to_realdebrid(target)
        elif target.get("download_url"):
            # Prowlarr .torrent download URL → fetch file → addTorrent
            return self._add_torrent_to_realdebrid(target)
        else:
            logger.error("  ✗ No valid download method")
            return {"status": "failed", "error": "no_download_method"}
    
    def _search_prowlarr(self, query: str) -> List[Dict]:
        """Search Prowlarr indexers."""
<<<<<<< HEAD
=======
        global _PROWLARR_DOWN_UNTIL
        now = time.time()
        if now < _PROWLARR_DOWN_UNTIL:
            remaining = int(_PROWLARR_DOWN_UNTIL - now)
            logger.warning(f"  Prowlarr cooling down after recent failure ({remaining}s remaining)")
            return []

>>>>>>> fc77b41 (Update workspace state and diagnostics)
        candidate_keys: List[str] = []
        if PROWLARR_API_KEY:
            candidate_keys.append(PROWLARR_API_KEY.strip())

        local_key = _read_local_prowlarr_api_key()
        if local_key and local_key not in candidate_keys:
            candidate_keys.append(local_key)

        if not candidate_keys:
            logger.warning("  Prowlarr API key not configured")
            return []

        for idx, key in enumerate(candidate_keys):
            try:
                response = requests.get(
                    f"{PROWLARR_URL}/api/v1/search",
                    headers={"X-Api-Key": key},
                    params={
                        "query": query,
                        "categories": "3000",
                    },
                    timeout=30,
                )

                if response.status_code == 200:
<<<<<<< HEAD
=======
                    _PROWLARR_DOWN_UNTIL = 0.0
>>>>>>> fc77b41 (Update workspace state and diagnostics)
                    if idx > 0:
                        logger.info("  Prowlarr auth recovered via local config key")
                    return response.json()

                if response.status_code == 401 and idx < len(candidate_keys) - 1:
                    logger.warning("  Prowlarr key unauthorized, retrying with fallback key")
                    continue

<<<<<<< HEAD
=======
                if response.status_code >= 500:
                    _PROWLARR_DOWN_UNTIL = time.time() + PROWLARR_COOLDOWN_SECONDS
>>>>>>> fc77b41 (Update workspace state and diagnostics)
                logger.error(f"  Prowlarr error: {response.status_code}")
                return []

            except Exception as e:
<<<<<<< HEAD
=======
                _PROWLARR_DOWN_UNTIL = time.time() + PROWLARR_COOLDOWN_SECONDS
>>>>>>> fc77b41 (Update workspace state and diagnostics)
                logger.error(f"  Prowlarr search failed: {e}")
                return []

        return []

    def _check_realdebrid_cache(self, magnet: str) -> tuple[bool, Optional[str]]:
        """
        Check if torrent is cached on Real-Debrid.

        Returns:
            (is_cached, download_link)
        """
        if not REALDEBRID_API_KEY:
            return False, None

        try:
            # Extract hash from magnet link
            hash_match = re.search(r"btih:([a-fA-F0-9]+)", magnet)
            if not hash_match:
                return False, None
            
            torrent_hash = hash_match.group(1)
            
            # Check instant availability
            response = self.session.get(
                f"{REALDEBRID_BASE_URL}/torrents/instantAvailability/{torrent_hash}",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                # If data is not empty, torrent is cached
                if data.get(torrent_hash):
                    logger.info(f"  ⚡ Torrent cached on Real-Debrid!")
                    return True, None
            
            return False, None
        
        except Exception as e:
            logger.error(f"  ✗ Real-Debrid cache check failed: {e}")
            return False, None
    
    def _add_to_realdebrid(self, target: Dict) -> Dict:
        """
        Add magnet to Real-Debrid and initiate download.
        """
        if not REALDEBRID_API_KEY:
            return {"status": "failed", "error": "no_api_key"}

        try:
            # Add magnet
            logger.info("  → Adding magnet to Real-Debrid...")
            response = self.session.post(
                f"{REALDEBRID_BASE_URL}/torrents/addMagnet",
                data={"magnet": target["magnet"]},
                timeout=10
            )

            if response.status_code != 201:
                logger.warning(f"  ⚠️  addMagnet returned {response.status_code}: {response.text[:200]}")
                # Fall back to .torrent download if we have a Prowlarr URL
                if target.get("download_url"):
                    logger.info("  → Falling back to .torrent upload...")
                    return self._add_torrent_to_realdebrid(target)
                return {"status": "failed", "error": "add_magnet_failed"}

            torrent_id = response.json().get("id")
            logger.info(f"  → Torrent ID: {torrent_id}")

            return self._wait_and_download(torrent_id, target)

        except Exception as e:
            logger.error(f"  ✗ Real-Debrid acquisition failed: {e}")
            return {"status": "failed", "error": str(e)}

    def _wait_and_download(self, torrent_id: str, target: Dict) -> Dict:
        """
        Wait for RD to process a torrent, select files, and download.
        Shared by both addMagnet and addTorrent flows.
        """
        try:
            # Wait for torrent info
            time.sleep(2)

            # Get torrent info
            response = self.session.get(
                f"{REALDEBRID_BASE_URL}/torrents/info/{torrent_id}",
                timeout=10
            )

            if response.status_code != 200:
                return {"status": "failed", "error": "get_info_failed"}

            info = response.json()

            # Select audio files preferentially, fall back to all
            audio_exts = {'.flac', '.mp3', '.wav', '.aac', '.ogg', '.m4a', '.wma', '.opus', '.alac'}
            files = info.get("files", [])
            audio_ids = [str(f["id"]) for f in files
                         if any(f.get("path", "").lower().endswith(ext) for ext in audio_exts)]
            file_ids = ",".join(audio_ids) if audio_ids else ",".join(str(f["id"]) for f in files)

            response = self.session.post(
                f"{REALDEBRID_BASE_URL}/torrents/selectFiles/{torrent_id}",
                data={"files": file_ids},
                timeout=10
            )

            if response.status_code != 204:
                return {"status": "failed", "error": "select_files_failed"}

            n_files = len(audio_ids) or len(files)
            logger.info(f"  → {n_files} files selected. Waiting for download...")

            # Shorter timeout for uncached torrents (they can take ages)
            is_cached = target.get("is_cached", False)
            max_wait = 30 if not is_cached else 120

            waited = 0
            while waited < max_wait:
                time.sleep(5)
                waited += 5

                try:
                    response = self.session.get(
                        f"{REALDEBRID_BASE_URL}/torrents/info/{torrent_id}",
                        timeout=15
                    )
                except (requests.ConnectionError, requests.Timeout) as e:
                    logger.warning(f"  ⚠️  Connection hiccup ({e.__class__.__name__}), retrying...")
                    time.sleep(3)
                    continue

                if response.status_code == 200:
                    torrent_info = response.json()
                    status = torrent_info.get("status")
                    progress = torrent_info.get("progress", 0)
                    if status == "downloaded":
                        logger.info("  ✓ Download complete!")
                        break
                    elif status in ("error", "magnet_error", "virus", "dead"):
                        logger.error(f"  ✗ RD torrent error: {status}")
                        return {"status": "failed", "error": status}
                    elif waited % 15 == 0:
                        logger.info(f"  ⏳ RD progress: {progress}% ({status})")

            # Get download links
            response = self.session.get(
                f"{REALDEBRID_BASE_URL}/torrents/info/{torrent_id}",
                timeout=10
            )

            if response.status_code == 200:
                info = response.json()
                links = info.get("links", [])
                if links:
                    # Unrestrict first link
                    return self._download_from_link(links[0], target)

            # Timed out but torrent is still alive on RD — return pending
            return {"status": "pending", "error": "no_download_link", "torrent_id": torrent_id}

        except Exception as e:
            logger.error(f"  ✗ Real-Debrid wait/download failed: {e}")
            return {"status": "failed", "error": str(e)}
    
    def _add_torrent_to_realdebrid(self, target: Dict) -> Dict:
        """
        Download .torrent file from Prowlarr, upload to Real-Debrid addTorrent.
        """
        if not REALDEBRID_API_KEY:
            return {"status": "failed", "error": "no_api_key"}

        try:
            download_url = target.get("download_url", "")

            # Safety: if the URL is actually a magnet, route to addMagnet
            if download_url.startswith("magnet:"):
                target["magnet"] = download_url
                return self._add_to_realdebrid(target)

            if not download_url or not download_url.startswith("http"):
                logger.error(f"  ✗ Invalid download URL: {download_url[:80]}")
                return {"status": "failed", "error": "invalid_download_url"}

            logger.info("  → Downloading .torrent from Prowlarr...")

            # Don't follow redirects — some indexers redirect to magnet links
            torrent_resp = requests.get(download_url, timeout=30, allow_redirects=False)

            # Handle redirect to magnet link
            if torrent_resp.status_code in (301, 302, 303, 307, 308):
                location = torrent_resp.headers.get("Location", "")
                if location.startswith("magnet:"):
                    logger.info("  → Prowlarr redirected to magnet link")
                    target["magnet"] = location
                    return self._add_to_realdebrid(target)
                # Normal HTTP redirect — follow it
                torrent_resp = requests.get(location, timeout=30, allow_redirects=False)

            if torrent_resp.status_code != 200:
                logger.error(f"  ✗ Prowlarr download failed: {torrent_resp.status_code}")
                return {"status": "failed", "error": f"prowlarr_download_{torrent_resp.status_code}"}

            torrent_bytes = torrent_resp.content

            # Check if Prowlarr returned a magnet link as text instead of a .torrent file
            if len(torrent_bytes) < 500:
                text = torrent_bytes.decode("utf-8", errors="ignore").strip()
                if text.startswith("magnet:"):
                    logger.info("  → Prowlarr returned magnet link as body")
                    target["magnet"] = text
                    return self._add_to_realdebrid(target)

            if len(torrent_bytes) < 50:
                logger.error("  ✗ Prowlarr returned empty/invalid torrent")
                return {"status": "failed", "error": "invalid_torrent_file"}

            # Upload to Real-Debrid addTorrent (raw binary PUT)
            logger.info("  → Uploading torrent to Real-Debrid...")
            rd_resp = self.session.put(
                f"{REALDEBRID_BASE_URL}/torrents/addTorrent",
                data=torrent_bytes,
                headers={"Content-Type": "application/octet-stream"},
                timeout=15,
            )

            if rd_resp.status_code not in (200, 201):
                logger.error(f"  ✗ RD addTorrent failed: {rd_resp.status_code} {rd_resp.text[:200]}")
                return {"status": "failed", "error": "rd_add_torrent_failed"}

            torrent_id = rd_resp.json().get("id")
            logger.info(f"  → Torrent ID: {torrent_id}")

            # From here it's the same flow: select files, wait, download
            return self._wait_and_download(torrent_id, target)

        except Exception as e:
            logger.error(f"  ✗ Torrent upload acquisition failed: {e}")
            return {"status": "failed", "error": str(e)}

    def _download_from_realdebrid(self, target: Dict) -> Dict:
        """Download file from Real-Debrid HTTPS link."""
        # Route through magnet or torrent depending on what we have
        if target.get("magnet") and target["magnet"].startswith("magnet:"):
            return self._add_to_realdebrid(target)
        elif target.get("download_url"):
            return self._add_torrent_to_realdebrid(target)
        return {"status": "failed", "error": "no_download_method"}
    
    def _download_from_link(self, link: str, target: Dict) -> Dict:
        """
        Unrestrict Real-Debrid link and download file.
        """
        try:
            # Unrestrict link
            response = self.session.post(
                f"{REALDEBRID_BASE_URL}/unrestrict/link",
                data={"link": link},
                timeout=10
            )
            
            if response.status_code != 200:
                return {"status": "failed", "error": "unrestrict_failed"}
            
            data = response.json()
            download_url = data.get("download")
            
            if not download_url:
                return {"status": "failed", "error": "no_download_url"}
            
            # Download file
            logger.info(f"  → Downloading from {download_url}")
            
            filename = data.get("filename", "download")
            output_path = Path(DOWNLOADS_FOLDER) / filename
            
            response = self.session.get(download_url, stream=True, timeout=None)
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"  ✓ Downloaded: {output_path}")
            
            return {
                "status": "completed",
                "file_path": str(output_path),
                "filename": filename
            }
        
        except Exception as e:
            logger.error(f"  ✗ Download failed: {e}")
            return {"status": "failed", "error": str(e)}
    
    # ── Sweep helpers (check / download pending RD torrents) ──

    def list_rd_torrents(self, limit: int = 50) -> List[Dict]:
        """List recent torrents on Real-Debrid account.

        Returns list of {id, filename, status, progress, links, ...}.
        """
        try:
            resp = self.session.get(
                f"{REALDEBRID_BASE_URL}/torrents",
                params={"limit": limit},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"  \u26a0\ufe0f  RD list torrents: {resp.status_code}")
            return []
        except Exception as e:
            logger.warning(f"  \u26a0\ufe0f  RD list torrents error: {e}")
            return []

    def check_torrent(self, torrent_id: str) -> Dict:
        """Check status of a previously submitted RD torrent."""
        try:
            resp = self.session.get(
                f"{REALDEBRID_BASE_URL}/torrents/info/{torrent_id}",
                timeout=10,
            )
            if resp.status_code != 200:
                return {"status": "unknown"}
            info = resp.json()
            return {
                "status": info.get("status"),
                "progress": info.get("progress", 0),
                "links": info.get("links", []),
                "filename": info.get("filename", ""),
            }
        except Exception as e:
            logger.warning(f"  ⚠️  check_torrent error: {e}")
            return {"status": "unknown"}

    def download_torrent_links(self, links: List[str], max_workers: int = 4) -> List[str]:
        """Unrestrict and download RD links in parallel. Returns local paths."""
        paths: List[str] = []
        if not links:
            return paths

        def _grab(link: str) -> Dict:
            return self._download_from_link(link, {})

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_grab, lnk): lnk for lnk in links}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result.get("status") == "completed":
                        paths.append(result["file_path"])
                except Exception as e:
                    logger.warning(f"  \u26a0\ufe0f  Parallel download error: {e}")
        return paths

    def _calculate_priority(
        self,
        result: Dict,
        is_cached: bool,
        quality_pref: str
    ) -> float:
        """
        Calculate acquisition priority.
        
        Scoring (seeder-weighted):
        - Seeders:       up to 0.50 (dominant factor — dead torrents are useless)
        - Cached on RD:  +0.30
        - Quality match: +0.15
        - Discography:   +0.05 (bonus for full artist torrents)
        """
        score = 0.0
        title = result.get("title", "").upper()
        seeders = result.get("seeders", 0) or 0

        # Seeders — dominant factor (scale 0-0.50)
        if seeders >= 50:
            score += 0.50
        elif seeders >= 20:
            score += 0.40
        elif seeders >= 10:
            score += 0.30
        elif seeders >= 5:
            score += 0.20
        elif seeders >= 1:
            score += 0.10
        # 0 seeders = +0.00 (dead torrent, ranked last)

        # Cached torrents are instant
        if is_cached:
            score += 0.30

        # Quality preference
        if quality_pref in title:
            score += 0.15
        elif "FLAC" in title and quality_pref != "MP3-320":
            score += 0.10

        # Discography bonus — full catalog in one grab
        if "DISCOGRAPHY" in title or "DISCOGRAFIA" in title or "COMPLETE" in title:
            score += 0.05

        return score
    
    def _detect_quality(self, title: str) -> str:
        """Detect quality from release title."""
        title_upper = title.upper()
        if "FLAC" in title_upper:
            return "FLAC"
        elif "320" in title_upper or "320KBPS" in title_upper:
            return "MP3-320"
        elif "V0" in title_upper:
            return "MP3-V0"
        else:
            return "Unknown"


# Singleton instance
hunter = Hunter()


# CLI interface
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    if len(sys.argv) < 2:
        print("\n🎯 Lyra Hunter - Accelerated Acquisition\n")
        print("Usage:")
        print("  python -m oracle.hunter hunt <query>   - Search and rank targets")
        print("  python -m oracle.hunter acquire <idx>  - Acquire target by index")
        print("\nExample:")
        print('  python -m oracle.hunter hunt "Daft Punk Random Access Memories FLAC"')
        print("\nRequires:")
        print("  - PROWLARR_URL and PROWLARR_API_KEY in .env")
        print("  - REALDEBRID_API_KEY in .env (optional, for instant downloads)\n")
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "hunt" and len(sys.argv) >= 3:
        query = " ".join(sys.argv[2:])
        targets = hunter.hunt(query)
        
        print(f"\n🎯 HUNT RESULTS: {len(targets)} targets\n")
        for i, target in enumerate(targets, 1):
            cached = "⚡ CACHED" if target["is_cached"] else ""
            print(f"{i:2}. [{target['priority']:.2f}] {cached}")
            print(f"    {target['title']}")
            print(f"    Quality: {target['quality']} | Seeders: {target['seeders']} | Size: {target.get('size', 'Unknown')}")
            print(f"    Indexer: {target['indexer']}")
            print()
    
    else:
        print("\n✗ Invalid command. Run with no args for help.\n")


