"""The Biographer — Cultural Context Enrichment.

Fetches artist biographies, imagery, scene context, and cultural positioning
from multiple sources and stores them in the enrich_cache table.

Sources:
    - Wikipedia    (Mediawiki API, free, no key needed)
    - Last.fm      (artist.getInfo — bio, tags, listeners)
    - TheAudioDB   (hi-res imagery — banner, logo, photo)
    - MusicBrainz  (formation year, origin, member list, relationships)
    - Discogs      (additional genre/era context)

Storage:
    enrich_cache (provider='biographer', lookup_key=sha1(artist_name))

Usage::

    from oracle.enrichers.biographer import Biographer

    bio = Biographer()
    data = bio.enrich_artist("Radiohead")
    print(data["bio"])
    print(data["images"]["banner"])

Author: Lyra Oracle — Sprint 1
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

from oracle.enrichers.cache import make_lookup_key, get_or_set_payload, set_cached_payload, get_cached_payload

logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": os.getenv(
        "LYRA_USER_AGENT",
        "LyraOracle/1.0 (github.com/lyra-oracle)",
    )
})

# Cache TTL: 30 days for biographical data (changes rarely)
_CACHE_TTL = int(os.getenv("BIOGRAPHER_CACHE_TTL_SECONDS", str(30 * 24 * 3600)))

_THEAUDIODB_BASE = "https://www.theaudiodb.com/api/v1/json"
_WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1/page/summary"
_WIKIPEDIA_SEARCH = "https://en.wikipedia.org/w/api.php"
_LASTFM_API = "https://ws.audioscrobbler.com/2.0/"


# ---------------------------------------------------------------------------
# Individual source fetchers
# ---------------------------------------------------------------------------


def _safe_get(url: str, params: Optional[Dict] = None, timeout: int = 15) -> Optional[Dict]:
    """GET with retry on 429/5xx. Returns None on failure."""
    for attempt in range(1, 4):
        try:
            resp = _SESSION.get(url, params=params, timeout=timeout)
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            if resp.status_code in {500, 502, 503, 504}:
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                return None
            if resp.status_code == 404:
                return {}
            resp.raise_for_status()
            return resp.json()
        except requests.Timeout:
            if attempt < 3:
                time.sleep(2)
            continue
        except Exception as exc:
            logger.debug("Biographer request failed: %s — %s", url, exc)
            return None
    return None


def _fetch_wikipedia(artist_name: str) -> Dict[str, Any]:
    """Fetch artist bio + origin data from Wikipedia REST API.

    Args:
        artist_name: Artist name to look up.

    Returns:
        Dict with keys: wiki_bio, wiki_url, wiki_thumbnail, wiki_extract.
    """
    if not artist_name.strip():
        return {}

    # 1. Try REST summary directly (fast path)
    safe_title = artist_name.replace(" ", "_")
    data = _safe_get(f"{_WIKIPEDIA_API}/{safe_title}")
    if data and data.get("extract") and data.get("type") != "disambiguation":
        return {
            "wiki_bio": data.get("extract", ""),
            "wiki_url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "wiki_thumbnail": (data.get("thumbnail") or {}).get("source", ""),
            "wiki_extract_first_sentence": (data.get("extract", "").split(". ")[0] + ".") if data.get("extract") else "",
        }

    # 2. Fall back to text search
    search_data = _safe_get(
        _WIKIPEDIA_SEARCH,
        params={
            "action": "query",
            "list": "search",
            "srsearch": f"{artist_name} band music",
            "srlimit": 3,
            "format": "json",
            "origin": "*",
        },
    )
    if not search_data:
        return {}

    results = (search_data.get("query") or {}).get("search", [])
    if not results:
        return {}

    # Pick first result that looks like a band/artist page
    title = results[0].get("title", "")
    if not title:
        return {}

    data = _safe_get(f"{_WIKIPEDIA_API}/{title.replace(' ', '_')}")
    if not data:
        return {}

    return {
        "wiki_bio": data.get("extract", ""),
        "wiki_url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
        "wiki_thumbnail": (data.get("thumbnail") or {}).get("source", ""),
        "wiki_extract_first_sentence": (data.get("extract", "").split(". ")[0] + ".") if data.get("extract") else "",
    }


def _fetch_lastfm_artist(artist_name: str) -> Dict[str, Any]:
    """Fetch artist bio, tags, and stats from Last.fm artist.getInfo.

    Args:
        artist_name: Artist name.

    Returns:
        Dict with keys: lastfm_bio, lastfm_tags, lastfm_listeners,
                        lastfm_playcount, lastfm_similar, lastfm_url.
    """
    api_key = os.getenv("LASTFM_API_KEY", "").strip()
    if not api_key:
        logger.debug("LASTFM_API_KEY missing; skipping Last.fm artist info")
        return {}

    data = _safe_get(
        _LASTFM_API,
        params={
            "method": "artist.getInfo",
            "artist": artist_name,
            "api_key": api_key,
            "format": "json",
            "autocorrect": "1",
        },
    )
    if not data or "artist" not in data:
        return {}

    artist = data["artist"]
    bio_node = artist.get("bio", {})
    wiki_summary = bio_node.get("summary", "") or ""
    # Strip Last.fm's anchor tags
    if "<a href=" in wiki_summary:
        wiki_summary = wiki_summary.split("<a href=", 1)[0].strip()

    tags_node = artist.get("tags", {}).get("tag", [])
    if isinstance(tags_node, dict):
        tags_node = [tags_node]
    tags: List[str] = [
        t.get("name", "").strip().lower()
        for t in tags_node[:8]
        if isinstance(t, dict) and t.get("name")
    ]

    similar_node = artist.get("similar", {}).get("artist", [])
    if isinstance(similar_node, dict):
        similar_node = [similar_node]
    similar: List[str] = [
        s.get("name", "").strip()
        for s in similar_node[:10]
        if isinstance(s, dict) and s.get("name")
    ]

    stats = artist.get("stats", {})
    return {
        "lastfm_bio": wiki_summary,
        "lastfm_tags": tags,
        "lastfm_listeners": _safe_int(stats.get("listeners")),
        "lastfm_playcount": _safe_int(stats.get("playcount")),
        "lastfm_similar": similar,
        "lastfm_url": artist.get("url", ""),
    }


def _fetch_theaudiodb(artist_name: str) -> Dict[str, Any]:
    """Fetch artist imagery from TheAudioDB.

    Args:
        artist_name: Artist name.

    Returns:
        Dict with keys: images (banner, logo, photo, fanart list).
    """
    api_key = os.getenv("THEAUDIODB_API_KEY", "1").strip() or "1"  # free key = "1"
    url = f"{_THEAUDIODB_BASE}/{api_key}/search.php"

    data = _safe_get(url, params={"s": artist_name})
    if not data or not data.get("artists"):
        return {"images": {}}

    artist = data["artists"][0]
    fanart = [v for k, v in artist.items() if k.startswith("strArtistFanart") and v][:5]

    return {
        "images": {
            "thumb": artist.get("strArtistThumb") or "",
            "banner": artist.get("strArtistBanner") or "",
            "logo": artist.get("strArtistLogo") or "",
            "cutout": artist.get("strArtistCutout") or "",
            "fanart": fanart,
        },
        "formation_year": _safe_int(artist.get("intFormedYear")),
        "disbanded_year": _safe_int(artist.get("intDiedYear")),
        "origin_country": artist.get("strCountry") or "",
        "origin_country_code": artist.get("strCountryCode") or "",
        "style": artist.get("strStyle") or "",
        "mood": artist.get("strMood") or "",
        "website": artist.get("strWebsite") or "",
        "facebook": artist.get("strFacebook") or "",
        "twitter": artist.get("strTwitter") or "",
        "theaudiodb_bio": artist.get("strBiographyEN") or "",
    }


def _fetch_musicbrainz_artist(artist_name: str, mbid: Optional[str] = None) -> Dict[str, Any]:
    """Fetch artist metadata from MusicBrainz — using existing musicbrainz module.

    Args:
        artist_name: Artist name (used if mbid is absent).
        mbid: MusicBrainz artist ID (preferred).

    Returns:
        Dict with keys: mbid, begin_date, end_date, area, member_names, genres.
    """
    try:
        from oracle.enrichers import musicbrainz as mb

        if mbid:
            payload = mb.lookup_artist_by_mbid(mbid)
        else:
            payload = mb.search_artist(artist_name)

        if not payload:
            return {}

        # search_artist may return a list; pick first
        if isinstance(payload, list):
            payload = payload[0] if payload else {}

        if not isinstance(payload, dict):
            return {}

        # life-span
        life_span = payload.get("life-span") or {}
        area = payload.get("begin-area") or payload.get("area") or {}
        area_name = area.get("name", "") if isinstance(area, dict) else ""

        # members from relations
        relations = payload.get("relations") or []
        member_names: List[str] = []
        for rel in relations:
            if not isinstance(rel, dict):
                continue
            if rel.get("type") in {"member of band", "member"}:
                artist_node = rel.get("artist") or {}
                name = artist_node.get("name", "")
                if name and name not in member_names:
                    member_names.append(name)

        # genres from tags
        tags = payload.get("tags") or payload.get("genres") or []
        genre_names: List[str] = [
            t.get("name", "").lower()
            for t in tags
            if isinstance(t, dict) and t.get("name")
        ][:8]

        return {
            "artist_mbid": payload.get("id", ""),
            "mb_begin_date": life_span.get("begin", ""),
            "mb_end_date": life_span.get("end", ""),
            "mb_ended": bool(life_span.get("ended")),
            "mb_area": area_name,
            "mb_type": payload.get("type", ""),
            "mb_members": member_names,
            "mb_genres": genre_names,
        }
    except Exception as exc:
        logger.debug("MusicBrainz biographer fetch failed: %s", exc)
        return {}


def _safe_int(val: Any) -> Optional[int]:
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Biographer public API
# ---------------------------------------------------------------------------


class Biographer:
    """Fetches and caches comprehensive artist biographical context.

    Usage::

        bio = Biographer()

        # Full enrich (all sources):
        data = bio.enrich_artist("radiohead")

        # With a known MusicBrainz ID:
        data = bio.enrich_artist("Radiohead", mbid="a74b1b7f-71a5-4011-9441-d0b5e4122711")

        # Force refresh (bypass cache):
        data = bio.enrich_artist("Radiohead", force=True)
    """

    PROVIDER = "biographer"

    def enrich_artist(
        self,
        artist_name: str,
        mbid: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Fetch and cache comprehensive artist biography.

        Combines: Wikipedia + Last.fm + TheAudioDB + MusicBrainz.

        Args:
            artist_name: Artist name (any capitalization).
            mbid: Optional MusicBrainz Artist ID (improves accuracy).
            force: When True, bypasses cache and re-fetches from all sources.

        Returns:
            Merged biography dict with keys:
                artist_name, bio, bio_source, images (dict), formation_year,
                origin, origin_country, mb_members (list), scene, genres (list),
                era, influences (list), influenced (list), social_links (dict),
                lastfm_listeners, lastfm_playcount, lastfm_similar (list),
                lastfm_url, theaudiodb_bio, wiki_url, artist_mbid.
        """
        if not artist_name or not artist_name.strip():
            return {}

        name_clean = artist_name.strip()
        lookup_key = make_lookup_key("biographer", name_clean)

        if not force:
            cached = get_cached_payload(self.PROVIDER, lookup_key, max_age_seconds=_CACHE_TTL)
            if cached:
                logger.debug("Biographer cache hit: %s", name_clean)
                return cached

        logger.info("Biographer: fetching '%s' from all sources ...", name_clean)

        # Fetch from all sources (independent — order doesn't matter)
        wiki = _fetch_wikipedia(name_clean)
        lfm = _fetch_lastfm_artist(name_clean)
        tadb = _fetch_theaudiodb(name_clean)
        mb = _fetch_musicbrainz_artist(name_clean, mbid=mbid)

        # Merge: pick best bio (prioritize TheAudioDB → Wikipedia → Last.fm)
        bio = (
            tadb.get("theaudiodb_bio")
            or wiki.get("wiki_bio")
            or lfm.get("lastfm_bio")
            or ""
        )
        if bio and len(bio) > 2000:
            bio = bio[:2000].rsplit(" ", 1)[0] + "…"

        bio_source = (
            "theaudiodb" if tadb.get("theaudiodb_bio")
            else "wikipedia" if wiki.get("wiki_bio")
            else "lastfm" if lfm.get("lastfm_bio")
            else "none"
        )

        # Merge genres (prefer Last.fm tags + MB genres)
        genres: List[str] = list(dict.fromkeys(
            (lfm.get("lastfm_tags") or []) + (mb.get("mb_genres") or [])
        ))[:10]

        # Determine "era" from formation year
        formation_year = (
            tadb.get("formation_year")
            or _year_from_begin_date(mb.get("mb_begin_date", ""))
        )
        era = _format_era(formation_year, genres)

        # Social links
        social_links: Dict[str, str] = {}
        if tadb.get("website"):
            social_links["website"] = tadb["website"]
        if tadb.get("facebook"):
            social_links["facebook"] = f"https://facebook.com/{tadb['facebook']}"
        if tadb.get("twitter"):
            social_links["twitter"] = f"https://twitter.com/{tadb['twitter'].lstrip('@')}"

        result: Dict[str, Any] = {
            "artist_name": name_clean,
            "bio": bio,
            "bio_source": bio_source,
            # Images
            "images": tadb.get("images") or {},
            "wiki_thumbnail": wiki.get("wiki_thumbnail") or "",
            # Origin
            "formation_year": formation_year,
            "disbanded_year": tadb.get("disbanded_year"),
            "origin": mb.get("mb_area") or tadb.get("origin_country") or "",
            "origin_country": tadb.get("origin_country") or "",
            "origin_country_code": tadb.get("origin_country_code") or "",
            # Members & MusicBrainz
            "artist_mbid": mb.get("artist_mbid") or mbid or "",
            "mb_type": mb.get("mb_type") or "",
            "mb_ended": mb.get("mb_ended") or False,
            "members": mb.get("mb_members") or [],
            # Cultural context
            "genres": genres,
            "scene": _infer_scene(genres),
            "era": era,
            "style": tadb.get("style") or "",
            "mood": tadb.get("mood") or "",
            # Social
            "wiki_url": wiki.get("wiki_url") or "",
            "lastfm_url": lfm.get("lastfm_url") or "",
            "social_links": social_links,
            # Stats
            "lastfm_listeners": lfm.get("lastfm_listeners"),
            "lastfm_playcount": lfm.get("lastfm_playcount"),
            "lastfm_similar": lfm.get("lastfm_similar") or [],
            # Source data
            "theaudiodb_bio": tadb.get("theaudiodb_bio") or "",
            "wiki_extract_first_sentence": wiki.get("wiki_extract_first_sentence") or "",
        }

        set_cached_payload(self.PROVIDER, lookup_key, result)
        logger.info("Biographer: cached '%s' (bio_source=%s)", name_clean, bio_source)
        return result

    def enrich_all_library_artists(
        self,
        limit: int = 0,
        force: bool = False,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """Enrich all unique artists in the library.

        Args:
            limit: Max artists to process (0 = no limit).
            force: Bypass cache for all artists.
            progress_callback: Optional callable(current, total, artist_name).

        Returns:
            Dict with keys: processed, cached, failed, errors.
        """
        from oracle.db.schema import get_connection

        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute(
                "SELECT DISTINCT artist FROM tracks WHERE artist IS NOT NULL AND artist != '' ORDER BY artist"
            )
            rows = c.fetchall()
        finally:
            conn.close()

        artists = [row[0] for row in rows]
        if limit > 0:
            artists = artists[:limit]

        total = len(artists)
        processed = cached = failed = 0
        errors: List[str] = []

        for i, artist_name in enumerate(artists):
            if progress_callback:
                progress_callback(i + 1, total, artist_name)

            lookup_key = make_lookup_key("biographer", artist_name.strip())
            if not force:
                cached_payload = get_cached_payload(self.PROVIDER, lookup_key, max_age_seconds=_CACHE_TTL)
                if cached_payload:
                    cached += 1
                    continue

            try:
                result = self.enrich_artist(artist_name, force=force)
                if result:
                    processed += 1
                else:
                    failed += 1
                    errors.append(f"{artist_name}: empty result")
            except Exception as exc:
                failed += 1
                errors.append(f"{artist_name}: {exc}")
                logger.warning("Biographer failed for '%s': %s", artist_name, exc)

            # polite delay to respect API rate limits
            time.sleep(0.5)

        return {
            "processed": processed,
            "cached": cached,
            "failed": failed,
            "total": total,
            "errors": errors[:20],
        }

    def get_cached(self, artist_name: str) -> Optional[Dict[str, Any]]:
        """Return cached biography for an artist, or None if not cached.

        Args:
            artist_name: Artist name.

        Returns:
            Cached payload dict, or None.
        """
        lookup_key = make_lookup_key("biographer", artist_name.strip())
        return get_cached_payload(self.PROVIDER, lookup_key, max_age_seconds=_CACHE_TTL)

    def enrich_stale_artists(
        self,
        limit: int = 0,
        ttl_seconds: Optional[int] = None,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """Enrich only artists whose cache entry is missing or older than TTL.

        This is the preferred "refresh" path — it never re-fetches fresh data,
        so a full library refresh is cheap when most artists are up to date.

        Args:
            limit: Max artists to enrich this run (0 = no limit).
            ttl_seconds: Override the default TTL (default: ``_CACHE_TTL``).
            progress_callback: Optional callable(current, total, artist_name).

        Returns:
            Dict with keys: processed, skipped, failed, total, errors.
        """
        from oracle.db.schema import get_connection

        effective_ttl = ttl_seconds if ttl_seconds is not None else _CACHE_TTL
        cutoff = time.time() - effective_ttl

        conn = get_connection()
        try:
            c = conn.cursor()
            # Collect all unique library artists
            c.execute(
                "SELECT DISTINCT artist FROM tracks "
                "WHERE artist IS NOT NULL AND artist != '' ORDER BY artist"
            )
            all_artists = [row[0] for row in c.fetchall()]

            # Batch-check which ones need enrichment (missing or stale)
            keys_to_artist = {
                make_lookup_key("biographer", a.strip()): a for a in all_artists
            }
            if keys_to_artist:
                placeholders = ",".join("?" * len(keys_to_artist))
                c.execute(
                    f"SELECT lookup_key, fetched_at FROM enrich_cache "
                    f"WHERE provider = 'biographer' AND lookup_key IN ({placeholders})",
                    list(keys_to_artist.keys()),
                )
                fresh_keys = {
                    row[0]
                    for row in c.fetchall()
                    if row[1] is not None and float(row[1]) > cutoff
                }
            else:
                fresh_keys = set()
        finally:
            conn.close()

        stale_artists = [
            a for k, a in keys_to_artist.items() if k not in fresh_keys
        ]
        if limit > 0:
            stale_artists = stale_artists[:limit]

        total_stale = len(stale_artists)
        processed = skipped = failed = 0
        errors: List[str] = []

        logger.info(
            "Biographer stale refresh: %d/%d artists need enrichment",
            total_stale, len(all_artists),
        )

        for i, artist_name in enumerate(stale_artists):
            if progress_callback:
                progress_callback(i + 1, total_stale, artist_name)
            try:
                result = self.enrich_artist(artist_name, force=False)
                if result:
                    processed += 1
                else:
                    failed += 1
                    errors.append(f"{artist_name}: empty result")
            except Exception as exc:
                failed += 1
                errors.append(f"{artist_name}: {exc}")
                logger.warning("Biographer stale-refresh failed for '%s': %s", artist_name, exc)
            time.sleep(0.5)

        return {
            "processed": processed,
            "skipped": len(all_artists) - total_stale,
            "failed": failed,
            "total_library": len(all_artists),
            "total_stale": total_stale,
            "errors": errors[:20],
        }

    def enrich_new_artists(self, artist_names: List[str]) -> Dict[str, Any]:
        """Enrich artists that have no cache entry at all (new to the library).

        Intended to be called after indexing new tracks. Never refetches existing
        entries regardless of age — use ``enrich_stale_artists`` for TTL-based
        refresh.

        Args:
            artist_names: List of artist name strings (raw, any casing).

        Returns:
            Dict with keys: processed, already_cached, failed, total, errors.
        """
        from oracle.db.schema import get_connection

        unique = list(dict.fromkeys(a.strip() for a in artist_names if a and a.strip()))
        if not unique:
            return {"processed": 0, "already_cached": 0, "failed": 0, "total": 0, "errors": []}

        keys_to_artist = {make_lookup_key("biographer", a): a for a in unique}

        conn = get_connection()
        try:
            c = conn.cursor()
            placeholders = ",".join("?" * len(keys_to_artist))
            c.execute(
                f"SELECT lookup_key FROM enrich_cache "
                f"WHERE provider = 'biographer' AND lookup_key IN ({placeholders})",
                list(keys_to_artist.keys()),
            )
            existing_keys = {row[0] for row in c.fetchall()}
        finally:
            conn.close()

        new_artists = [a for k, a in keys_to_artist.items() if k not in existing_keys]

        processed = already_cached = failed = 0
        already_cached = len(unique) - len(new_artists)
        errors: List[str] = []

        logger.info(
            "Biographer: enriching %d new artists (%d already cached)",
            len(new_artists), already_cached,
        )

        for artist_name in new_artists:
            try:
                result = self.enrich_artist(artist_name, force=False)
                if result:
                    processed += 1
                else:
                    failed += 1
                    errors.append(f"{artist_name}: empty result")
            except Exception as exc:
                failed += 1
                errors.append(f"{artist_name}: {exc}")
                logger.warning("Biographer new-artist enrich failed '%s': %s", artist_name, exc)
            time.sleep(0.5)

        return {
            "processed": processed,
            "already_cached": already_cached,
            "failed": failed,
            "total": len(unique),
            "errors": errors[:20],
        }


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _year_from_begin_date(begin_date: str) -> Optional[int]:
    """Extract year from a MusicBrainz date string like '1991-05-12'."""
    if not begin_date:
        return None
    try:
        return int(begin_date.split("-")[0])
    except (ValueError, IndexError):
        return None


def _format_era(formation_year: Optional[int], genres: List[str]) -> str:
    """Build a human-readable era string.

    Args:
        formation_year: Year band formed.
        genres: Genre tags.

    Returns:
        String like '1990s alternative rock' or '' if insufficient data.
    """
    if not formation_year:
        return ""
    decade = (formation_year // 10) * 10
    genre_part = genres[0] if genres else "music"
    return f"{decade}s {genre_part}"


_SCENE_MAP: Dict[str, List[str]] = {
    "Britpop": ["britpop", "brit pop", "britrock"],
    "Shoegaze": ["shoegaze", "shoegazing", "dream pop", "ethereal wave"],
    "Post-Rock": ["post-rock", "post rock", "instrumental rock"],
    "Grime": ["grime", "uk hip hop", "uk rap"],
    "IDM": ["idm", "intelligent dance music", "electronica"],
    "Nu Metal": ["nu metal", "numetal", "alternative metal"],
    "Grunge": ["grunge", "seattle sound"],
    "Trip-Hop": ["trip-hop", "trip hop", "bristol sound"],
    "New Wave": ["new wave", "synthpop", "synth-pop", "post-punk"],
    "Garage Rock Revival": ["garage rock", "indie rock", "lo-fi"],
    "Electronic": ["electronic", "electro", "techno", "house", "trance"],
}


def _infer_scene(genres: List[str]) -> str:
    """Infer scene/movement from genre tags.

    Args:
        genres: List of genre tag strings.

    Returns:
        Scene name string, or '' if no match.
    """
    genre_set = {g.lower() for g in genres}
    for scene_name, keywords in _SCENE_MAP.items():
        if any(k in g for k in keywords for g in genre_set):
            return scene_name
    return ""
