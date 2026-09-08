# -*- coding: utf-8 -*-
"""
Fetch all posts from https://x.com/AnycubicAli and export metrics to Excel.

Data source: OpenCLI twitter adapter (reuses the logged-in Chrome session).

Columns:
  Public (auto-fetched):  Post id, Date, Post text, Post Link, Impressions(views),
                          Likes, Replies, Reposts(retweets)
  Owner-only (X Analytics private metrics, marked N/A unless logged in as
  the account owner):     Engagements, Bookmarks, New follows, Profile visits,
                          Detail Expands, URL Clicks, Hashtag Clicks,
                          Permalink Clicks

Usage:
  python fetch_anycubicali_posts.py [--username AnycubicAli] [--limit 10000]
                                    [--output test.xlsx] [--page-delay 2]
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

OPENCLI = r"C:\Users\zhengjingyi\.workbuddy\binaries\node\versions\22.22.2\opencli.cmd"

COLUMNS = [
    "Post id",
    "Date",
    "Post text",
    "Post Link",
    "Impressions",
    "Likes",
    "Engagements",
    "Bookmarks",
    "Shares",
    "New follows",
    "Replies",
    "Reposts",
    "Profile visits",
    "Detail Expands",
    "URL Clicks",
    "Hashtag Clicks",
    "Permalink Clicks",
]

# Metrics only visible in the account owner's X Analytics dashboard.
OWNER_ONLY = {
    "Engagements",
    "Bookmarks",
    "New follows",
    "Profile visits",
    "Detail Expands",
    "URL Clicks",
    "Hashtag Clicks",
    "Permalink Clicks",
}


def parse_date(raw: str) -> str:
    """Twitter style 'Wed Nov 11 06:05:56 +0000 2020' -> '2020-11-11 06:05:56'."""
    if not raw:
        return ""
    try:
        return datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y").strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except ValueError:
        return raw


def fetch_tweets(username: str, limit: int, page_delay: int) -> list:
    """Fetch all timeline posts via opencli twitter tweets."""
    cmd = [
        OPENCLI,
        "twitter",
        "tweets",
        username,
        "--limit",
        str(limit),
        "--page-delay",
        str(page_delay),
        "-f",
        "json",
    ]
    print(f"[fetch] {' '.join(cmd)}", flush=True)
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        print(result.stdout[-2000:], file=sys.stderr)
        print(result.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"opencli failed with exit code {result.returncode}")
    # The JSON payload is on stdout; tolerate update-notice noise around it.
    text = result.stdout.strip()
    start = text.find("[")
    if start == -1:
        raise SystemExit("No JSON array found in opencli output")
    text = text[start:]
    end = text.rfind("]")
    if end != -1:
        text = text[: end + 1]
    return json.loads(text)


def write_excel(rows: list, out_path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Posts"

    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(color="FFFFFF", bold=True)
    for col, name in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col, value=name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    for r, row in enumerate(rows, start=2):
        for c, name in enumerate(COLUMNS, start=1):
            value = row.get(name, "")
            cell = ws.cell(row=r, column=c, value=value)
            if name == "Post text":
                cell.alignment = Alignment(wrap_text=True, vertical="top")

    widths = {
        "Post id": 22,
        "Date": 20,
        "Post text": 60,
        "Post Link": 55,
        "Impressions": 13,
        "Likes": 9,
        "Engagements": 13,
        "Bookmarks": 12,
        "Shares": 9,
        "New follows": 12,
        "Replies": 9,
        "Reposts": 9,
        "Profile visits": 14,
        "Detail Expands": 14,
        "URL Clicks": 12,
        "Hashtag Clicks": 14,
        "Permalink Clicks": 14,
    }
    for c, name in enumerate(COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(c)].width = widths.get(name, 12)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{len(rows) + 1}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="AnycubicAli")
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--page-delay", type=int, default=2)
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent / "test.xlsx"),
    )
    args = parser.parse_args()

    tweets = fetch_tweets(args.username, args.limit, args.page_delay)
    print(f"[fetch] got {len(tweets)} posts", flush=True)

    rows = []
    for t in tweets:
        row = {
            "Post id": t.get("id", ""),
            "Date": parse_date(t.get("created_at", "")),
            "Post text": (t.get("text") or "").replace("\r", ""),
            "Post Link": t.get("url", ""),
            "Impressions": t.get("views", ""),
            "Likes": t.get("likes", ""),
            "Shares": t.get("retweets", ""),
            "Replies": t.get("replies", ""),
            "Reposts": t.get("retweets", ""),
        }
        for name in OWNER_ONLY:
            row[name] = "N/A"
        rows.append(row)

    out_path = Path(args.output)
    write_excel(rows, out_path)
    print(f"[done] wrote {len(rows)} rows -> {out_path}", flush=True)


if __name__ == "__main__":
    main()
