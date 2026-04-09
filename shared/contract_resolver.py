"""Contract resolver: asset_id → TopstepX contract ID.

Resolution priority:
  1. Session cache (populated at startup, survives for process lifetime)
  2. config/contract_ids.json (verified mapping file)
  3. P3-D00 roll_calendar (dynamic, updated by roll management)
  4. TopstepX API search (last resort, one-time per asset)

Usage:
    from shared.contract_resolver import resolve_contract_id, preload_contracts
    preload_contracts()  # Call once at startup
    cid = resolve_contract_id("ES")  # → "CON.F.US.EP.M26"
"""

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# Session-level cache: {asset_id: contract_id}
_cache: dict[str, str] = {}
_cache_lock = threading.Lock()

# Path to verified contract mapping — check both local dev and Docker mount paths
_LOCAL_CONFIG = Path(__file__).resolve().parent.parent / "config" / "contract_ids.json"
_DOCKER_CONFIG = Path("/captain/config/contract_ids.json")
_CONFIG_PATH = _LOCAL_CONFIG if _LOCAL_CONFIG.exists() else _DOCKER_CONFIG


def resolve_contract_id(asset_id: str) -> str | None:
    """Resolve asset_id to TopstepX contract ID.

    Returns None if asset cannot be resolved (caller must handle).
    Thread-safe.
    """
    # 1. Check cache
    cached = _cache.get(asset_id)
    if cached:
        return cached

    # 2. Try config file
    contract_id = _resolve_from_config(asset_id)
    if contract_id:
        with _cache_lock:
            _cache[asset_id] = contract_id
        return contract_id

    # 3. Try P3-D00 roll_calendar
    contract_id = _resolve_from_d00(asset_id)
    if contract_id:
        with _cache_lock:
            _cache[asset_id] = contract_id
        return contract_id

    # 4. TopstepX API search (last resort)
    contract_id = _resolve_from_api(asset_id)
    if contract_id:
        with _cache_lock:
            _cache[asset_id] = contract_id
    return contract_id


def preload_contracts(asset_ids: list[str] | None = None) -> dict[str, str]:
    """Preload contract IDs for all (or specified) assets. Call at startup.

    Returns {asset_id: contract_id} for all resolved assets.
    """
    if asset_ids is None:
        # Load all from config
        config = _load_config()
        asset_ids = list(config.get("contracts", {}).keys())

    resolved = {}
    for asset_id in asset_ids:
        cid = resolve_contract_id(asset_id)
        if cid:
            resolved[asset_id] = cid
        else:
            logger.warning("Could not resolve contract for asset %s", asset_id)
    return resolved


def get_all_contract_ids() -> dict[str, str]:
    """Return current cache of resolved contract IDs."""
    return dict(_cache)


def invalidate(asset_id: str | None = None):
    """Clear cache for one asset or all (e.g., after contract roll)."""
    with _cache_lock:
        if asset_id:
            _cache.pop(asset_id, None)
        else:
            _cache.clear()


# ---------------------------------------------------------------------------
# Resolution backends
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load contract_ids.json."""
    if not _CONFIG_PATH.exists():
        logger.warning("Contract config not found at %s", _CONFIG_PATH)
        return {}
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _resolve_from_config(asset_id: str) -> str | None:
    """Resolve from config/contract_ids.json."""
    config = _load_config()
    entry = config.get("contracts", {}).get(asset_id)
    if entry:
        return entry.get("contract_id")
    return None


def _resolve_from_d00(asset_id: str) -> str | None:
    """Resolve from P3-D00 roll_calendar.topstep_contract_id field."""
    try:
        from shared.questdb_client import get_cursor
        with get_cursor() as cur:
            cur.execute(
                "SELECT roll_calendar FROM p3_d00_asset_universe "
                "LATEST ON last_updated PARTITION BY asset_id WHERE asset_id = %s",
                (asset_id,),
            )
            row = cur.fetchone()
        if row and row[0]:
            cal = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            return cal.get("topstep_contract_id")
    except Exception as e:
        logger.debug("D00 contract lookup failed for %s: %s", asset_id, e)
    return None


def _resolve_from_api(asset_id: str) -> str | None:
    """Last resort: search TopstepX API for the contract."""
    try:
        from shared.topstep_client import get_topstep_client
        client = get_topstep_client()
        contracts = client.search_contracts(asset_id)
        if contracts:
            return contracts[0].get("id")
    except Exception as e:
        logger.debug("API contract search failed for %s: %s", asset_id, e)
    return None
