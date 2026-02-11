# src/acu/parse.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

Point = Tuple[float, float]
Quad = List[Point]


@dataclass(frozen=True)
class ParsedQuad:
    page: int
    quad: Quad


def get_first_content(analysis_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not analysis_result or "result" not in analysis_result:
        return None
    contents = analysis_result.get("result", {}).get("contents", []) or []
    return contents[0] if contents else None


def get_fields(analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    first = get_first_content(analysis_result)
    if not first:
        return {}
    return first.get("fields", {}) or {}


def _unwrap_field_value(field_obj: Dict[str, Any]) -> Any:
    if not isinstance(field_obj, dict):
        return field_obj

    t = field_obj.get("type")
    if t == "string":
        return field_obj.get("valueString")
    if t == "number":
        return field_obj.get("valueNumber")
    if t == "boolean":
        return field_obj.get("valueBoolean")
    if t == "integer":
        return field_obj.get("valueInteger")
    if t == "date":
        return field_obj.get("valueDate")
    if t == "time":
        return field_obj.get("valueTime")
    if t == "object":
        return field_obj.get("valueObject")
    if t == "array":
        items = field_obj.get("valueArray", []) or []
        return [_unwrap_field_value(i) for i in items]

    return field_obj


def flatten_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (fields or {}).items():
        out[k] = _unwrap_field_value(v) if isinstance(v, dict) else v
    return out


_D_QUAD_RE = re.compile(r"D\(([^)]+)\)")


def parse_all_source_quads(source: Any) -> List[ParsedQuad]:
    if not isinstance(source, str):
        return []

    out: List[ParsedQuad] = []
    for inner in _D_QUAD_RE.findall(source):
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) != 9:
            continue

        try:
            page = int(float(parts[0]))
            coords = list(map(float, parts[1:]))
            pts: Quad = list(zip(coords[0::2], coords[1::2]))
            if len(pts) == 4:
                out.append(ParsedQuad(page=page, quad=pts))
        except Exception:
            continue

    return out
