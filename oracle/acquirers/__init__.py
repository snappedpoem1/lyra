"""Acquisition backends for Lyra Oracle.

Tiered waterfall strategy:
  T1: Qobuz      (hi-fi streaming API -> FLAC up to 24-bit/96kHz)
  T2: Streamrip  (alternative hi-fi ripper fallback)
  T3: Slskd      (peer-to-peer FLAC search via Soulseek)
  T4: Real-Debrid (Prowlarr search -> RD cache -> direct HTTPS download)
  T5: SpotDL     (YouTube with Spotify metadata, always-available fallback)

All tiers gracefully degrade when services aren't available.
"""

from oracle.acquirers.waterfall import acquire, get_tier_status, AcquisitionResult

__all__ = [
    "acquire",
    "get_tier_status",
    "AcquisitionResult",
]
