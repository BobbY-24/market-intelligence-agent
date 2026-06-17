from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.models import Asset, PricePoint


def write_ytd_charts(
    generated_at: datetime,
    assets: list[Asset],
    price_histories: dict[str, list[PricePoint]],
    reports_dir: Path,
) -> dict[str, str]:
    charts_dir = reports_dir / "charts" / generated_at.strftime("%Y-%m-%d")
    charts_dir.mkdir(parents=True, exist_ok=True)
    chart_paths: dict[str, str] = {}
    for asset in assets:
        if asset.asset_type not in {"equity", "etf"}:
            continue
        points = price_histories.get(asset.symbol, [])
        if len(points) < 2:
            continue
        output_path = charts_dir / f"{asset.symbol.lower()}-ytd.svg"
        output_path.write_text(_build_svg(asset.symbol, asset.name, points), encoding="utf-8")
        chart_paths[asset.symbol] = output_path.relative_to(reports_dir).as_posix()
    return chart_paths


def _build_svg(symbol: str, name: str, points: list[PricePoint]) -> str:
    width = 760
    height = 240
    pad_left = 56
    pad_right = 20
    pad_top = 28
    pad_bottom = 34
    plot_width = width - pad_left - pad_right
    plot_height = height - pad_top - pad_bottom
    closes = [point.close for point in points]
    min_close = min(closes)
    max_close = max(closes)
    span = max(max_close - min_close, 0.01)
    x_step = plot_width / max(len(points) - 1, 1)

    coords = []
    for index, point in enumerate(points):
        x = pad_left + index * x_step
        normalized = (point.close - min_close) / span
        y = pad_top + plot_height - normalized * plot_height
        coords.append(f"{x:.1f},{y:.1f}")

    start_label = f"{points[0].date.strftime('%b')} {points[0].date.day}"
    end_label = f"{points[-1].date.strftime('%b')} {points[-1].date.day}"
    change_pct = ((points[-1].close / points[0].close) - 1) * 100
    stroke = "#0f766e" if change_pct >= 0 else "#b91c1c"
    fill = "#ccfbf1" if change_pct >= 0 else "#fee2e2"
    plot_bottom = pad_top + plot_height
    points_attr = " ".join(coords)
    polygon_attr = (
        f"{pad_left:.1f},{plot_bottom:.1f} "
        f"{points_attr} "
        f"{width - pad_right:.1f},{plot_bottom:.1f}"
    )

    return "\n".join(
        [
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
                f'height="{height}" viewBox="0 0 {width} {height}" role="img" '
                'aria-labelledby="title desc">'
            ),
            f"<title>{symbol} YTD chart</title>",
            f"<desc>{name} year-to-date closing-price chart.</desc>",
            '<rect width="100%" height="100%" fill="#fffdf8" rx="14"/>',
            _svg_text(pad_left, 18, f"{symbol} YTD", size=16, fill="#1f2937"),
            _svg_text(
                width - pad_right,
                18,
                f"{change_pct:+.2f}%",
                size=14,
                fill="#475569",
                anchor="end",
            ),
            _svg_line(pad_left, plot_bottom, width - pad_right, plot_bottom),
            _svg_line(pad_left, pad_top, pad_left, plot_bottom),
            _svg_text(pad_left, height - 10, start_label, size=12, fill="#64748b"),
            _svg_text(
                width - pad_right,
                height - 10,
                end_label,
                size=12,
                fill="#64748b",
                anchor="end",
            ),
            _svg_text(10, pad_top + 8, f"{max_close:.2f}", size=12, fill="#64748b"),
            _svg_text(10, plot_bottom, f"{min_close:.2f}", size=12, fill="#64748b"),
            f'<polygon points="{polygon_attr}" fill="{fill}" opacity="0.35"/>',
            (
                f'<polyline points="{points_attr}" fill="none" stroke="{stroke}" '
                'stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
            ),
            "</svg>",
            "",
        ]
    )


def _svg_text(
    x: float,
    y: float,
    content: str,
    *,
    size: int,
    fill: str,
    anchor: str | None = None,
) -> str:
    anchor_attr = f' text-anchor="{anchor}"' if anchor else ""
    return (
        f'<text x="{x}" y="{y}"{anchor_attr} font-size="{size}" '
        f'font-family="Georgia, serif" fill="{fill}">{content}</text>'
    )


def _svg_line(x1: float, y1: float, x2: float, y2: float) -> str:
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        'stroke="#cbd5e1" stroke-width="1"/>'
    )
