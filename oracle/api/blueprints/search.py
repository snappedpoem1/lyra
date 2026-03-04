"""Search blueprint — semantic, hybrid, LLM rewrite, remixes."""

from __future__ import annotations

import traceback

from flask import Blueprint, jsonify, request

from oracle.validation import validate_search_request, validate_boolean, sanitize_integer

bp = Blueprint("search", __name__)

# ---------------------------------------------------------------------------
# Optional: LLM for query rewriting
# ---------------------------------------------------------------------------

try:
    from oracle.llm import LLMClient
except Exception:
    LLMClient = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# LLM helper (search-specific)
# ---------------------------------------------------------------------------

def _rewrite_search_query_with_llm(query: str, n: int) -> dict:
    """Rewrite free-form query into CLAP-optimised text via local LLM."""
    fallback = {
        "query": query,
        "n": n,
        "used_llm": False,
        "llm": {"status": "unavailable"},
        "intent": "unknown",
        "rationale": "LLM rewrite unavailable; using raw query.",
    }
    if not LLMClient:
        return fallback
    try:
        client = LLMClient.from_env()
        status = client.check_available()
        llm_payload = status.as_dict()
        llm_payload["status"] = "ok" if status.ok else "unavailable"
        fallback["llm"] = llm_payload
        if not status.ok:
            return fallback

        result = client.chat(
            [{"role": "user", "content": query}],
            temperature=0.2,
            max_tokens=180,
            json_schema={
                "name": "search_rewrite",
                "schema": {
                    "type": "object",
                    "properties": {
                        "clap_query": {"type": "string"},
                        "n": {"type": "integer", "minimum": 1, "maximum": 1000},
                        "intent": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["clap_query", "n", "intent", "rationale"],
                    "additionalProperties": False,
                },
            },
            system=(
                "You rewrite music search requests into compact CLAP-friendly audio descriptions. "
                "Focus on sonic traits (texture, tempo, instrumentation, energy, mood). "
                "Keep clap_query concise and retrieval-effective."
            ),
        )
        if not result.get("ok") or "data" not in result:
            fallback["rationale"] = f"LLM rewrite failed: {result.get('error', 'unknown')}"
            return fallback

        payload = result["data"]
        rewritten = (payload.get("clap_query") or "").strip() or query
        rewritten_n = sanitize_integer(payload.get("n", n), default=n, min_val=1, max_val=1000)
        return {
            "query": rewritten,
            "n": rewritten_n,
            "used_llm": rewritten != query or rewritten_n != n,
            "llm": llm_payload,
            "intent": (payload.get("intent") or "unknown").strip() or "unknown",
            "rationale": (payload.get("rationale") or "").strip(),
        }
    except Exception as exc:
        fallback["rationale"] = f"LLM rewrite exception: {exc}"
        return fallback


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/api/search", methods=["POST"])
def api_search():
    """Semantic search endpoint."""
    try:
        from oracle.search import search

        data = request.get_json() or {}
        valid, error, sanitized = validate_search_request(data)
        if not valid:
            return jsonify({"error": error}), 400

        raw_use_rewrite = data.get("rewrite_with_llm", data.get("natural_language", False))
        valid, error, use_rewrite = validate_boolean(raw_use_rewrite, "rewrite_with_llm")
        if not valid:
            return jsonify({"error": error}), 400

        query = sanitized["query"]
        n = sanitized["n"]
        rewrite_meta = {
            "query": query, "n": n, "used_llm": False,
            "intent": "unknown", "rationale": "", "llm": {"status": "not_requested"},
        }
        if use_rewrite:
            rewrite_meta = _rewrite_search_query_with_llm(query, n)
            query = rewrite_meta["query"]
            n = rewrite_meta["n"]

        results = search(query, n=n)
        return jsonify({
            "results": results,
            "count": len(results),
            "original_query": sanitized["query"],
            "query": query,
            "n": n,
            "rewrite": rewrite_meta,
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/search/rewrite", methods=["POST"])
def api_search_rewrite():
    """Rewrite a query with LLM for CLAP search, without running search."""
    try:
        data = request.get_json() or {}
        valid, error, sanitized = validate_search_request(data)
        if not valid:
            return jsonify({"error": error}), 400
        rewrite = _rewrite_search_query_with_llm(sanitized["query"], sanitized["n"])
        return jsonify({
            "original_query": sanitized["query"],
            "query": rewrite["query"],
            "n": rewrite["n"],
            "rewrite": rewrite,
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/search/hybrid", methods=["POST"])
def api_search_hybrid():
    """Hybrid search: semantic + metadata filters + dimensional ranges."""
    try:
        from oracle.search import hybrid_search

        data = request.get_json() or {}
        original_query = (data.get("query") or "").strip()
        query = original_query or None
        filters = data.get("filters") or {}
        dimension_ranges = data.get("dimension_ranges") or data.get("dimensions") or {}
        sort_by = data.get("sort_by") or data.get("sort") or "relevance"
        top_k = sanitize_integer(
            data.get("top_k") or data.get("limit") or 20,
            default=20, min_val=1, max_val=1000,
        )

        valid, error, rewrite_requested = validate_boolean(
            data.get("rewrite_with_llm", data.get("natural_language", False)),
            "rewrite_with_llm",
        )
        if not valid:
            return jsonify({"error": error}), 400

        rewrite_meta = None
        if query and rewrite_requested:
            rewrite_meta = _rewrite_search_query_with_llm(query, top_k)
            query = (rewrite_meta.get("query") or query).strip() or query
            top_k = sanitize_integer(rewrite_meta.get("n", top_k), default=top_k, min_val=1, max_val=1000)

        if not query and not filters:
            return jsonify({"error": "query or filters required"}), 400

        results = hybrid_search(
            query=query,
            filters=filters,
            dimension_ranges=dimension_ranges,
            sort_by=sort_by,
            top_k=top_k,
        )
        response: dict = {"results": results, "count": len(results), "query": query, "top_k": top_k}
        if original_query:
            response["original_query"] = original_query
        if rewrite_meta:
            response["rewrite"] = rewrite_meta
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route("/api/remixes/search", methods=["POST"])
def api_remixes_search():
    """Find and view remix tracks for artist/album/track scopes."""
    try:
        from oracle.search import find_remixes

        data = request.get_json() or {}
        artist = (data.get("artist") or "").strip()
        album = (data.get("album") or "").strip()
        track = (data.get("track") or "").strip()
        n = sanitize_integer(data.get("n", 100), default=100, min_val=1, max_val=1000)
        sort_by = (data.get("sort_by") or "recent").strip().lower()

        valid, error, include_candidates = validate_boolean(
            data.get("include_candidates", True),
            "include_candidates",
        )
        if not valid:
            return jsonify({"error": error}), 400

        if not artist and not album and not track:
            return jsonify({"error": "artist, album, or track is required"}), 400

        results = find_remixes(
            artist=artist or None,
            album=album or None,
            track=track or None,
            n=n,
            include_candidates=include_candidates,
            sort_by=sort_by,
        )
        strict_count = sum(1 for r in results if r.get("is_strict_remix"))
        candidate_count = len(results) - strict_count

        return jsonify({
            "filters": {
                "artist": artist, "album": album, "track": track,
                "n": n, "include_candidates": include_candidates, "sort_by": sort_by,
            },
            "count": len(results),
            "summary": {"strict_remix": strict_count, "candidate": candidate_count},
            "results": results,
        })
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500
