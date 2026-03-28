"""
UI Formatters — safe formatting utilities for Streamlit dashboard
================================================================
All dashboard display values go through these formatters to prevent
NoneType / TypeError crashes when backend returns null/missing fields.
"""

from typing import Any, Optional


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Safe conversion to float. None / '' / non-numeric → default."""
    if value is None:
        return default
    if value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """Safe conversion to int."""
    if value is None:
        return default
    if value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def fmt_text(value: Any, default: str = "—") -> str:
    """Generic text with fallback."""
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def fmt_number(value: Any, digits: int = 1, default: str = "—") -> str:
    """Number with configurable decimal places."""
    num = safe_float(value)
    if num is None:
        return default
    return f"{num:.{digits}f}"


def fmt_integer(value: Any, default: str = "—") -> str:
    """Integer with thousands separator."""
    num = safe_int(value)
    if num is None:
        return default
    return f"{num:,}"


def fmt_currency(value: Any, symbol: str = "¥", digits: int = 0, default: str = "—") -> str:
    """Currency with configurable symbol and precision."""
    num = safe_float(value)
    if num is None:
        return default
    if digits == 0:
        return f"{symbol}{num:,.0f}"
    return f"{symbol}{num:,.{digits}f}"


def fmt_percent(value: Any, digits: int = 1, default: str = "—", already_percent: bool = False) -> str:
    """Percentage: 0.42 → '42.0%'. already_percent=True: 42 → '42.0%'."""
    num = safe_float(value)
    if num is None:
        return default
    if not already_percent:
        num *= 100
    return f"{num:.{digits}f}%"


def fmt_years(value: Any, digits: int = 1, default: str = "—") -> str:
    """Years display: 2.5 → '2.5年'."""
    num = safe_float(value)
    if num is None:
        return default
    return f"{num:.{digits}f}年"


def fmt_months(value: Any, digits: int = 1, default: str = "—") -> str:
    """Months display."""
    num = safe_float(value)
    if num is None:
        return default
    return f"{num:.{digits}f}个月"


def fmt_area(value: Any, digits: int = 0, default: str = "—") -> str:
    """Area in m²."""
    num = safe_float(value)
    if num is None:
        return default
    return f"{num:,.{digits}f} m²"


def fmt_count(value: Any, unit: str = "", default: str = "—") -> str:
    """Integer count with optional unit."""
    num = safe_int(value)
    if num is None:
        return default
    return f"{num:,}{unit}"


def fmt_delta_percent(value: Any, digits: int = 1, default: Optional[str] = None) -> Optional[str]:
    """
    Streamlit metric delta. Returns None if value is None — this tells
    Streamlit to not show a delta arrow, which is safer than a broken delta.
    """
    num = safe_float(value)
    if num is None:
        return default
    return f"{num:.{digits}f}%"
