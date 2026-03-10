"""Lyra Protocol: Unified Asset Ingestion & Archival System.

Async swarm that combines metadata resolution (MusicBrainz/Last.fm) with
indexer + node discovery, then routes acquisition through either Slskd or
qBittorrent-compatible transport.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List

import logging as _logging

import aiohttp
import musicbrainzngs
import pylast

# musicbrainzngs prints noisy "uncaught attribute" warnings to stdout — suppress them
_logging.getLogger("musicbrainzngs").setLevel(_logging.ERROR)
import qbittorrentapi
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


NET_INDEXER_URL = _env("LYRA_PROTOCOL_INDEXER_URL", _env("PROWLARR_URL", "http://localhost:9696"))
NET_INDEXER_KEY = _env("LYRA_PROTOCOL_INDEXER_KEY", _env("PROWLARR_API_KEY"))
NET_NODE_URL = _env("LYRA_PROTOCOL_NODE_URL", "http://localhost:5030")
NET_NODE_API_BASE = _env("LYRA_PROTOCOL_NODE_API_BASE", "/api/v0")
NET_NODE_KEY = _env("LYRA_PROTOCOL_NODE_KEY")
NET_NODE_USER = _env("LYRA_PROTOCOL_NODE_USER", "slskd")
NET_NODE_PASS = _env("LYRA_PROTOCOL_NODE_PASS", "slskd")
CACHE_GATEWAY_URL = _env("LYRA_PROTOCOL_CACHE_URL", "https://api.real-debrid.com/rest/1.0")
CACHE_TOKEN = _env("LYRA_PROTOCOL_CACHE_TOKEN", _env("REAL_DEBRID_KEY"))
TRANSPORT_HOST = _env("LYRA_PROTOCOL_TRANSPORT_HOST", "localhost")
TRANSPORT_PORT = int(_env("LYRA_PROTOCOL_TRANSPORT_PORT", "6500"))
TRANSPORT_USER = _env("LYRA_PROTOCOL_TRANSPORT_USER", "admin")
TRANSPORT_PASS = _env("LYRA_PROTOCOL_TRANSPORT_PASS", "admin")

MB_AGENT = (
    _env("LYRA_PROTOCOL_MB_APP", "LyraSystem"),
    _env("LYRA_PROTOCOL_MB_VERSION", "2.0"),
    _env("LYRA_PROTOCOL_MB_CONTACT", "admin@localhost"),
)
LFM_KEY = _env("LASTFM_API_KEY")
LFM_SECRET = _env("LASTFM_API_SECRET", _env("LASTFM_SECRET"))


@dataclass
class DigitalArtifact:
    source: str
    identifier: str
    uri: str
    integrity_score: int
    metadata: Dict[str, Any]


class LyraCortex:
    """Resolve rough artist/title input into canonical metadata."""

    def __init__(self) -> None:
        musicbrainzngs.set_useragent(*MB_AGENT)
        self.lfm = None
        if LFM_KEY and LFM_SECRET:
            self.lfm = pylast.LastFMNetwork(api_key=LFM_KEY, api_secret=LFM_SECRET)

    def resolve_signal(self, artist_input: str, title_input: str) -> Dict[str, Any]:
        intel: Dict[str, Any] = {
            "artist": artist_input,
            "title": title_input,
            "album": None,
            "mbid": None,
            "tags": [],
        }
        try:
            res = musicbrainzngs.search_recordings(
                query=f"artist:{artist_input} AND recording:{title_input}",
                limit=1,
            )
            recording_list = res.get("recording-list", [])
            if recording_list:
                rec = recording_list[0]
                intel["mbid"] = rec.get("id")
                artist_credit = rec.get("artist-credit", [])
                if artist_credit:
                    intel["artist"] = artist_credit[0].get("artist", {}).get("name", intel["artist"])
                intel["title"] = rec.get("title", intel["title"])
                release_list = rec.get("release-list", [])
                if release_list:
                    intel["album"] = release_list[0].get("title")
        except Exception:
            pass

        if self.lfm:
            try:
                track = self.lfm.get_track(intel["artist"], intel["title"])
                intel["tags"] = [t.item.name for t in track.get_top_tags(limit=3)]
            except Exception:
                pass

        return intel


class LyraSwarm:
    """Asynchronous retrieval from Prowlarr + Slskd with RD cache checks."""

    def __init__(self) -> None:
        self.session: aiohttp.ClientSession | None = None
        self._node_token: str = ""
        self.transport = qbittorrentapi.Client(
            host=TRANSPORT_HOST,
            port=TRANSPORT_PORT,
            username=TRANSPORT_USER,
            password=TRANSPORT_PASS,
        )

    def _node_url(self, path: str) -> str:
        base = NET_NODE_URL.rstrip("/")
        api = NET_NODE_API_BASE.strip("/")
        if api:
            return f"{base}/{api}/{path.lstrip('/')}"
        return f"{base}/{path.lstrip('/')}"

    async def _node_headers(self) -> Dict[str, str]:
        if NET_NODE_KEY:
            return {"X-API-Key": NET_NODE_KEY}
        if not self._node_token:
            await self._node_login()
        if self._node_token:
            return {"Authorization": f"Bearer {self._node_token}"}
        return {}

    async def _node_login(self) -> None:
        if self._node_token:
            return
        assert self.session is not None
        try:
            async with self.session.post(
                self._node_url("/session"),
                json={"username": NET_NODE_USER, "password": NET_NODE_PASS},
            ) as response:
                payload = await response.json(content_type=None)
            token = payload.get("token") if isinstance(payload, dict) else None
            self._node_token = token or ""
        except Exception:
            self._node_token = ""

    async def __aenter__(self) -> "LyraSwarm":
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self.session:
            await self.session.close()

    async def _transport_add(self, uri: str) -> None:
        # Primary path: qBittorrent API client.
        try:
            self.transport.auth_log_in()
            self.transport.torrents_add(urls=uri, tags="lyra_ingest")
            return
        except Exception:
            pass

        # Fallback path: direct HTTP calls (works with RDT-Client auth flow).
        assert self.session is not None
        login_url = f"http://{TRANSPORT_HOST}:{TRANSPORT_PORT}/api/v2/auth/login"
        add_url = f"http://{TRANSPORT_HOST}:{TRANSPORT_PORT}/api/v2/torrents/add"

        async with self.session.post(
            login_url,
            data={"username": TRANSPORT_USER, "password": TRANSPORT_PASS},
        ) as login_resp:
            login_text = await login_resp.text()
            if login_resp.status != 200 or "Ok" not in login_text:
                raise RuntimeError(f"Transport login failed: {login_resp.status} {login_text[:120]}")

        async with self.session.post(
            add_url,
            data={"urls": uri, "tags": "lyra_ingest"},
        ) as add_resp:
            if add_resp.status not in {200, 201}:
                body = await add_resp.text()
                raise RuntimeError(f"Transport add failed: {add_resp.status} {body[:200]}")

    async def _verify_cache(self, hashes: List[str]) -> set[str]:
        if not hashes or not CACHE_TOKEN:
            return set()
        assert self.session is not None
        url = f"{CACHE_GATEWAY_URL}/torrents/instantAvailability/{'/'.join(hashes)}"
        try:
            async with self.session.get(url, headers={"Authorization": f"Bearer {CACHE_TOKEN}"}) as response:
                data = await response.json()
            return {h for h, d in data.items() if d and d.get("rd")}
        except Exception:
            return set()

    async def query_indexers(self, query: str, intel: Dict[str, Any]) -> List[DigitalArtifact]:
        if not NET_INDEXER_KEY:
            return []
        assert self.session is not None
        candidates: List[DigitalArtifact] = []
        # Keep indexer queries focused on music releases:
        # 3010=Audio/MP3, 3040=Audio/Lossless
        params = {"query": query, "categories": "3010,3040", "type": "search"}
        try:
            async with self.session.get(
                f"{NET_INDEXER_URL}/api/v1/search",
                params=params,
                headers={"X-Api-Key": NET_INDEXER_KEY},
            ) as response:
                data = await response.json(content_type=None)
        except Exception:
            return []

        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Some indexers return {"results":[...]} while others return raw lists.
            maybe_results = data.get("results")
            items = maybe_results if isinstance(maybe_results, list) else []
        else:
            items = []

        hash_map: Dict[str, Dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            info_hash = (item.get("infoHash") or "").lower()
            if info_hash:
                hash_map[info_hash] = item
                continue
            magnet = item.get("magnetUrl") or ""
            match = re.search(r"btih:([a-zA-Z0-9]+)", magnet)
            if match:
                hash_map[match.group(1).lower()] = item

        cached = await self._verify_cache(list(hash_map.keys()))
        for info_hash, item in hash_map.items():
            is_cached = info_hash in cached
            score = 50
            title_lower = (item.get("title") or "").lower()
            if "flac" in title_lower:
                score += 50
            if is_cached:
                score += 1000
            uri = item.get("magnetUrl") or item.get("downloadUrl") or ""
            if not uri:
                continue
            candidates.append(
                DigitalArtifact(
                    source="cache_verified" if is_cached else "net_indexer",
                    identifier=info_hash,
                    uri=uri,
                    integrity_score=score,
                    metadata=intel,
                )
            )
        return candidates

    async def query_node(self, query: str, intel: Dict[str, Any]) -> List[DigitalArtifact]:
        assert self.session is not None
        headers = await self._node_headers()
        if not headers:
            return []
        try:
            async with self.session.post(
                self._node_url("/searches"),
                json={"searchText": query},
                headers=headers,
            ) as response:
                sid_data = await response.json(content_type=None)
                sid = sid_data.get("id") if isinstance(sid_data, dict) else None
            if not sid:
                return []
            detail_payloads: list[Dict[str, Any]] = []
            seen_ids: set[str] = set()
            query_norm = query.strip().lower()
            min_started = datetime.now(timezone.utc) - timedelta(minutes=20)
            # Slskd search responses can arrive asynchronously and may be split
            # across multiple search ids with identical search text.
            for _ in range(6):
                await asyncio.sleep(3)
                candidate_ids = {sid}
                async with self.session.get(
                    self._node_url("/searches"),
                    headers=headers,
                ) as response:
                    summaries = await response.json(content_type=None)
                if isinstance(summaries, list):
                    for item in summaries:
                        if not isinstance(item, dict):
                            continue
                        st = (item.get("searchText") or "").strip().lower()
                        if st != query_norm:
                            continue
                        started_raw = item.get("startedAt") or ""
                        try:
                            started_dt = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
                        except Exception:
                            started_dt = None
                        if started_dt and started_dt < min_started:
                            continue
                        item_id = item.get("id")
                        if item_id:
                            candidate_ids.add(item_id)
                for cid in candidate_ids:
                    if cid in seen_ids:
                        continue
                    async with self.session.get(
                        self._node_url(f"/searches/{cid}?includeResponses=true"),
                        headers=headers,
                    ) as response:
                        payload = await response.json(content_type=None)
                    if isinstance(payload, dict):
                        detail_payloads.append(payload)
                        seen_ids.add(cid)
                if any(p.get("responses") for p in detail_payloads):
                    break
        except Exception:
            return []
        candidates: List[DigitalArtifact] = []
        for payload in detail_payloads:
            for user in payload.get("responses", []):
                if user.get("locked"):
                    continue
                for item in user.get("files", []):
                    if item.get("isLocked"):
                        continue
                    ext = (item.get("extension") or "").lower()
                    bitrate = item.get("bitRate") or 0
                    score = 0
                    if ext == "flac":
                        score = 90
                    elif ext == "mp3" and bitrate >= 320:
                        score = 60
                    elif ext in {"mp3", "m4a", "aac", "ogg", "opus"} and bitrate >= 192:
                        score = 40
                    elif ext in {"mp3", "m4a", "aac", "ogg", "opus"}:
                        score = 20
                    if score <= 0:
                        continue
                    candidates.append(
                        DigitalArtifact(
                            source="net_node",
                            identifier=item.get("filename") or "",
                            uri=user.get("username") or "",
                            integrity_score=score,
                            metadata=intel,
                        )
                    )
        return [c for c in candidates if c.identifier and c.uri]

    @staticmethod
    def _normalize_title(value: str) -> str:
        s = value or ""
        s = re.sub(r"\s*\((live|remaster(?:ed)?|acoustic|demo|edit|radio edit)[^)]*\)", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*\[(live|remaster(?:ed)?|acoustic|demo|edit|radio edit)[^\]]*\]", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _build_query_variants(self, artist: str, title: str, intel: Dict[str, Any]) -> List[tuple[str, str]]:
        artist_i = (intel.get("artist") or artist).strip()
        title_i = (intel.get("title") or title).strip()
        album_i = (intel.get("album") or "").strip()
        title_n = self._normalize_title(title_i)
        title_raw_n = self._normalize_title(title)

        raw_candidates: List[tuple[str, str]] = []
        if album_i:
            raw_candidates.append((f"{artist_i} {album_i}", f"{artist_i} {title_i}"))
        raw_candidates.append((f"{artist_i} {title_i}", f"{artist_i} {title_i}"))
        if title_n and title_n.lower() != title_i.lower():
            raw_candidates.append((f"{artist_i} {title_n}", f"{artist_i} {title_n}"))
        if title_raw_n and title_raw_n.lower() not in {title_i.lower(), title_n.lower() if title_n else ""}:
            raw_candidates.append((f"{artist_i} {title_raw_n}", f"{artist_i} {title_raw_n}"))
        raw_candidates.append((artist_i, f"{artist_i} {title_i}"))

        variants: List[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for idx_q, node_q in raw_candidates:
            pair = (idx_q.strip(), node_q.strip())
            if not pair[0] or not pair[1]:
                continue
            key = (pair[0].lower(), pair[1].lower())
            if key in seen:
                continue
            seen.add(key)
            variants.append(pair)
        return variants

    async def execute_protocol(self, artist: str, title: str) -> Dict[str, Any]:
        cortex = LyraCortex()
        intel = cortex.resolve_signal(artist, title)
        variants = self._build_query_variants(artist, title, intel)
        artifacts: List[DigitalArtifact] = []
        seen_artifacts: set[tuple[str, str]] = set()

        for indexer_query, node_query in variants:
            results = await asyncio.gather(
                self.query_indexers(indexer_query, intel),
                self.query_node(node_query, intel),
            )
            for group in results:
                for item in group:
                    k = (item.source, item.identifier.lower())
                    if k in seen_artifacts:
                        continue
                    seen_artifacts.add(k)
                    artifacts.append(item)

        artifacts.sort(key=lambda item: item.integrity_score, reverse=True)
        if not artifacts:
            return {
                "status": "no_results",
                "query": f"{intel['artist']} {intel['title']}",
                "attempted_queries": [f"{iq} | {nq}" for iq, nq in variants],
                "intel": intel,
            }

        winner = artifacts[0]
        if winner.source == "net_node":
            assert self.session is not None
            # slskd API: POST /api/v0/transfers/downloads/{username}
            # Body: [{"filename": "...", "size": optional}]
            username = winner.uri  # uri field holds the soulseek username
            payload = [{"filename": winner.identifier}]
            headers = await self._node_headers()
            if not headers:
                return {"status": "failed", "error": "Node authentication failed", "winner": winner}
            try:
                async with self.session.post(
                    self._node_url(f"/transfers/downloads/{username}"),
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status not in (200, 201):
                        body = await response.text()
                        return {
                            "status": "failed",
                            "error": f"slskd enqueue failed: HTTP {response.status} {body[:120]}",
                            "winner": winner,
                        }
            except Exception as exc:
                return {"status": "failed", "error": str(exc), "winner": winner}
            return {"status": "queued", "route": "net_node", "winner": winner}

        try:
            await self._transport_add(winner.uri)
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "winner": winner}
        return {"status": "queued", "route": "transport", "winner": winner}


async def run_lyra_protocol(artist: str, title: str) -> Dict[str, Any]:
    async with LyraSwarm() as swarm:
        return await swarm.execute_protocol(artist, title)
