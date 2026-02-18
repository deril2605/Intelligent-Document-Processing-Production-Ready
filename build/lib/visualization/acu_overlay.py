from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Tuple

import fitz
from PIL import Image, ImageDraw


def _confidence_color(confidence: float | None) -> Tuple[int, int, int, int]:
    if confidence is None:
        return (30, 64, 175, 255)
    if confidence >= 0.9:
        return (22, 163, 74, 255)
    if confidence >= 0.7:
        return (217, 119, 6, 255)
    return (220, 38, 38, 255)


def _parse_source_quads(source: str) -> List[Tuple[int, List[Tuple[float, float]]]]:
    if not isinstance(source, str):
        return []
    quads: List[Tuple[int, List[Tuple[float, float]]]] = []
    for inner in re.findall(r"D\(([^)]+)\)", source):
        parts = [p.strip() for p in inner.split(",")]
        if len(parts) != 9:
            continue
        try:
            page_num = int(float(parts[0]))
            coords = list(map(float, parts[1:]))
        except Exception:
            continue
        points = list(zip(coords[0::2], coords[1::2]))
        if len(points) == 4:
            quads.append((page_num, points))
    return quads


def _extract_raw_field_items(acu_result: Dict[str, Any]) -> Tuple[Dict[int, Dict[str, float]], List[Dict[str, Any]]]:
    result = acu_result.get("result", {})
    contents = result.get("contents", []) if isinstance(result, dict) else []

    pages_by_num: Dict[int, Dict[str, float]] = {}
    items: List[Dict[str, Any]] = []

    for content in contents:
        if not isinstance(content, dict):
            continue

        for page in content.get("pages", []):
            if not isinstance(page, dict):
                continue
            page_num = page.get("pageNumber")
            width = page.get("width")
            height = page.get("height")
            if isinstance(page_num, int) and isinstance(width, (int, float)) and isinstance(height, (int, float)):
                pages_by_num[page_num] = {"width": float(width), "height": float(height)}

        fields = content.get("fields", {})
        if not isinstance(fields, dict):
            continue
        for field_name, field_payload in fields.items():
            if not field_name.endswith("_raw") or not isinstance(field_payload, dict):
                continue
            source = field_payload.get("source")
            if isinstance(source, str):
                items.append(
                    {
                        "field_name": field_name,
                        "confidence": field_payload.get("confidence"),
                        "source": source,
                    }
                )

    return pages_by_num, items


def _to_pixel_points(
    points: List[Tuple[float, float]],
    page_width: float,
    page_height: float,
    image_width: int,
    image_height: int,
) -> List[Tuple[float, float]]:
    return [(x / page_width * image_width, y / page_height * image_height) for x, y in points]


def build_acu_annotated_pages(pdf_data: bytes, acu_result: Dict[str, Any]) -> Dict[int, bytes]:
    """
    Render ACU *_raw field quads to page PNG bytes.
    Returns {page_number: png_bytes}.
    """
    pages_by_num, raw_items = _extract_raw_field_items(acu_result)

    pdf = fitz.open(stream=pdf_data, filetype="pdf")
    if len(pdf) == 0:
        return {}
    images: List[Image.Image] = []
    for page_idx in range(len(pdf)):
        page = pdf[page_idx]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)

    page_to_drawables: Dict[int, List[Dict[str, Any]]] = {}

    for item in raw_items:
        source = item.get("source")
        if not isinstance(source, str):
            continue
        for page_num, quad in _parse_source_quads(source):
            drawables = page_to_drawables.setdefault(page_num, [])
            drawables.append(
                {
                    "field_name": item.get("field_name", "field"),
                    "confidence": item.get("confidence"),
                    "quad": quad,
                }
            )

    output: Dict[int, bytes] = {}
    for page_num in range(1, len(images) + 1):
        drawables = page_to_drawables.get(page_num, [])
        page_meta = pages_by_num.get(page_num)

        image: Image.Image = images[page_num - 1].convert("RGBA")
        draw = ImageDraw.Draw(image, "RGBA")
        img_w, img_h = image.size
        page_w = page_meta["width"] if page_meta else float(img_w)
        page_h = page_meta["height"] if page_meta else float(img_h)

        for entry in drawables:
            points = _to_pixel_points(entry["quad"], page_w, page_h, img_w, img_h)
            color = _confidence_color(entry.get("confidence"))

            draw.line(points + [points[0]], fill=color, width=3)

            x0 = min(p[0] for p in points)
            y0 = min(p[1] for p in points)
            raw_label = str(entry.get("field_name", "field"))
            # Keep overlay labels minimal; remove technical suffixes and confidence text.
            label = raw_label.removesuffix("_raw").removesuffix("_normalized")
            tx = int(max(0, x0))
            ty = int(y0 - 14 if y0 > 16 else y0 + 2)
            # Render label without opaque rectangle to avoid masking PDF content.
            draw.text(
                (tx + 2, ty),
                label[:40],
                fill=(17, 24, 39, 255),
                stroke_width=1,
                stroke_fill=(255, 255, 255, 220),
            )

        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="PNG")
        output[page_num] = buf.getvalue()

    return output
