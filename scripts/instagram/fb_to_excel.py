# -*- coding: utf-8 -*-
"""把 fb_rows_final.json 的 20 条 Meta Business Insights 数据转成 Excel(fb_test.xlsx)"""
import re
import json
import sys
from datetime import datetime, timezone, timedelta

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

BASE = "E:/CCProject/agent_reach/scripts/instagram"
SRC = f"{BASE}/fb_rows_final.json"
OUT = f"{BASE}/fb_test.xlsx"

CST = timezone(timedelta(hours=8))

# 中文指标说明(供后续参考),Excel 表头沿用英文以匹配之前 IG 任务风格
METRIC_LABELS = {
    "views": "Views",
    "reach": "Reach",
    "viewers": "Viewers",
    "interactions": "Interactions",
    "net_reactions": "Likes/Reactions",
    "net_comments": "Comments",
    "shares": "Shares",
    "net_saves": "Saves",
    "link_clicks": "Link clicks",
    "replies": "Replies",
    "new_follows": "New follows",
    "video_play_time": "Video play time (min)",
    "video_average_play_time": "Avg play time (sec)",
    "video_three_second_views": "Video 3s views",
    "instream_ads_estimated_earnings": "Instream ads earnings",
}

METRIC_ORDER = [
    "views", "reach", "viewers", "interactions", "net_reactions",
    "net_comments", "shares", "net_saves", "link_clicks", "replies",
    "new_follows", "video_play_time", "video_average_play_time",
    "video_three_second_views", "instream_ads_estimated_earnings",
]

HEADERS = ["Report date", "Post ID", "Type", "Owner", "Title", "Publish time"] + \
          [METRIC_LABELS[k] for k in METRIC_ORDER] + ["Thumbnail URL"]

TYPE_NAMES = {
    "IG_STORY": "IG Story",
    "IG_POST": "IG Post",
    "FB_PAGE_POST": "FB Page Post",
}

def fmt_time(ts):
    if not ts:
        return ""
    return datetime.fromtimestamp(ts, CST).strftime("%Y-%m-%d %H:%M:%S")

_ILLEGAL_XML = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')

def clean_str(v):
    if v is None:
        return ""
    s = str(v)
    s = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return _ILLEGAL_XML.sub("", s).strip()

def fmt_metric(v, key):
    if v is None:
        return None
    if key == "video_play_time" and isinstance(v, (int, float)):
        # Meta 单位毫秒 -> 分钟
        return round(v / 60000.0, 1)
    if key == "video_average_play_time" and isinstance(v, (int, float)):
        # 毫秒 -> 秒
        return round(v / 1000.0, 1)
    if key == "instream_ads_estimated_earnings" and isinstance(v, (int, float)):
        # 金额单位分 -> 美元(如为分)
        return round(v / 100.0, 2)
    return v

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else SRC
    out = sys.argv[2] if len(sys.argv) > 2 else OUT
    rows = json.load(open(src, encoding="utf-8"))
    report_date = datetime.now(CST).strftime("%Y-%m-%d")
    report_date = datetime.now(CST).strftime("%Y-%m-%d")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "FB Insights"

    # 样式
    header_fill = PatternFill("solid", fgColor="1D3A5F")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    thin = Side(style="thin", color="D0D0D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center")
    left_wrap = Alignment(horizontal="left", vertical="top", wrap_text=True)
    num_fmt = "#,##0"

    ws.append(HEADERS)
    for c in range(1, len(HEADERS) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center
        cell.border = border

    for i, r in enumerate(rows, start=1):
        try:
            m = r.get("metrics", {})
            title = clean_str((r.get("title") or "").replace("\n", " "))
            row = [
                report_date,
                r.get("row_id"),
                TYPE_NAMES.get(r.get("entity_type"), r.get("entity_type")),
                clean_str(r.get("owner")),
                title,
                fmt_time(r.get("created_at")),
            ]
            for k in METRIC_ORDER:
                row.append(fmt_metric(m.get(k), k))
            row.append(clean_str(r.get("image_uri")))
            ws.append(row)
        except Exception as e:
            print(f"row {i} error: {e}")
            raise

        # 行样式
        last_col = len(HEADERS)
        for c in range(1, last_col + 1):
            cell = ws.cell(row=ws.max_row, column=c)
            cell.border = border
            if c in (5,):
                cell.alignment = left_wrap
            elif c in (6,):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            if 7 <= c <= 7 + len(METRIC_ORDER) - 1 and isinstance(cell.value, (int, float)):
                cell.number_format = num_fmt

    # 列宽
    widths = [12, 18, 13, 15, 60, 19] + [12] * len(METRIC_ORDER) + [40]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{ws.max_row}"

    wb.save(out)
    print(f"saved: {out} rows={len(rows)}")

    # 打印视频时长/收入原始值,确认单位换算合理(只看前 3 条有值的)
    shown = 0
    for r in rows:
        m = r.get("metrics", {})
        if m.get("video_play_time") and shown < 3:
            print(r["entity_type"], r["row_id"], "raw video_play_time:", m["video_play_time"],
                  "-> min:", fmt_metric(m["video_play_time"], "video_play_time"))
            shown += 1
        if m.get("instream_ads_estimated_earnings") and shown < 3:
            print(r["entity_type"], r["row_id"], "raw earnings:", m["instream_ads_estimated_earnings"],
                  "-> USD:", fmt_metric(m["instream_ads_estimated_earnings"], "instream_ads_estimated_earnings"))
            shown += 1
        if shown >= 3:
            break

if __name__ == "__main__":
    main()
