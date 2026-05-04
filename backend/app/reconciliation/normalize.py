"""Invoice number normalization for matching."""
from __future__ import annotations

import re

# Match runs of digits so we can strip leading zeros per numeric segment
_DIGITS_RE = re.compile(r"\d+")
# Non-alphanumeric, non-slash, non-dot characters to drop
_STRIP_RE = re.compile(r"[^a-z0-9/.]")


def normalize_invoice_no(value: str) -> str:
    """Canonical form for invoice number comparison.

    Steps:
      1. Lowercase
      2. Strip surrounding whitespace
      3. Remove characters that aren't letters, digits, '/', or '.'
         (kills hyphens, spaces, parens, etc.)
      4. Strip leading zeros from each numeric segment

    Decimal '.' is preserved so identifiers like 'mushak-9.1/...' stay intact.

    >>> normalize_invoice_no("INV-0023/2024")
    'inv23/2024'
    """
    s = value.lower().strip()
    s = _STRIP_RE.sub("", s)
    return _DIGITS_RE.sub(lambda m: str(int(m.group(0))), s)
