#!/usr/bin/env python3 test
"""
Make three profile cards as SVG files. No other website is needed.

  streak.svg     -> total contributions, current streak, longest streak
  stats.svg      -> repos, stars, followers, pull requests, issues
  languages.svg  -> top languages from your public repos

It reads your data from the GitHub GraphQL API, so it never breaks
because a free community server is down or out of rate limit.

Run on GitHub Actions (see .github/workflows/profile.yml) or on your PC:

    py scripts\\generate_cards.py --demo          (fake data, no token)
    set GH_TOKEN=your_token && py scripts\\generate_cards.py --user YourName
"""

import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from html import escape


def utcnow():
    """Current UTC time (no timezone object, simple to compare)."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0)


API = "https://api.github.com/graphql"

# ---------- colors (same green as your typing text: 00FF9D) ----------
BG = "#0d1117"
BORDER = "#30363d"
TEXT = "#c9d1d9"
MUTED = "#8b949e"
ACCENT = "#00ff9d"
ACCENT2 = "#00c8ff"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"


# =====================================================================
# 1. GET DATA
# =====================================================================
def gql(query, token):
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-cards-script",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    if data.get("errors"):
        raise RuntimeError(f"GitHub API error: {data['errors']}")
    return data["data"]


def parse_time(text):
    return dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")


def fetch_profile(login, token):
    """Return a dict with days, repos, followers, prs, issues."""
    now = utcnow()
    created = parse_time(
        gql('query{user(login:"%s"){createdAt}}' % login, token)["user"]["createdAt"]
    )

    # The calendar can only be asked for 1 year at a time -> one alias per year.
    years = []
    for year in range(created.year, now.year + 1):
        start = dt.datetime(year, 1, 1)
        end = min(dt.datetime(year, 12, 31, 23, 59, 59), now)
        years.append(
            'y%d: contributionsCollection(from:"%sZ", to:"%sZ")'
            "{contributionCalendar{weeks{contributionDays{date contributionCount}}}}"
            % (year, start.isoformat(), end.isoformat())
        )

    query = """query{user(login:"%s"){
        followers{totalCount}
        pullRequests{totalCount}
        issues{totalCount}
        repositories(first:100, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC,
                     orderBy:{field:STARGAZERS, direction:DESC}){
          totalCount
          nodes{stargazerCount
                languages(first:8, orderBy:{field:SIZE, direction:DESC}){
                  edges{size node{name color}}}}
        }
        %s
    }}""" % (login, "\n".join(years))
    user = gql(query, token)["user"]

    days = {}
    for key, value in user.items():
        if key.startswith("y") and key[1:].isdigit():
            for week in value["contributionCalendar"]["weeks"]:
                for day in week["contributionDays"]:
                    days[dt.date.fromisoformat(day["date"])] = day["contributionCount"]

    repos = user["repositories"]["nodes"]
    languages = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            size, color = languages.get(name, (0, edge["node"]["color"]))
            languages[name] = (size + edge["size"], color)

    return {
        "created": created.date(),
        "days": days,
        "repo_count": user["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "followers": user["followers"]["totalCount"],
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "languages": languages,
    }


# =====================================================================
# 2. STREAK MATH  (the part that was wrong in the old card)
# =====================================================================
def compute_streaks(days, today):
    """
    days  : {date: contribution_count}
    today : the last day to look at (UTC)

    Rules:
      * a day counts if it has 1 or more contributions
      * the CURRENT streak may end today OR yesterday
        (today is not finished yet, so 0 today does not break it)
    Returns (total, (current, start, end), (longest, start, end))
    """
    days = {d: c for d, c in days.items() if d <= today}
    total = sum(days.values())

    longest = (0, None, None)
    run_start = prev = None
    run = 0
    for day in sorted(d for d, c in days.items() if c > 0):
        if prev is not None and (day - prev).days == 1:
            run += 1
        else:
            run, run_start = 1, day
        prev = day
        if run > longest[0]:
            longest = (run, run_start, day)

    # walk backwards from today
    cursor = today
    if days.get(cursor, 0) == 0:
        cursor -= dt.timedelta(days=1)  # grace: today is not over yet
    current_end = cursor
    length = 0
    while days.get(cursor, 0) > 0:
        length += 1
        cursor -= dt.timedelta(days=1)
    current = (length, cursor + dt.timedelta(days=1), current_end) if length else (0, None, None)

    return total, current, longest


# =====================================================================
# 3. DRAW SVG
# =====================================================================
def fmt_date(d, today):
    text = f"{d:%b} {d.day}"
    return text if d.year == today.year else f"{text}, {d.year}"


def fmt_range(start, end, today):
    if start is None:
        return "No streak yet"
    if start == end:
        return fmt_date(start, today)
    return f"{fmt_date(start, today)} - {fmt_date(end, today)}"


def svg_open(width, height, title):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
<title>{escape(title)}</title>
<defs>
  <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{ACCENT}"/><stop offset="1" stop-color="{ACCENT2}"/>
  </linearGradient>
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="3" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
</defs>
<style>
  text {{ font-family: {FONT}; }}
  .big   {{ font-size: 38px; font-weight: 700; fill: {TEXT}; }}
  .label {{ font-size: 15px; font-weight: 600; fill: {ACCENT}; }}
  .sub   {{ font-size: 12px; fill: {MUTED}; }}
  .title {{ font-size: 17px; font-weight: 700; fill: {ACCENT}; }}
  .row   {{ font-size: 14px; fill: {TEXT}; }}
  .val   {{ font-size: 14px; font-weight: 700; fill: {TEXT}; }}
  .fade  {{ opacity: 0; animation: fade .6s ease forwards; }}
  @keyframes fade {{ to {{ opacity: 1; }} }}
  @keyframes ring {{ from {{ stroke-dashoffset: var(--len); }} }}
  .ring {{ animation: ring 1.2s ease-out; }}
  @media (prefers-reduced-motion: reduce) {{
    .fade {{ animation: none; opacity: 1; }} .ring {{ animation: none; }}
  }}
</style>
<rect x="0.5" y="0.5" rx="12" width="{width - 1}" height="{height - 1}" fill="{BG}" stroke="{BORDER}"/>
"""


def flame(x, y, scale=1.0):
    return (
        f'<g transform="translate({x} {y}) scale({scale})" fill="url(#g)">'
        '<path d="M0,-13 C7,-6 10,-2 10,3 C10,9 5,13 0,13 C-5,13 -10,9 -10,3 '
        'C-10,-1 -7,-4 -5,-8 C-4,-5 -3,-4 -1,-4 C1,-7 0,-10 0,-13 Z"/></g>'
    )


def streak_card(data, today, updated):
    total, current, longest = compute_streaks(data["days"], today)
    w, h = 800, 190
    cur_len, cur_s, cur_e = current
    lon_len, lon_s, lon_e = longest

    r = 42
    circ = 2 * 3.14159265 * r
    progress = min(1.0, cur_len / lon_len) if lon_len else 0
    dash = circ * progress

    start = data["created"]
    out = svg_open(w, h, "GitHub streak")
    # dividers
    out += f'<line x1="267" y1="35" x2="267" y2="150" stroke="{BORDER}"/>\n'
    out += f'<line x1="533" y1="35" x2="533" y2="150" stroke="{BORDER}"/>\n'

    # column 1: total
    out += f"""<g class="fade" style="animation-delay:.1s" text-anchor="middle">
  <text x="133" y="92" class="big">{total:,}</text>
  <text x="133" y="124" class="label">Total Contributions</text>
  <text x="133" y="146" class="sub">{escape(fmt_date(start, today))} - Present</text>
</g>\n"""

    # column 2: ring with current streak
    out += f"""<g text-anchor="middle">
  <circle cx="400" cy="82" r="{r}" fill="none" stroke="{BORDER}" stroke-width="6"/>
  <circle class="ring" style="--len:{dash:.1f}" cx="400" cy="82" r="{r}" fill="none" stroke="url(#g)"
          stroke-width="6" stroke-linecap="round" stroke-dasharray="{dash:.1f} {circ:.1f}"
          transform="rotate(-90 400 82)" filter="url(#glow)"/>
  <text x="400" y="94" class="big" style="font-size:34px">{cur_len}</text>
  <circle cx="400" cy="38" r="15" fill="{BG}"/>
  {flame(400, 38, 0.8)}
  <text x="400" y="148" class="label" style="font-size:16px">Current Streak</text>
  <text x="400" y="168" class="sub">{escape(fmt_range(cur_s, cur_e, today))}</text>
</g>\n"""

    # column 3: longest
    out += f"""<g class="fade" style="animation-delay:.3s" text-anchor="middle">
  <text x="667" y="92" class="big">{lon_len}</text>
  <text x="667" y="124" class="label">Longest Streak</text>
  <text x="667" y="146" class="sub">{escape(fmt_range(lon_s, lon_e, today))}</text>
</g>\n"""

    out += (
        f'<text x="{w - 14}" y="{h - 10}" text-anchor="end" class="sub" '
        f'style="font-size:10px">updated {updated}</text>\n</svg>\n'
    )
    return out


def stats_card(data, updated):
    w, h = 390, 190
    rows = [
        ("Public repositories", data["repo_count"], ACCENT),
        ("Stars earned", data["stars"], "#ffd33d"),
        ("Followers", data["followers"], ACCENT2),
        ("Pull requests", data["prs"], "#c792ea"),
        ("Issues", data["issues"], "#ff7b72"),
    ]
    out = svg_open(w, h, "GitHub stats")
    out += '<text x="24" y="34" class="title">GitHub Stats</text>\n'
    for i, (name, value, color) in enumerate(rows):
        y = 66 + i * 25
        out += (
            f'<g class="fade" style="animation-delay:{0.1 + i * 0.1:.1f}s">'
            f'<circle cx="30" cy="{y - 5}" r="5" fill="{color}"/>'
            f'<text x="46" y="{y}" class="row">{escape(name)}</text>'
            f'<text x="{w - 24}" y="{y}" text-anchor="end" class="val">{value:,}</text></g>\n'
        )
    out += f'<text x="{w - 14}" y="{h - 8}" text-anchor="end" class="sub" style="font-size:10px">updated {updated}</text>\n</svg>\n'
    return out


def languages_card(data, updated, limit=6):
    w, h = 390, 190
    items = sorted(data["languages"].items(), key=lambda kv: kv[1][0], reverse=True)
    total = sum(size for _, (size, _) in items) or 1
    top = items[:limit]
    other = sum(size for _, (size, _) in items[limit:])
    if other:
        top.append(("Other", (other, MUTED)))

    out = svg_open(w, h, "Top languages")
    out += '<text x="24" y="34" class="title">Top Languages</text>\n'
    if not items:
        out += f'<text x="24" y="90" class="row">No public code yet - push a project!</text>\n</svg>\n'
        return out

    bar_x, bar_w = 24, w - 48
    out += f'<clipPath id="bar"><rect x="{bar_x}" y="48" width="{bar_w}" height="10" rx="5"/></clipPath>\n<g clip-path="url(#bar)">\n'
    x = bar_x
    for name, (size, color) in top:
        seg = bar_w * size / total
        out += f'  <rect x="{x:.1f}" y="48" width="{max(seg, 2):.1f}" height="10" fill="{color or MUTED}"/>\n'
        x += seg
    out += "</g>\n"

    for i, (name, (size, color)) in enumerate(top[:8]):
        col, row = i % 2, i // 2
        px, py = 24 + col * 180, 90 + row * 24
        pct = 100 * size / total
        out += (
            f'<g class="fade" style="animation-delay:{0.1 + i * 0.08:.2f}s">'
            f'<circle cx="{px + 5}" cy="{py - 5}" r="5" fill="{color or MUTED}"/>'
            f'<text x="{px + 18}" y="{py}" class="row">{escape(name)} '
            f'<tspan fill="{MUTED}">{pct:.1f}%</tspan></text></g>\n'
        )
    out += f'<text x="{w - 14}" y="{h - 8}" text-anchor="end" class="sub" style="font-size:10px">updated {updated}</text>\n</svg>\n'
    return out


# =====================================================================
# 4. MAIN
# =====================================================================
def demo_data():
    today = utcnow().date()
    days = {}
    # fake history: gaps, a 9 day run, and a current 5 day run
    for back in range(120):
        d = today - dt.timedelta(days=back)
        if back < 5 or 20 <= back < 29 or back % 7 in (3, 4) and back < 100:
            days[d] = (back * 3) % 7 + 1
    return {
        "created": today - dt.timedelta(days=119),
        "days": days,
        "repo_count": 12,
        "stars": 7,
        "followers": 18,
        "prs": 4,
        "issues": 2,
        "languages": {
            "JavaScript": (52000, "#f1e05a"),
            "HTML": (31000, "#e34c26"),
            "CSS": (24000, "#563d7c"),
            "PHP": (9000, "#4F5D95"),
            "Python": (4000, "#3572A5"),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user", default=os.environ.get("GITHUB_REPOSITORY_OWNER"))
    parser.add_argument("--out", default=os.environ.get("OUT_DIR", "dist"))
    parser.add_argument("--demo", action="store_true", help="use fake data (no token needed)")
    args = parser.parse_args()

    if args.demo:
        data = demo_data()
    else:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token or not args.user:
            sys.exit("Need a GH_TOKEN and a --user name (or use --demo).")
        data = fetch_profile(args.user, token)

    now = utcnow()
    today, updated = now.date(), now.strftime("%Y-%m-%d %H:%M UTC")

    os.makedirs(args.out, exist_ok=True)
    files = {
        "streak.svg": streak_card(data, today, updated),
        "stats.svg": stats_card(data, updated),
        "languages.svg": languages_card(data, updated),
    }
    for name, svg in files.items():
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as f:
            f.write(svg)
        print("wrote", os.path.join(args.out, name))

    total, current, longest = compute_streaks(data["days"], today)
    print(f"total={total} current={current[0]} longest={longest[0]}")


if __name__ == "__main__":
    main()
