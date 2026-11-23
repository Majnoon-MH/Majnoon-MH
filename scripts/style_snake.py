#!/usr/bin/env python3
"""
Give a snake SVG a violet gradient background.

    python3 scripts/style_snake.py dist/snake-neon.svg dark
    python3 scripts/style_snake.py dist/snake.svg light

What it does:
  1. adds a violet gradient rectangle behind the grid
  2. makes the EMPTY squares see-through, so the gradient shows in them
If the snake file looks different one day, it only prints a warning and
leaves the file as it is (the snake still works, just without violet).
"""
import re
import sys

THEMES = {
    # gradient stops (left-top -> right-bottom), empty squares, square border
    "dark": (["#1e1038", "#4c1d95", "#7c3aed"], "rgba(255,255,255,0.12)", "rgba(255,255,255,0.10)"),
    "light": (["#f5f3ff", "#ddd6fe", "#c4b5fd"], "rgba(255,255,255,0.70)", "rgba(76,29,149,0.15)"),
}


def style(svg, theme):
    stops, empty, border = THEMES[theme]

    # 1) empty squares: --ce (empty) and --c0 (0 contributions)
    svg, n1 = re.subn(r"--ce:[^;}]+", f"--ce:{empty}", svg, count=1)
    svg, n2 = re.subn(r"--c0:[^;}]+", f"--c0:{empty}", svg, count=1)
    svg = re.sub(r"--cb:[^;}]+", f"--cb:{border}", svg, count=1)

    # 2) background, right after the <desc> tag, using the viewBox size
    box = re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([\d.]+) ([\d.]+)"', svg)
    if not (n1 and n2 and box):
        return None
    x, y, w, h = box.groups()
    stop_xml = "".join(
        f'<stop offset="{i / (len(stops) - 1):.2f}" stop-color="{c}"/>' for i, c in enumerate(stops)
    )
    bg = (
        f'<defs><linearGradient id="violet" x1="0" y1="0" x2="1" y2="1">{stop_xml}</linearGradient></defs>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="url(#violet)"/>'
    )
    svg, n3 = re.subn(r"(</desc>)", r"\1" + bg.replace("\\", "\\\\"), svg, count=1)
    return svg if n3 else None


def main():
    if len(sys.argv) != 3 or sys.argv[2] not in THEMES:
        sys.exit("usage: style_snake.py FILE dark|light")
    path, theme = sys.argv[1], sys.argv[2]
    with open(path, encoding="utf-8") as f:
        svg = f.read()
    result = style(svg, theme)
    if result is None:
        print(f"::warning::Could not style {path} (unknown snake format). Left as it is.")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(result)
    print("styled", path, theme)


if __name__ == "__main__":
    main()
