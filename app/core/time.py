"""UTC timestamp helpers matching the database's timezone-naive columns."""
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current UTC time without tzinfo for ``DateTime`` columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
