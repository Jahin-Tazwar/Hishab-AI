"""
HishabAI Backend — Bangladesh-Specific Formatting Utilities

Currency (BDT), date, and number formatting for Bangladesh.
South Asian numbering system: lakh (1,00,000) and crore (1,00,00,000).
"""

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from zoneinfo import ZoneInfo

# Bangladesh timezone
BD_TZ = ZoneInfo("Asia/Dhaka")

# Currency
CURRENCY_SYMBOL = "৳"  # Unicode U+09F3
CURRENCY_CODE = "BDT"


def format_bdt(amount: Decimal | float | int, include_symbol: bool = True) -> str:
    """
    Format a number in BDT with South Asian grouping (lakh/crore system).

    Examples:
        1234567.89 → "৳ 12,34,567.89"
        100000     → "৳ 1,00,000.00"
        50.5       → "৳ 50.50"
    """
    amount = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    is_negative = amount < 0
    amount = abs(amount)

    # Split integer and decimal parts
    integer_part = int(amount)
    decimal_part = f"{amount % 1:.2f}"[2:]  # Get "XX" after "0."

    # South Asian grouping: first 3 digits from right, then groups of 2
    s = str(integer_part)
    if len(s) <= 3:
        formatted_int = s
    else:
        # Last 3 digits
        result = s[-3:]
        remaining = s[:-3]
        # Group remaining in pairs from the right
        while remaining:
            result = remaining[-2:] + "," + result
            remaining = remaining[:-2]
        formatted_int = result

    sign = "-" if is_negative else ""
    if include_symbol:
        return f"{sign}{CURRENCY_SYMBOL} {formatted_int}.{decimal_part}"
    return f"{sign}{formatted_int}.{decimal_part}"


def format_date_bd(d: date | datetime) -> str:
    """
    Format a date for Bangladesh official documents: DD/MM/YYYY

    Example: date(2024, 7, 15) → "15/07/2024"
    """
    return d.strftime("%d/%m/%Y")


def format_date_iso(d: date | datetime) -> str:
    """
    Format a date in ISO 8601 for internal storage: YYYY-MM-DD
    """
    return d.strftime("%Y-%m-%d")


def now_bd() -> datetime:
    """Returns current datetime in Bangladesh timezone (UTC+6)."""
    return datetime.now(BD_TZ)


def fiscal_year_label(d: Optional[date] = None) -> str:
    """
    Returns the Bangladesh fiscal year label for a given date.
    Fiscal year runs July 1 to June 30.

    Examples:
        date(2024, 8, 1)  → "FY2024-25"
        date(2024, 3, 15) → "FY2023-24"
    """
    if d is None:
        d = now_bd().date()

    if d.month >= 7:
        return f"FY{d.year}-{str(d.year + 1)[-2:]}"
    else:
        return f"FY{d.year - 1}-{str(d.year)[-2:]}"


def fiscal_year_dates(fy_label: str) -> tuple[date, date]:
    """
    Parse a fiscal year label and return (start_date, end_date).

    Example: "FY2023-24" → (date(2023, 7, 1), date(2024, 6, 30))
    """
    start_year = int(fy_label[2:6])
    return date(start_year, 7, 1), date(start_year + 1, 6, 30)


def validate_bin(value: str) -> bool:
    """Validate Bangladesh BIN (Business Identification Number): exactly 9 digits."""
    return bool(value and len(value) == 9 and value.isdigit())


def validate_tin(value: str) -> bool:
    """Validate Bangladesh TIN (Taxpayer Identification Number): exactly 12 digits."""
    return bool(value and len(value) == 12 and value.isdigit())
