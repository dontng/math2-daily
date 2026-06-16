#!/usr/bin/env python3
"""
数二「通关」任务量计算器 —— 把题库 + 时间 + 截止日 解成每日新题量 N 与分钟预算。

模型与 408-from-44/docs/学习数学模型.md 同构：
    总题次 = 题库 × 曝光次数 k
    引入窗口 W = 距截止 - 间隔尾长 T（保证最后一刷落在截止前）
    每日新题 N = ceil(题库 / W)
    每日分钟 = 新题×t1 + 复习×t2
区别：数二单题精做远重于 408 选择题，故 k 默认 4（非 7），且以「分钟预算」为硬约束。

Usage:
    python3 scripts/quota.py --bank 880
    python3 scripts/quota.py --bank 370 --k 5 --deadline 2026-11-15 --t1 12
    python3 scripts/quota.py --scenarios          # 一次性打印 370/660/880/1200 对比

Defaults 取自 horizon（考试约 2026-12-20）与档位周预算（≈14h/周 ≈120min/天均摊）。
所有数字都是参数，按真实资源覆盖即可。
"""

import argparse
import math
from datetime import date, datetime

# ── 默认参数（可被命令行覆盖） ──────────────────────────────────────────────
EXAM_DATE = date(2026, 12, 20)        # 数学约在考研第二日上午，horizon 称「12月第三周」
GAOSHU_RATIO = 0.78                   # 数二卷面：高数 116 / 线代 34 ≈ 78% / 22%
INTERVALS = [3, 8, 20]                # k=4 的 3 次复习间隔（天），压缩以赶在截止前刷完
T1_MIN = 9.0                          # 精做单题分钟（含订正），强化题集均值
T2_MIN = 3.5                          # 复习单题分钟（看思路 / 卡壳重做）
BUDGET_MIN = 120.0                    # 每日数学分钟均摊（档位浮动后的等效）

# 档位周预算（仅作展示与 sanity check，见 horizon 档位系统）
TIERS = [
    ("高档", "周日上午 + 工作日峰值晚", 2, [3.5, 2.5]),  # 周 6.0h
    ("中档", "工作日晚", 4, [2.0]),                       # 周 8.0h
]


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def weekly_budget_hours():
    total = 0.0
    rows = []
    for name, when, n, durs in TIERS:
        # durs 可为每次时长列表（高档两次不同）或单值
        wk = sum(durs) if len(durs) == n else durs[0] * n
        rows.append((name, when, n, wk))
        total += wk
    return rows, total


def plan(bank, today, deadline, k, intervals, t1, t2, gs_ratio):
    days = (deadline - today).days
    tail = sum(intervals)                       # 引入到最后一刷的时间宽度
    window = max(days - tail, 1)                # 必须在此窗口内引入完所有新题
    n = math.ceil(bank / window)
    n_gs = round(n * gs_ratio)
    n_la = n - n_gs

    intro_done = today.fromordinal(today.toordinal() + math.ceil(bank / n))
    last_touch = intro_done.fromordinal(intro_done.toordinal() + tail)

    total_exposures = bank * k
    # 均摊（铺满整个 days）
    avg_new_per_day = bank / days
    avg_rev_per_day = bank * (k - 1) / days
    avg_min = avg_new_per_day * t1 + avg_rev_per_day * t2
    # 峰值（引入与复习重叠期：当天 N 新 + N×(k-1) 复习）
    peak_events = n + n * (k - 1)
    peak_min = n * t1 + n * (k - 1) * t2
    total_min = bank * t1 + bank * (k - 1) * t2

    return dict(
        days=days, tail=tail, window=window, n=n, n_gs=n_gs, n_la=n_la,
        intro_done=intro_done, last_touch=last_touch,
        total_exposures=total_exposures,
        avg_events=avg_new_per_day + avg_rev_per_day, avg_min=avg_min,
        peak_events=peak_events, peak_min=peak_min,
        total_min=total_min, feasible=last_touch <= deadline,
    )


def fmt(p, bank, k, t1, t2, budget):
    over = p["avg_min"] - budget
    flag = "✅ 容得下" if p["avg_min"] <= budget else f"⚠️ 超预算 {over:+.0f}min/天"
    touch_flag = "✅" if p["feasible"] else "❌ 最后一刷落在考后"
    return f"""\
  题库 {bank} 题 × {k} 次曝光 = {p['total_exposures']} 题次
  距截止 {p['days']} 天 │ 间隔尾长 {p['tail']} 天 │ 引入窗口 {p['window']} 天
  ── 每日新题 N = {p['n']}/天  (高数 {p['n_gs']} + 线代 {p['n_la']})
  引入完成 ≈ {p['intro_done']}   最后一刷 ≈ {p['last_touch']}  {touch_flag}
  日均吞吐 ≈ {p['avg_events']:.0f} 题次/天   日均 ≈ {p['avg_min']:.0f} min/天   {flag}
  峰值（引入×复习重叠）≈ {p['peak_events']} 题次 / {p['peak_min']:.0f} min（压在高档周日）
  精做单题 {t1:.0f}min · 复习单题 {t2:.0f}min · 总投入 ≈ {p['total_min']/60:.0f}h"""


def main():
    ap = argparse.ArgumentParser(description="数二每日通关任务量计算器")
    ap.add_argument("--bank", type=int, default=880, help="题库总题数（默认 880 强化题集）")
    ap.add_argument("--today", type=parse_date, default=date.today(), help="起算日 YYYY-MM-DD")
    ap.add_argument("--deadline", type=parse_date, default=EXAM_DATE,
                    help="该阶段截止日 YYYY-MM-DD（强化阶段填 8/31，真题阶段填考期）")
    ap.add_argument("--k", type=int, default=4, help="每题曝光次数（默认 4：1 精做 + 3 复习）")
    ap.add_argument("--intervals", type=int, nargs="+", default=INTERVALS,
                    help="k-1 个复习间隔（天）")
    ap.add_argument("--t1", type=float, default=T1_MIN, help="精做单题分钟")
    ap.add_argument("--t2", type=float, default=T2_MIN, help="复习单题分钟")
    ap.add_argument("--budget", type=float, default=BUDGET_MIN, help="每日数学分钟均摊")
    ap.add_argument("--gaoshu", type=float, default=GAOSHU_RATIO, help="高数占比")
    ap.add_argument("--scenarios", action="store_true", help="打印 370/660/880/1200 题库对比")
    args = ap.parse_args()

    rows, wk_total = weekly_budget_hours()
    print(f"\n距 {args.deadline}（截止）还有 {(args.deadline - args.today).days} 天"
          f"  ·  起算 {args.today}\n")
    print("档位周预算：")
    for name, when, n, wk in rows:
        print(f"  {name:<4} {when:<22} ×{n}/周  ≈ {wk:.1f}h/周")
    print(f"  ── 合计 ≈ {wk_total:.1f}h/周 ≈ {wk_total*60/7:.0f}min/天均摊\n")

    if args.scenarios:
        for bank in (370, 660, 880, 1200):
            p = plan(bank, args.today, args.deadline, args.k, args.intervals,
                     args.t1, args.t2, args.gaoshu)
            print(f"── 场景：{bank} 题 " + "─" * 40)
            print(fmt(p, bank, args.k, args.t1, args.t2, args.budget))
            print()
    else:
        p = plan(args.bank, args.today, args.deadline, args.k, args.intervals,
                 args.t1, args.t2, args.gaoshu)
        print(fmt(p, args.bank, args.k, args.t1, args.t2, args.budget))
        print()


if __name__ == "__main__":
    main()
