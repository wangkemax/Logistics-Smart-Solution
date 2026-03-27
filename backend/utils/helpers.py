"""Utility helper functions for the Logistics Presale AI system."""
from typing import Any, Dict, List, Optional
import os
import json
from datetime import datetime


def format_currency(amount: float, unit: str = "万元") -> str:
    """Format a numeric amount as a currency string."""
    if unit == "万元":
        return f"¥{amount / 10000:.1f}万元"
    return f"¥{amount:,.0f}元"


def format_percentage(value: float) -> str:
    """Format a decimal ratio as a percentage string."""
    return f"{value * 100:.1f}%"


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max."""
    return max(min_val, min(max_val, value))


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, returning default if denominator is zero."""
    if denominator == 0:
        return default
    return numerator / denominator


def load_csv_as_dict(filepath: str) -> List[Dict[str, Any]]:
    """Load a CSV file and return as a list of dicts."""
    try:
        import pandas as pd
        df = pd.read_csv(filepath)
        return df.to_dict(orient="records")
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"Error loading CSV {filepath}: {e}")
        return []


def ensure_dir(path: str) -> None:
    """Ensure a directory exists, creating it if necessary."""
    os.makedirs(path, exist_ok=True)


def get_project_root() -> str:
    """Return the absolute path to the project root directory."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_data_path(filename: str) -> str:
    """Return the absolute path to a file in the data directory."""
    return os.path.join(get_project_root(), "data", filename)


def now_iso() -> str:
    """Return current UTC datetime as ISO 8601 string."""
    return datetime.utcnow().isoformat() + "Z"


def level_to_numeric(level: str, mapping: Optional[Dict[str, float]] = None) -> float:
    """Convert a level string (低/中/高) to a numeric value."""
    if mapping is None:
        mapping = {"低": 0.5, "中": 1.0, "高": 1.5}
    return mapping.get(level, 1.0)


def summarize_profile(profile: Dict[str, Any]) -> str:
    """Generate a brief human-readable summary of a project profile."""
    parts = [
        f"行业: {profile.get('industry', 'N/A')}",
        f"面积: {profile.get('warehouse_area', 0):,}㎡",
        f"SKU: {profile.get('sku_count', 0):,}",
        f"日订单: {profile.get('daily_orders', 0):,}",
    ]
    return " | ".join(parts)
