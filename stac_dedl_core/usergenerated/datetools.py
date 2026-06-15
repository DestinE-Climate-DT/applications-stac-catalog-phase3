from datetime import datetime


def is_same_day(datetime1: datetime, datetime2: datetime) -> bool:
    """Check if two datetime objects represent the same calendar day."""
    return datetime1.date() == datetime2.date()
