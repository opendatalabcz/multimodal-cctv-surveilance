"""Pytest defaults.

Langfuse stays off for the suite even when a developer ``.env`` enables it.
``load_dotenv()`` does not override variables that are already set.
"""

from __future__ import annotations

import os

os.environ["LANGFUSE_ENABLED"] = "false"
