import hashlib
from datetime import datetime, timedelta, timezone
from ..database import cache_get, cache_set

def cache_key(prefix, *parts):
    raw = "|".join(str(p).strip().lower() for p in parts)
    return prefix + ":" + hashlib.sha256(raw.encode()).hexdigest()

def cached(key, days=0, hours=0):
    def decorator(fn):
        async def wrapper(*args, **kwargs):
            value = cache_get(key(*args, **kwargs) if callable(key) else key)
            if value is not None: return value
            value = await fn(*args, **kwargs)
            cache_set(key(*args, **kwargs) if callable(key) else key, value, datetime.now(timezone.utc)+timedelta(days=days,hours=hours))
            return value
        return wrapper
    return decorator

