#!/usr/bin/env python3
"""
数二「时间进度」追踪器 —— 不算题量，只算时间节点与轮速。

与 408 一致的只是「每天的时间量」（≈120min/天，档位 14h/周）；方法完全不同：
数二先把强化打穿（例题+严选题 ≥4 轮 → 十七堂课），再进真题，全程无明确题量，
只有清晰的阶段时间节点 + 轮次推进。本工具回答：

    今天在哪个阶段？该阶段还剩几天？强化期每轮该多少天？我是否落后？

Usage:
    python3 scripts/pace.py                 # 甘特 + 今天定位 + 轮速
    python3 scripts/pace.py --today 2026-07-20
    python3 scripts/pace.py --round 2       # 我已完成 2 轮，查是否跟得上节点

时间节点（horizon 对齐，考试约 2026-12-20）：
    9 月前       强化超量多刷（例题+严选题 ≥4 轮，后接十七堂课）
    9 中–10 下   真题多刷
    整个 11 月    模拟多刷
    12 月（考前两周回归） 真题复刷 + 强化期专项
"""

import argparse
from datetime import date, datetime

# ── 阶段编排（时间驱动；rounds 仅强化例题/严选题有，用于算轮速，非题量） ──────
PHASES = [
    dict(key="强化A", name="强化 · 武忠祥例题 + 严选题（≥4 轮）",
         start=date(2026, 6, 16), end=date(2026, 8, 26), rounds=4, slow_first=True),
    dict(key="强化B", name="强化 · 十七堂课（精做 1 遍）",
         start=date(2026, 8, 27), end=date(2026, 9, 13), rounds=1, slow_first=False),
    dict(key="真题", name="真题 · 多刷（按专题→按年份）",
         start=date(2026, 9, 14), end=date(2026, 10, 25), rounds=None, slow_first=False),
    dict(key="模拟", name="模拟 · 各种模拟卷多刷（整卷计时）",
         start=date(2026, 11, 1), end=date(2026, 11, 30), rounds=None, slow_first=False),
    dict(key="回归", name="回归 · 真题复刷 + 强化期专项练习",
         start=date(2026, 12, 1), end=date(2026, 12, 20), rounds=None, slow_first=False),
]

# 每日时间锚点（与 408 一致；档位见 horizon）
TIERS = [
    ("高档", "周日上午 + 工作日峰值晚", "≈6.0h/周"),
    ("中档", "工作日晚", "≈8.0h/周"),
]
DAILY_MIN = 120  # 14h/周 均摊


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def round_schedule(p):
    """返回各轮天数：精做首轮慢(~40%)，其余均分。"""
    d = (p["end"] - p["start"]).days + 1
    r = p["rounds"]
    if not r:
        return None
    if r == 1:
        return [d]
    if p["slow_first"]:
        first = round(d * 0.40)
        rest = (d - first) / (r - 1)
        return [first] + [round(rest)] * (r - 1)
    each = d / r
    return [round(each)] * r


def locate(today):
    for i, p in enumerate(PHASES):
        if p["start"] <= today <= p["end"]:
            return i, p
        if today < p["start"]:
            return i, None  # 落在间隙/未开始，下一阶段是 p
    return len(PHASES), None


def bar(p, today):
    total = (p["end"] - p["start"]).days + 1
    if today < p["start"]:
        done = 0
    elif today > p["end"]:
        done = total
    else:
        done = (today - p["start"]).days + 1
    filled = round(done / total * 18)
    return "█" * filled + "·" * (18 - filled), done, total


def main():
    ap = argparse.ArgumentParser(description="数二时间进度追踪器")
    ap.add_argument("--today", type=parse_date, default=date.today())
    ap.add_argument("--round", type=int, default=None, help="强化A 已完成轮数，查进度")
    args = ap.parse_args()
    today = args.today
    exam = PHASES[-1]["end"]

    print(f"\n距数学考试 {exam} 还有 {(exam - today).days} 天   ·   今天 {today}")
    print("每日时间锚点（= 408 口径，不数题）：", end="")
    print("  " + " / ".join(f"{n} {w}" for n, w, _ in [(a, c, b) for a, b, c in TIERS]),
          f"  ≈ {DAILY_MIN}min/天均摊\n")

    print("阶段甘特：")
    for p in PHASES:
        b, done, total = bar(p, today)
        here = "  ◀ 现在" if p["start"] <= today <= p["end"] else ""
        rng = f"{p['start']:%m/%d}–{p['end']:%m/%d}"
        print(f"  {b}  {rng}  {total:>2}天  {p['name']}{here}")
        rs = round_schedule(p)
        if rs and p["rounds"] and p["rounds"] > 1:
            shape = " + ".join(f"{x}天" for x in rs)
            print(f"  {' '*18}  轮速：{shape}  （首轮精做慢，后续轮复习+错题提速）")
    print()

    # 今天定位
    idx, cur = locate(today)
    if cur is None:
        if idx < len(PHASES):
            nxt = PHASES[idx]
            print(f"▶ 当前在阶段间隙；下一阶段「{nxt['name']}」于 {nxt['start']} 开始"
                  f"（还有 {(nxt['start']-today).days} 天）。")
        else:
            print("▶ 全程已过考试日。")
    else:
        _, done, total = bar(cur, today)
        left = (cur["end"] - today).days
        print(f"▶ 当前阶段：{cur['name']}")
        print(f"   已进行 {done}/{total} 天，剩 {left} 天。")
        if cur["rounds"] and cur["rounds"] > 1:
            rs = round_schedule(cur)
            cum, should_round = 0, 1
            for i, x in enumerate(rs, 1):
                cum += x
                if done <= cum:
                    should_round = i
                    break
            else:
                should_round = len(rs)
            print(f"   按轮速，今天应在 第 {should_round} 轮。")
            if args.round is not None:
                if args.round >= should_round:
                    print(f"   你已完成 {args.round} 轮 → ✅ 跟上/领先节点。")
                else:
                    print(f"   你已完成 {args.round} 轮 → ⚠️ 落后 {should_round-args.round} 轮，"
                          f"后续轮只做错题/卡壳题提速。")
    print()


if __name__ == "__main__":
    main()
