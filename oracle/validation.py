"""Input validation utilities for Lyra Oracle API."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# ============================================================================
# VALIDATION RULES
# ============================================================================

MAX_QUERY_LENGTH = 500
MAX_NAME_LENGTH = 100
MAX_PATH_LENGTH = 500
MAX_URL_LENGTH = 2048
MAX_RESULTS = 1000
MIN_RESULTS = 1

VALID_MODES = {'hardlink', 'symlink', 'shortcut'}
VALID_PRESETS = {'artist_album', 'genre', 'year'}
VALID_SOURCES = {'youtube', 'prowlarr', 'manual'}


# ============================================================================
# VALIDATORS
# ============================================================================

def validate_query(query: str) -> Tuple[bool, Optional[str]]:
    """Validate search query.
    
    Returns:
        (is_valid, error_message)
    """
    if not query:
        return False, "Query is required"
    
    if not isinstance(query, str):
        return False, "Query must be a string"
    
    query = query.strip()
    if not query:
        return False, "Query cannot be empty or whitespace only"
    
    if len(query) > MAX_QUERY_LENGTH:
        return False, f"Query too long (max {MAX_QUERY_LENGTH} characters)"
    
    # Check for suspicious characters (basic SQL injection prevention)
    suspicious_patterns = [
        r";\s*DROP\s+TABLE",
        r";\s*DELETE\s+FROM",
        r";\s*UPDATE\s+",
        r"--",
        r"/\*.*\*/",
    ]
    for pattern in suspicious_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return False, "Query contains suspicious characters"
    
    return True, None


def validate_name(name: str, field_name: str = "Name") -> Tuple[bool, Optional[str]]:
    """Validate name field (vibe name, etc).
    
    Returns:
        (is_valid, error_message)
    """
    if not name:
        return False, f"{field_name} is required"
    
    if not isinstance(name, str):
        return False, f"{field_name} must be a string"
    
    name = name.strip()
    if not name:
        return False, f"{field_name} cannot be empty or whitespace only"
    
    if len(name) > MAX_NAME_LENGTH:
        return False, f"{field_name} too long (max {MAX_NAME_LENGTH} characters)"
    
    # Check for forbidden characters
    forbidden_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in forbidden_chars:
        if char in name:
            return False, f"{field_name} contains forbidden character: {char}"
    
    return True, None


def validate_count(n: Any, field_name: str = "Count") -> Tuple[bool, Optional[str], Optional[int]]:
    """Validate count parameter (n, limit, etc).
    
    Returns:
        (is_valid, error_message, sanitized_value)
    """
    try:
        n = int(n)
    except (ValueError, TypeError):
        return False, f"{field_name} must be an integer", None
    
    if n < MIN_RESULTS:
        return False, f"{field_name} must be at least {MIN_RESULTS}", None
    
    if n > MAX_RESULTS:
        return False, f"{field_name} cannot exceed {MAX_RESULTS}", None
    
    return True, None, n


def validate_path(path: str, must_exist: bool = False) -> Tuple[bool, Optional[str]]:
    """Validate file/directory path.
    
    Returns:
        (is_valid, error_message)
    """
    if not path:
        return False, "Path is required"
    
    if not isinstance(path, str):
        return False, "Path must be a string"
    
    path = path.strip()
    if not path:
        return False, "Path cannot be empty"
    
    if len(path) > MAX_PATH_LENGTH:
        return False, f"Path too long (max {MAX_PATH_LENGTH} characters)"
    
    # Check for suspicious characters
    if '..' in path:
        return False, "Path traversal not allowed (..)"
    
    if must_exist:
        if not Path(path).exists():
            return False, f"Path does not exist: {path}"
    
    return True, None


def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """Validate URL.
    
    Returns:
        (is_valid, error_message)
    """
    if not url:
        return False, "URL is required"
    
    if not isinstance(url, str):
        return False, "URL must be a string"
    
    url = url.strip()
    if not url:
        return False, "URL cannot be empty"
    
    if len(url) > MAX_URL_LENGTH:
        return False, f"URL too long (max {MAX_URL_LENGTH} characters)"
    
    # Basic URL format check
    if not url.startswith(('http://', 'https://')):
        return False, "URL must start with http:// or https://"
    
    return True, None


def validate_mode(mode: str) -> Tuple[bool, Optional[str]]:
    """Validate materialization mode.
    
    Returns:
        (is_valid, error_message)
    """
    if not mode:
        return False, "Mode is required"
    
    if not isinstance(mode, str):
        return False, "Mode must be a string"
    
    mode = mode.strip().lower()
    if mode not in VALID_MODES:
        return False, f"Invalid mode. Must be one of: {', '.join(VALID_MODES)}"
    
    return True, None


def validate_preset(preset: str) -> Tuple[bool, Optional[str]]:
    """Validate curation preset.
    
    Returns:
        (is_valid, error_message)
    """
    if not preset:
        return False, "Preset is required"
    
    if not isinstance(preset, str):
        return False, "Preset must be a string"
    
    preset = preset.strip().lower()
    if preset not in VALID_PRESETS:
        return False, f"Invalid preset. Must be one of: {', '.join(VALID_PRESETS)}"
    
    return True, None


def validate_confidence(confidence: Any) -> Tuple[bool, Optional[str], Optional[float]]:
    """Validate confidence value (0.0 - 1.0).
    
    Returns:
        (is_valid, error_message, sanitized_value)
    """
    try:
        confidence = float(confidence)
    except (ValueError, TypeError):
        return False, "Confidence must be a number", None
    
    if confidence < 0.0 or confidence > 1.0:
        return False, "Confidence must be between 0.0 and 1.0", None
    
    return True, None, confidence


def validate_boolean(value: Any, field_name: str = "Field") -> Tuple[bool, Optional[str], Optional[bool]]:
    """Validate boolean value.
    
    Returns:
        (is_valid, error_message, sanitized_value)
    """
    if isinstance(value, bool):
        return True, None, value
    
    if isinstance(value, str):
        value_lower = value.lower()
        if value_lower in ('true', '1', 'yes', 'on'):
            return True, None, True
        if value_lower in ('false', '0', 'no', 'off'):
            return True, None, False
    
    if isinstance(value, int):
        return True, None, bool(value)
    
    return False, f"{field_name} must be a boolean", None


# ============================================================================
# COMPOSITE VALIDATORS
# ============================================================================

def validate_search_request(data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict]]:
    """Validate search request payload.
    
    Returns:
        (is_valid, error_message, sanitized_data)
    """
    query = data.get('query', '')
    n = data.get('n', 10)
    
    valid, error = validate_query(query)
    if not valid:
        return False, error, None
    
    valid, error, n = validate_count(n, "Result count")
    if not valid:
        return False, error, None
    
    return True, None, {'query': query.strip(), 'n': n}


def validate_vibe_save_request(data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict]]:
    """Validate vibe save request payload.
    
    Returns:
        (is_valid, error_message, sanitized_data)
    """
    name = data.get('name', '')
    query = data.get('query', '')
    n = data.get('n', 200)
    
    valid, error = validate_name(name, "Vibe name")
    if not valid:
        return False, error, None
    
    valid, error = validate_query(query)
    if not valid:
        return False, error, None
    
    valid, error, n = validate_count(n, "Track count")
    if not valid:
        return False, error, None
    
    return True, None, {
        'name': name.strip(),
        'query': query.strip(),
        'n': n
    }


def validate_vibe_materialize_request(data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict]]:
    """Validate vibe materialize request payload.
    
    Returns:
        (is_valid, error_message, sanitized_data)
    """
    name = data.get('name', '')
    mode = data.get('mode', 'hardlink')
    
    valid, error = validate_name(name, "Vibe name")
    if not valid:
        return False, error, None
    
    valid, error = validate_mode(mode)
    if not valid:
        return False, error, None
    
    return True, None, {
        'name': name.strip(),
        'mode': mode.strip().lower()
    }


# ============================================================================
# SANITIZATION
# ============================================================================

def sanitize_string(s: str, max_length: int = 500) -> str:
    """Sanitize string input.
    
    Args:
        s: Input string
        max_length: Maximum allowed length
    
    Returns:
        Sanitized string
    """
    if not isinstance(s, str):
        return ""
    
    # Strip whitespace
    s = s.strip()
    
    # Truncate if too long
    if len(s) > max_length:
        s = s[:max_length]
    
    # Remove null bytes
    s = s.replace('\x00', '')
    
    return s


def sanitize_integer(n: Any, default: int = 0, min_val: int = 0, max_val: int = 99999) -> int:
    """Sanitize integer input.
    
    Args:
        n: Input value
        default: Default value if invalid
        min_val: Minimum allowed value
        max_val: Maximum allowed value
    
    Returns:
        Sanitized integer
    """
    try:
        n = int(n)
    except (ValueError, TypeError):
        return default
    
    if n < min_val:
        return min_val
    if n > max_val:
        return max_val
    
    return n
