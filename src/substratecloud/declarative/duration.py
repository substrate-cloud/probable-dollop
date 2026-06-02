"""Duration parsing — '4h' / '30m' / '1d' / '60s' into timedelta."""

from __future__ import annotations

import re
from datetime import timedelta

_PATTERN = re.compile(r"^(\d+)([smhd])$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(value: str) -> timedelta:
    """Parse a duration string into a timedelta.

    Accepted forms: `<int><unit>` where unit is one of `s`, `m`, `h`, `d`.
    Examples: `60s`, `30m`, `4h`, `1d`.
    """
    m = _PATTERN.match(value)
    if m is None:
        raise ValueError(
            f"invalid duration {value!r}; expected like '60s', '30m', '4h', '1d'"
        )
    n = int(m.group(1))
    unit = m.group(2)
    return timedelta(seconds=n * _UNIT_SECONDS[unit])


def is_valid_duration(value: str) -> bool:
    return _PATTERN.match(value) is not None
