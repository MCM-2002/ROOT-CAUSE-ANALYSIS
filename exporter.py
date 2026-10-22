"""SVG / PNG / PDF export.

PNG and PDF are produced with CairoSVG when available. If the native Cairo
library is missing (common on Windows), svglib + ReportLab is used as a fallback.
"""
from __future__ import annotations

import io


class ExportError(Exception):
    """User-presentable export failure."""


def export_svg(svg: str) -> bytes:
    if not svg or "<svg" not in svg:
        raise ExportError("There is no diagram to export.")
    return svg.encode("utf-8")


def _cairosvg():
    try:
        import cairosvg  # noqa: WPS433

        return cairosvg
    except Exception:  # ImportError or OSError (missing libcairo)
        return None


def export_png(svg: str, scale: float = 2.0) -> bytes:
    export_svg(svg)
    errors = []
    cs = _cairosvg()
    if cs is not None:
        try:
            return cs.svg2png(bytestring=svg.encode("utf-8"), scale=scale, background_color="white")
        except Exception as exc:
            errors.append(f"cairosvg: {exc}")
    try:
        from reportlab.graphics import renderPM
        from svglib.svglib import svg2rlg

        drawing = svg2rlg(io.StringIO(svg))
        if drawing is None:
            raise ValueError("could not parse SVG")
        return renderPM.drawToString(drawing, fmt="PNG", dpi=int(72 * scale), bg=0xFFFFFF)
    except Exception as exc:
        errors.append(f"svglib: {exc}")
    raise ExportError(
        "PNG export failed. Install the Cairo library (see README) and try again. Details: " + " | ".join(errors)
    )


def export_pdf(svg: str) -> bytes:
    export_svg(svg)
    errors = []
    cs = _cairosvg()
    if cs is not None:
        try:
            return cs.svg2pdf(bytestring=svg.encode("utf-8"))
        except Exception as exc:
            errors.append(f"cairosvg: {exc}")
    try:
        from reportlab.graphics import renderPDF
        from svglib.svglib import svg2rlg

        drawing = svg2rlg(io.StringIO(svg))
        if drawing is None:
            raise ValueError("could not parse SVG")
        return renderPDF.drawToString(drawing)
    except Exception as exc:
        errors.append(f"svglib: {exc}")
    raise ExportError("PDF export failed. Details: " + " | ".join(errors))
