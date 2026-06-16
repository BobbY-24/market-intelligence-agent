from __future__ import annotations

import json
from dataclasses import asdict

from src.models import ReportBundle


def render_json(bundle: ReportBundle) -> str:
    data = asdict(bundle)
    return json.dumps(data, default=str, indent=2, sort_keys=True) + "\n"

