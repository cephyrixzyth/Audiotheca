"""Identifiers for legacy minute-stamped reports and newly allocated scan runs."""

import re
import secrets
from datetime import datetime

STAMP_PATTERN = r"\d{8}_\d{4}(?:\d{2}_\d{6}_[a-f0-9]{12})?"
STAMP_RE = re.compile(rf"^{STAMP_PATTERN}$")
SUMMARY_RE = re.compile(rf"^Run_Summary_({STAMP_PATTERN})\.txt$")


def new_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f_") + secrets.token_hex(6)
