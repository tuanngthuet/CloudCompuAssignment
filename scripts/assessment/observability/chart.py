"""Render selected C1 CSV series as dependency-free SVG charts."""
import argparse
import csv
from html import escape
from pathlib import Path

COLORS = ["#2563eb", "#dc2626", "#9333ea", "#059669", "#d97706", "#475569"]
OVERVIEW = [
    ("API tasks", ["ecs.api.desired", "ecs.api.running", "ecs.api.pending"]),
    ("EC2 capacity", ["asg.desired", "asg.in_service", "ecs.registered_instances"]),
    ("ALB targets", ["alb.healthy_targets", "alb.unhealthy_targets"]),
]


def contiguous(data):
    """Keep missing samples as visible gaps instead of joining across them."""
    groups = []
    for point in sorted(data):
        if not groups or point[0] != groups[-1][-1][0] + 1:
            groups.append([])
        groups[-1].append(point)
    return groups


def render(rows, names, title):
    width, height = 1100, 500
    left, right, top, bottom = 70, 25, 45, 70
    times = sorted({r["sample_at"] for r in rows})
    series = {name: [] for name in names}
    for row in rows:
        if row["metric"] not in series or row["status"] not in ("OBSERVED", "OVER_INTERVAL") or not row["value"]:
            continue
        try:
            series[row["metric"]].append((times.index(row["sample_at"]), float(row["value"])))
        except ValueError:
            continue
    values = [value for data in series.values() for _, value in data]
    ceiling = max(values + [1])
    plot_w, plot_h = width - left - right, height - top - bottom
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="{left}" y="25" font-family="sans-serif" font-size="18">{escape(title)}</text>',
             f'<path d="M{left} {top}V{height-bottom}H{width-right}" fill="none" stroke="#64748b"/>']
    for i in range(5):
        y = top + plot_h * i / 4
        label = ceiling * (1 - i / 4)
        parts.append(f'<line x1="{left}" x2="{width-right}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e2e8f0"/>')
        parts.append(f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11">{label:.1f}</text>')
    for idx, name in enumerate(names):
        data = series[name]
        if not data:
            continue
        color = COLORS[idx % len(COLORS)]
        for segment in contiguous(data):
            points = " ".join(f"{left + plot_w * x / max(1, len(times)-1):.1f},"
                              f"{top + plot_h * (1-y/ceiling):.1f}" for x, y in segment)
            parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
        for x, y in data:
            parts.append(f'<circle cx="{left + plot_w*x/max(1,len(times)-1):.1f}" '
                         f'cy="{top + plot_h*(1-y/ceiling):.1f}" r="2" fill="{color}"/>')
        parts.append(f'<text x="{left + (idx % 3) * 340}" y="{height-48 + (idx // 3)*18}" '
                     f'font-family="sans-serif" font-size="12" fill="{color}">{escape(name)}</text>')
    if times:
        for x, label in ((left, times[0]), (width-right, times[-1])):
            parts.append(f'<text x="{x}" y="{height-8}" font-family="sans-serif" font-size="11" '
                         f'text-anchor="{"start" if x == left else "end"}">{escape(label)}</text>')
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def render_overview(rows):
    """Three aligned panels with independent count axes and one UTC time axis."""
    width, height = 1100, 800
    left, right, top, panel_h, gap = 75, 25, 65, 180, 50
    times = sorted({row["sample_at"] for row in rows})
    positions = {stamp: i for i, stamp in enumerate(times)}
    plot_w = width - left - right
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<text x="75" y="30" font-family="sans-serif" font-size="20">C1 tasks, EC2 and targets</text>']
    for panel, (title, names) in enumerate(OVERVIEW):
        y0 = top + panel * (panel_h + gap)
        available = {name: [] for name in names}
        for row in rows:
            if row["metric"] not in available or row["status"] != "OBSERVED" or not row["value"]:
                continue
            try:
                available[row["metric"]].append((positions[row["sample_at"]], float(row["value"])))
            except ValueError:
                continue
        ceiling = max([value for data in available.values() for _, value in data] + [1])
        parts.append(f'<text x="{left}" y="{y0-18}" font-family="sans-serif" font-size="14">{escape(title)} (count)</text>')
        parts.append(f'<path d="M{left} {y0}V{y0+panel_h}H{width-right}" fill="none" stroke="#64748b"/>')
        for tick in range(3):
            y = y0 + panel_h * tick / 2
            parts.append(f'<line x1="{left}" x2="{width-right}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e2e8f0"/>')
            parts.append(f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11">{ceiling*(1-tick/2):.1f}</text>')
        for idx, name in enumerate(names):
            data = sorted(available[name])
            color = COLORS[idx]
            for segment in contiguous(data):
                points = " ".join(f"{left + plot_w*x/max(1,len(times)-1):.1f},"
                                  f"{y0 + panel_h*(1-value/ceiling):.1f}" for x, value in segment)
                parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
            for x, value in data:
                parts.append(f'<circle cx="{left + plot_w*x/max(1,len(times)-1):.1f}" '
                             f'cy="{y0 + panel_h*(1-value/ceiling):.1f}" r="2" fill="{color}"/>')
            parts.append(f'<text x="{left+idx*330}" y="{y0+panel_h+19}" font-family="sans-serif" '
                         f'font-size="11" fill="{color}">{escape(name)}{" (missing)" if not data else ""}</text>')
    if times:
        parts.append(f'<text x="{left}" y="{height-10}" font-family="sans-serif" font-size="11">{escape(times[0])}</text>')
        parts.append(f'<text x="{width-right}" y="{height-10}" text-anchor="end" font-family="sans-serif" font-size="11">{escape(times[-1])}</text>')
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metrics_csv", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with args.metrics_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    args.out.mkdir(parents=True, exist_ok=True)
    # One scale per metric: percentages, counts and seconds must not share a y axis.
    for name in sorted({row["metric"] for row in rows}):
        if not any(row["metric"] == name and row["status"] in ("OBSERVED", "OVER_INTERVAL") for row in rows):
            continue
        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
        unit = next((row["unit"] for row in rows if row["metric"] == name and row["unit"]), "")
        (args.out / (safe_name + ".svg")).write_text(render(rows, [name], "C1 " + name + " (" + unit + ")"), encoding="utf-8")
    (args.out / "tasks-ec2-targets.svg").write_text(render_overview(rows), encoding="utf-8")
    print("Charts:", args.out)


if __name__ == "__main__":
    main()
