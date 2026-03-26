#!/usr/bin/env python3
"""
╭─────────────────────────────────╮
│   ~ Salat Tracker ~             │
│   Qada Prayer Calculator        │
│   Colorful & Friendly Edition   │
╰─────────────────────────────────╯

A CLI tool to calculate and track missed obligatory prayers (qada)
since reaching the age of obligation in Islam.

Tracks: Fajr, Dhuhr, Asr, Maghrib, Isha + Jumu'ah (Friday)
"""

import json
import os
import sys
import calendar
from datetime import datetime, date, timedelta
from pathlib import Path

# ── Colors ──────────────────────────────────────────────────────────

class C:
    """ANSI color codes for the friendly palette."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    ITALIC  = "\033[3m"
    UNDER   = "\033[4m"

    # Catppuccin-inspired palette
    MAUVE   = "\033[38;5;183m"   # headings, accents
    PINK    = "\033[38;5;211m"   # numbers, counts
    GREEN   = "\033[38;5;150m"   # success, done
    BLUE    = "\033[38;5;111m"   # info, labels
    YELLOW  = "\033[38;5;222m"   # warnings, highlights
    RED     = "\033[38;5;203m"   # pending, owed
    PEACH   = "\033[38;5;216m"   # warm accents
    TEAL    = "\033[38;5;116m"   # secondary info
    LAVEN   = "\033[38;5;147m"   # soft purple
    SKY     = "\033[38;5;117m"   # light blue
    GRAY    = "\033[38;5;245m"   # muted text
    WHITE   = "\033[38;5;255m"   # bright text
    BG_SEL  = "\033[48;5;236m"   # selected bg
    BG_HEAD = "\033[48;5;235m"   # header bg
    RESP    = "\033[38;5;158m"   # response/feedback messages (mint green)


PRAYERS = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]
DATA_FILE = Path(__file__).parent / "salat_data.json"


def feedback(msg):
    """Display a response message in the unique feedback color."""
    print(f"\n  {C.RESP}{msg}{C.RESET}\n")
    input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")

# ── Data Persistence ────────────────────────────────────────────────

def load_data():
    """Load saved tracker data from disk."""
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError):
            return None
    return None


def save_data(data):
    """Save tracker data to disk."""
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def obligation_start_date(dob: date, puberty_age: int) -> date:
    """Calculate obligation start, handling Feb 29 DOB on non-leap target years."""
    target_year = dob.year + puberty_age
    if dob.month == 2 and dob.day == 29 and not calendar.isleap(target_year):
        return date(target_year, 3, 1)
    return date(target_year, dob.month, dob.day)


def init_data(dob: date, puberty_age: int, name: str = ""):
    """Create a fresh data structure."""
    start = obligation_start_date(dob, puberty_age)
    return {
        "name": name,
        "dob": dob.isoformat(),
        "puberty_age": puberty_age,
        "start_date": start.isoformat(),
        "completed": {}  # "YYYY-MM-DD": ["Fajr", "Dhuhr", ...] or ["Jumuah"]
    }

# ── Calculation Helpers ─────────────────────────────────────────────

def get_start_date(data):
    return date.fromisoformat(data["start_date"])


def days_since_start(data):
    start = get_start_date(data)
    today = date.today()
    if today < start:
        return 0
    return (today - start).days + 1  # inclusive of start


def fridays_since_start(data):
    start = get_start_date(data)
    today = date.today()
    if today < start:
        return 0
    count = 0
    d = start
    # Jump to first Friday
    while d.weekday() != 4 and d <= today:
        d += timedelta(days=1)
    while d <= today:
        count += 1
        d += timedelta(days=7)
    return count


def completed_count(data, prayer_name):
    """Count how many times a specific prayer has been marked completed."""
    count = 0
    for day_prayers in data["completed"].values():
        count += day_prayers.count(prayer_name)
    return count


def get_stats(data):
    """Calculate all prayer stats."""
    total_days = days_since_start(data)
    total_fridays = fridays_since_start(data)

    stats = {}
    for p in PRAYERS:
        owed = total_days
        done = completed_count(data, p)
        stats[p] = {"owed": owed, "done": done, "remaining": max(0, owed - done)}

    jdone = completed_count(data, "Jumuah")
    stats["Jumu'ah"] = {"owed": total_fridays, "done": jdone, "remaining": max(0, total_fridays - jdone)}

    return stats, total_days, total_fridays


def get_jumuah_streak(data):
    """Calculate current consecutive missed Jumu'ah count and longest streak.
    Counts backwards from the most recent Friday."""
    start = get_start_date(data)
    today = date.today()

    # Build list of all Fridays from start to today
    fridays = []
    d = start
    while d.weekday() != 4 and d <= today:
        d += timedelta(days=1)
    while d <= today:
        fridays.append(d)
        d += timedelta(days=7)

    if not fridays:
        return 0, 0

    # Current streak (counting back from most recent Friday)
    current_streak = 0
    for fri in reversed(fridays):
        day_str = fri.isoformat()
        completed = data["completed"].get(day_str, [])
        if "Jumuah" not in completed:
            current_streak += 1
        else:
            break

    # Longest missed streak
    longest = 0
    streak = 0
    for fri in fridays:
        day_str = fri.isoformat()
        completed = data["completed"].get(day_str, [])
        if "Jumuah" not in completed:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0

    return current_streak, longest


def get_daily_streak(data):
    """Count consecutive days ending today (or yesterday) where all 5 daily prayers were done.
    Returns (current_streak, longest_streak)."""
    start = get_start_date(data)
    today = date.today()

    if today < start:
        return 0, 0

    # Walk backwards from today to find current streak
    current_streak = 0
    d = today
    while d >= start:
        day_str = d.isoformat()
        completed = data["completed"].get(day_str, [])
        all_five = all(p in completed for p in PRAYERS)
        if all_five:
            current_streak += 1
            d -= timedelta(days=1)
        else:
            break

    # Walk forward from start to find longest streak
    longest = 0
    streak = 0
    d = start
    while d <= today:
        day_str = d.isoformat()
        completed = data["completed"].get(day_str, [])
        all_five = all(p in completed for p in PRAYERS)
        if all_five:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
        d += timedelta(days=1)

    return current_streak, longest


def get_most_missed(data, period="current_month"):
    """Return (prayer_name, completion_pct) for the most-missed prayer in a period.
    period: 'current_month' or 'last_month'
    Returns a dict: {prayer: pct} for all 5 prayers, and the worst one."""
    today = date.today()
    start = get_start_date(data)

    if period == "current_month":
        p_start = date(today.year, today.month, 1)
        p_end = today
        label = today.strftime("%B")
    else:  # last_month
        first_this = date(today.year, today.month, 1)
        p_end = first_this - timedelta(days=1)
        p_start = date(p_end.year, p_end.month, 1)
        label = p_end.strftime("%B")

    p_start = max(p_start, start)
    if p_end < p_start:
        return label, {}

    # Count eligible days and completion per prayer
    results = {}
    total_days = (p_end - p_start).days + 1
    for p in PRAYERS:
        done = 0
        d = p_start
        while d <= p_end:
            if p in data["completed"].get(d.isoformat(), []):
                done += 1
            d += timedelta(days=1)
        results[p] = done / total_days if total_days > 0 else 0

    return label, results


def get_qada_payoff_estimate(data):
    """Estimate how long until all qada is cleared based on recent pace.
    Looks at prayers marked in last 30 days beyond the daily 5 owed.
    Returns (extra_per_day, years, months, days) or None if no data."""
    today = date.today()
    start = get_start_date(data)
    if today < start:
        return None

    stats, _, _ = get_stats(data)
    total_remaining = sum(s["remaining"] for s in stats.values())
    if total_remaining == 0:
        return None

    # Count prayers marked in last 30 days
    window = 30
    window_start = today - timedelta(days=window - 1)
    prayers_in_window = 0
    for offset in range(window):
        d = window_start + timedelta(days=offset)
        prayers_in_window += len(data["completed"].get(d.isoformat(), []))

    # Each day you "owe" 5 prayers (+ Jumuah on Fridays, ~5.14/day avg)
    # Estimate daily obligation: 5 daily + 1/7 Jumuah ≈ 5.14
    daily_owed = 5 + (1 / 7)
    total_marked = prayers_in_window
    # Extra = above what you owed during window
    extra_total = total_marked - (daily_owed * window)
    extra_per_day = extra_total / window

    if extra_per_day <= 0:
        return None  # Not making progress

    days_to_clear = total_remaining / extra_per_day
    years = int(days_to_clear // 365)
    months = int((days_to_clear % 365) // 30)
    days_rem = int(days_to_clear % 30)

    return round(extra_per_day, 1), years, months, days_rem


def parse_relative_date(date_str):
    """Parse relative date strings: 'today', 'yesterday', '-1', '-3', or YYYY-MM-DD.
    Returns a date object or None on failure."""
    s = date_str.strip().lower()
    today = date.today()
    if s in ("today", "t", "0"):
        return today
    if s in ("yesterday", "y", "-1", "yest"):
        return today - timedelta(days=1)
    # Numeric offset like -2, -7
    if s.startswith("-") and s[1:].isdigit():
        offset = int(s[1:])
        return today - timedelta(days=offset)
    # ISO date
    try:
        return date.fromisoformat(date_str.strip())
    except ValueError:
        return None


def get_today_status(data):
    """Return (done_count, expected, remaining_names) for today."""
    today = date.today()
    start = get_start_date(data)
    if today < start:
        return None
    day_str = today.isoformat()
    completed = data["completed"].get(day_str, [])
    is_friday = today.weekday() == 4
    available = PRAYERS + (["Jumuah"] if is_friday else [])
    expected = len(available)
    done = len(completed)
    remaining = [("Jumu'ah" if p == "Jumuah" else p) for p in available if p not in completed]
    return done, expected, remaining


def get_weekly_monthly_summary(data):
    """Compute weekly and monthly summary stats."""
    today = date.today()
    start = get_start_date(data)

    # This week (Mon–today)
    week_start = today - timedelta(days=today.weekday())
    week_start = max(week_start, start)

    # This month
    month_start = date(today.year, today.month, 1)
    month_start = max(month_start, start)

    def count_range(d_start, d_end):
        done = 0
        owed = 0
        d = d_start
        while d <= d_end:
            is_fri = d.weekday() == 4
            exp = 6 if is_fri else 5
            owed += exp
            done += len(data["completed"].get(d.isoformat(), []))
            d += timedelta(days=1)
        return done, owed

    week_done, week_owed = count_range(week_start, today)
    month_done, month_owed = count_range(month_start, today)

    # Best day this month (most prayers)
    best_day = None
    best_count = -1
    d = month_start
    while d <= today:
        cnt = len(data["completed"].get(d.isoformat(), []))
        if cnt > best_count:
            best_count = cnt
            best_day = d
        d += timedelta(days=1)

    # Daily streak
    streak, longest = get_daily_streak(data)

    return {
        "week_done": week_done, "week_owed": week_owed,
        "month_done": month_done, "month_owed": month_owed,
        "best_day": best_day, "best_day_count": best_count,
        "daily_streak": streak, "longest_streak": longest,
    }


def print_jumuah_warning(data):
    """Show warning if 3+ consecutive Jumu'ah prayers have been missed."""
    current_streak, longest = get_jumuah_streak(data)

    if current_streak >= 3:
        print(f"  {C.RED}{C.BOLD}⚠  JUMU'AH WARNING{C.RESET}")
        print(f"  {C.RED}You have missed {current_streak} consecutive Jumu'ah prayers.{C.RESET}")
        print()
        print(f"  {C.YELLOW}The Prophet (ﷺ) said:{C.RESET}")
        print(f"  {C.YELLOW}{C.ITALIC}\"Whoever neglects three Jumu'ah prayers out of{C.RESET}")
        print(f"  {C.YELLOW}{C.ITALIC}negligence, Allah will place a seal on his heart.\"{C.RESET}")
        print(f"  {C.GRAY}— Sunan Abu Dawud 1052, Sunan al-Tirmidhi 500{C.RESET}")
        print()
    elif current_streak == 2:
        print(f"  {C.YELLOW}⚠  You have missed 2 consecutive Jumu'ah prayers.{C.RESET}")
        print(f"  {C.GRAY}Be careful not to miss a third — see the hadith on this.{C.RESET}")
        print()


def apply_jumuah_dhuhr_logic(completed, prayer, is_friday, adding):
    """When adding Jumu'ah on Friday, auto-add Dhuhr too.
    Dhuhr alone does NOT count as Jumu'ah.
    Returns list of extra messages to display."""
    messages = []
    if adding and is_friday and prayer == "Jumuah":
        # Auto-add Dhuhr when Jumu'ah is selected
        if "Dhuhr" not in completed:
            completed.append("Dhuhr")
            messages.append(("add", "Dhuhr", "auto-added (Jumu'ah counts as Dhuhr)"))
    return messages


def get_month_data(data, year, month):
    """Get completion data for a specific month."""
    start = get_start_date(data)
    cal = calendar.Calendar(firstweekday=0)  # Monday start
    weeks = cal.monthdayscalendar(year, month)

    month_info = []
    for week in weeks:
        week_info = []
        for day in week:
            if day == 0:
                week_info.append(None)
                continue
            d = date(year, month, day)
            day_str = d.isoformat()
            completed_prayers = data["completed"].get(day_str, [])
            is_before_start = d < start
            is_future = d > date.today()
            is_today = d == date.today()
            is_friday = d.weekday() == 4

            total_expected = 5
            if is_friday:
                total_expected = 6  # 5 daily + Jumu'ah

            week_info.append({
                "day": day,
                "date": d,
                "completed": completed_prayers,
                "expected": total_expected,
                "before_start": is_before_start,
                "future": is_future,
                "today": is_today,
                "friday": is_friday,
            })
        month_info.append(week_info)
    return month_info

# ── Display Functions ───────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def banner(data=None):
    """Print the app banner, optionally with a name greeting."""
    print()
    print(f"  {C.MAUVE}{C.BOLD}~ salat tracker ~{C.RESET}")
    if data and data.get("name"):
        print(f"  {C.PEACH}Assalamu Alaikum, {data['name']}!{C.RESET}")
    else:
        print(f"  {C.GRAY}qada prayer calculator{C.RESET}")
    print()


def print_bismillah():
    print(f"\n  {C.YELLOW}{C.BOLD}Bismillah al-Rahman al-Rahim{C.RESET}")
    print(f"  {C.GRAY}In the name of Allah, the Most Gracious, the Most Merciful{C.RESET}\n")


def print_divider(char="─", width=50):
    print(f"  {C.GRAY}{char * width}{C.RESET}")


def print_stats_table(data):
    """Display the prayer stats table."""
    stats, total_days, total_fridays = get_stats(data)
    start = get_start_date(data)

    print(f"  {C.BLUE}Date of birth    {C.WHITE}{data['dob']}{C.RESET}")
    print(f"  {C.BLUE}Obligation from  {C.WHITE}{data['start_date']}{C.RESET}")
    print(f"  {C.BLUE}Days elapsed     {C.PINK}{total_days:,}{C.RESET}")
    print(f"  {C.BLUE}Fridays elapsed  {C.PINK}{total_fridays:,}{C.RESET}")
    print()
    print_divider()
    print()

    # Table header
    print(f"  {C.LAVEN}{'Prayer':<12} {'Owed':>8}  {'Done':>8}  {'Left':>8}  {'Progress'}{C.RESET}")
    print(f"  {C.GRAY}{'─'*12} {'─'*8}  {'─'*8}  {'─'*8}  {'─'*14}{C.RESET}")

    total_owed = 0
    total_done = 0
    total_left = 0

    all_prayers = PRAYERS + ["Jumu'ah"]
    for p in all_prayers:
        s = stats[p]
        total_owed += s["owed"]
        total_done += s["done"]
        total_left += s["remaining"]

        # Progress bar
        if s["owed"] > 0:
            pct = s["done"] / s["owed"]
        else:
            pct = 0
        bar_width = 10
        filled = int(pct * bar_width)
        bar = f"{C.GREEN}{'█' * filled}{C.GRAY}{'░' * (bar_width - filled)}{C.RESET}"
        pct_str = f"{pct*100:.1f}%"

        # Color the remaining count
        if s["remaining"] == 0:
            left_color = C.GREEN
            left_str = "✓ done"
        else:
            left_color = C.RED
            left_str = f"{s['remaining']:,}"

        owed_str = f"{s['owed']:,}"
        done_str = f"{s['done']:,}"

        print(f"  {C.PEACH}{p:<12}{C.RESET} {C.PINK}{owed_str:>8}{C.RESET}  {C.GREEN}{done_str:>8}{C.RESET}  {left_color}{left_str:>8}{C.RESET}  {bar} {C.GRAY}{pct_str}{C.RESET}")

    print(f"  {C.GRAY}{'─'*12} {'─'*8}  {'─'*8}  {'─'*8}  {'─'*14}{C.RESET}")

    if total_owed > 0:
        total_pct = total_done / total_owed
    else:
        total_pct = 0
    filled = int(total_pct * 10)
    bar = f"{C.GREEN}{'█' * filled}{C.GRAY}{'░' * (10 - filled)}{C.RESET}"

    print(f"  {C.YELLOW}{C.BOLD}{'Total':<12}{C.RESET} {C.PINK}{C.BOLD}{total_owed:,}{C.RESET}  {C.GREEN}{C.BOLD}{total_done:>8,}{C.RESET}  {C.RED}{C.BOLD}{total_left:>8,}{C.RESET}  {bar} {C.GRAY}{total_pct*100:.1f}%{C.RESET}")
    print()

    # Jumu'ah consecutive streak info
    current_streak, longest_streak = get_jumuah_streak(data)
    streak_color = C.GREEN if current_streak == 0 else (C.YELLOW if current_streak < 3 else C.RED)
    print(f"  {C.BLUE}Jumu'ah streak   {streak_color}{current_streak} consecutive missed{C.RESET}")
    if longest_streak > 0:
        print(f"  {C.BLUE}Longest missed   {C.GRAY}{longest_streak} consecutive{C.RESET}")

    # Daily prayer streak (2.2)
    daily_streak, daily_longest = get_daily_streak(data)
    dstreak_color = C.GREEN if daily_streak >= 3 else (C.YELLOW if daily_streak >= 1 else C.GRAY)
    streak_label = f"{daily_streak} day{'s' if daily_streak != 1 else ''}"
    if daily_streak > 0 and daily_streak == daily_longest and daily_longest >= 3:
        streak_label += " 🔥"
    print(f"  {C.BLUE}Daily streak     {dstreak_color}{streak_label} all 5 prayed{C.RESET}")
    if daily_longest > 0:
        print(f"  {C.BLUE}Best streak      {C.GRAY}{daily_longest} day{'s' if daily_longest != 1 else ''}{C.RESET}")
    print()

    # Qada payoff estimate (2.4)
    payoff = get_qada_payoff_estimate(data)
    if payoff:
        extra_pd, yrs, mos, dys = payoff
        parts = []
        if yrs:  parts.append(f"{yrs}yr")
        if mos:  parts.append(f"{mos}mo")
        if dys or not parts: parts.append(f"{dys}d")
        eta_str = " ".join(parts)
        print(f"  {C.BLUE}Qada payoff ETA  {C.TEAL}~{eta_str}  {C.GRAY}(+{extra_pd}/day pace, last 30d){C.RESET}")
        print()

    # Show warning if needed
    print_jumuah_warning(data)


def print_calendar(data, year, month):
    """Display a calendar view for a given month."""
    month_name = calendar.month_name[month]
    print(f"  {C.MAUVE}{C.BOLD}{month_name} {year}{C.RESET}")
    print()
    print(f"  {C.BLUE} Mo   Tu   We   Th   Fr   Sa   Su{C.RESET}")

    month_data = get_month_data(data, year, month)

    for week in month_data:
        row = "  "
        for day_info in week:
            if day_info is None:
                row += "     "
                continue

            day = day_info["day"]
            day_str = f"{day:>2}"

            if day_info["before_start"] or day_info["future"]:
                row += f" {C.GRAY}{day_str}{C.RESET}  "
            elif day_info["today"]:
                row += f" {C.BG_SEL}{C.YELLOW}{C.BOLD}{day_str}{C.RESET}  "
            elif len(day_info["completed"]) >= day_info["expected"]:
                # All prayers done this day
                row += f" {C.GREEN}{C.BOLD}{day_str}{C.RESET}  "
            elif len(day_info["completed"]) > 0:
                # Some prayers done
                row += f" {C.PEACH}{day_str}{C.RESET}  "
            elif day_info["friday"]:
                row += f" {C.LAVEN}{day_str}{C.RESET}  "
            else:
                row += f" {C.WHITE}{day_str}{C.RESET}  "

        print(row)

    print()
    print(f"  {C.YELLOW}{C.BOLD}██{C.RESET} {C.GRAY}today  {C.GREEN}{C.BOLD}██{C.RESET} {C.GRAY}all done  {C.PEACH}██{C.RESET} {C.GRAY}partial  {C.LAVEN}██{C.RESET} {C.GRAY}friday{C.RESET}")
    print()


def print_day_detail(data, d):
    """Show detailed prayer status for a specific day."""
    start = get_start_date(data)
    day_str = d.isoformat()
    completed = data["completed"].get(day_str, [])
    is_friday = d.weekday() == 4

    day_name = calendar.day_name[d.weekday()]
    print(f"\n  {C.MAUVE}{C.BOLD}{day_name}, {d.strftime('%d %B %Y')}{C.RESET}")

    if d < start:
        print(f"\n  {C.RESP}This date is before your obligation start. No prayers tracked.{C.RESET}\n")
        return
    if d > date.today():
        print(f"\n  {C.RESP}This is a future date. No prayers to show yet.{C.RESET}\n")
        return

    print()
    for p in PRAYERS:
        if p in completed:
            print(f"  {C.GREEN}  ✓  {p}{C.RESET}")
        else:
            print(f"  {C.RED}  ○  {p}{C.RESET}")

    if is_friday:
        if "Jumuah" in completed:
            print(f"  {C.GREEN}  ✓  Jumu'ah{C.RESET}")
        else:
            print(f"  {C.RED}  ○  Jumu'ah{C.RESET}")

    done = len(completed)
    expected = 6 if is_friday else 5
    print(f"\n  {C.GRAY}{done}/{expected} prayers completed{C.RESET}\n")


def quick_mark(data, date_str, selection):
    """One-liner mark: mark 2026-03-21 a  or  mark 2026-03-21 1,2,3,5"""
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        print(f"\n  {C.RESP}Invalid date: {date_str}. Use format YYYY-MM-DD.{C.RESET}\n")
        return

    start = get_start_date(data)
    if d < start:
        print(f"\n  {C.RESP}That date is before your obligation start ({data['start_date']}). No changes made.{C.RESET}\n")
        return
    if d > date.today():
        print(f"\n  {C.RESP}Can't mark future dates. Try today or earlier.{C.RESET}\n")
        return

    day_str = d.isoformat()
    if day_str not in data["completed"]:
        data["completed"][day_str] = []

    is_friday = d.weekday() == 4
    available = PRAYERS.copy()
    if is_friday:
        available.append("Jumuah")

    completed = data["completed"][day_str]
    day_name = calendar.day_name[d.weekday()]
    selection = selection.strip().lower()

    if selection == "a":
        data["completed"][day_str] = available.copy()
        print(f"\n  {C.PEACH}{C.BOLD}{day_name}, {d.strftime('%d %B %Y')}{C.RESET}\n")
        for p in available:
            display_name = "Jumu'ah" if p == "Jumuah" else p
            print(f"  {C.GREEN}  ✓ {display_name}{C.RESET}")
        print(f"\n  {C.RESP}All {len(available)} prayers marked for {d.strftime('%d %B %Y')}. Saved.{C.RESET}")
    elif selection == "c":
        data["completed"][day_str] = []
        print(f"\n  {C.PEACH}{C.BOLD}{day_name}, {d.strftime('%d %B %Y')}{C.RESET}")
        print(f"\n  {C.RESP}All prayers cleared for {d.strftime('%d %B %Y')}. Saved.{C.RESET}")
    else:
        try:
            indices = [int(x.strip()) for x in selection.split(",")]
            print(f"\n  {C.PEACH}{C.BOLD}{day_name}, {d.strftime('%d %B %Y')}{C.RESET}\n")
            toggled = 0
            for idx in indices:
                if 1 <= idx <= len(available):
                    prayer = available[idx - 1]
                    display_name = "Jumu'ah" if prayer == "Jumuah" else prayer
                    if prayer in completed:
                        completed.remove(prayer)
                        print(f"  {C.YELLOW}  ○ Removed {display_name}{C.RESET}")
                    else:
                        completed.append(prayer)
                        print(f"  {C.GREEN}  ✓ Added {display_name}{C.RESET}")
                        # Jumu'ah auto-adds Dhuhr
                        extras = apply_jumuah_dhuhr_logic(completed, prayer, is_friday, True)
                        for _, name, note in extras:
                            print(f"  {C.TEAL}  ✓ {name} ({note}){C.RESET}")
                    toggled += 1
                else:
                    print(f"  {C.RED}  ? Invalid number: {idx}{C.RESET}")
            data["completed"][day_str] = completed
            # Show final state
            print()
            for i, p in enumerate(available, 1):
                display_name = "Jumu'ah" if p == "Jumuah" else p
                if p in data["completed"].get(day_str, []):
                    print(f"  {C.GREEN}  [{i}] ✓ {display_name}{C.RESET}")
                else:
                    print(f"  {C.RED}  [{i}] ○ {display_name}{C.RESET}")
            done = len(data["completed"].get(day_str, []))
            print(f"\n  {C.RESP}Toggled {toggled} prayer(s). Now {done}/{len(available)} completed for this day. Saved.{C.RESET}")
        except ValueError:
            print(f"\n  {C.RESP}Invalid selection. Use numbers like 1,2,3 or 'a' for all.{C.RESET}")
            return

    # Clean up empty days
    if not data["completed"].get(day_str):
        data["completed"].pop(day_str, None)

    save_data(data)


def mark_prayers_menu(data, prefill_date=None):
    """Interactive menu to mark prayers as completed."""
    print(f"\n  {C.MAUVE}{C.BOLD}Mark prayers as completed{C.RESET}")

    if prefill_date:
        date_input = prefill_date
    else:
        print(f"  {C.GRAY}Enter a date or press Enter for today{C.RESET}\n")
        date_input = input(f"  {C.SKY}Date (YYYY-MM-DD){C.RESET} [{C.GRAY}{date.today()}{C.RESET}]: ").strip()

    if date_input == "":
        d = date.today()
    else:
        try:
            d = date.fromisoformat(date_input)
        except ValueError:
            print(f"\n  {C.RESP}Invalid date format. Use YYYY-MM-DD.{C.RESET}\n")
            return

    start = get_start_date(data)
    if d < start:
        print(f"\n  {C.RESP}That date is before your obligation start ({data['start_date']}). No changes made.{C.RESET}\n")
        return
    if d > date.today():
        print(f"\n  {C.RESP}Can't mark future dates. Try today or earlier.{C.RESET}\n")
        return

    day_str = d.isoformat()
    if day_str not in data["completed"]:
        data["completed"][day_str] = []

    completed = data["completed"][day_str]
    is_friday = d.weekday() == 4

    available = PRAYERS.copy()
    if is_friday:
        available.append("Jumuah")

    day_name = calendar.day_name[d.weekday()]

    # Loop so user can keep toggling until satisfied
    while True:
        completed = data["completed"].get(day_str, [])
        done_count = len(completed)
        expected = len(available)

        print(f"\n  {C.PEACH}{C.BOLD}{day_name}, {d.strftime('%d %B %Y')}{C.RESET}")
        print(f"  {C.GRAY}{done_count}/{expected} prayers completed{C.RESET}\n")

        # Show current state with order of completion
        for i, p in enumerate(available, 1):
            display_name = "Jumu'ah" if p == "Jumuah" else p
            if p in completed:
                print(f"  {C.GREEN}  [{i}] ✓ {display_name}{C.RESET}")
            else:
                print(f"  {C.RED}  [{i}] ○ {display_name}{C.RESET}")

        print()
        print(f"  {C.GRAY}Toggle numbers (e.g. 1,3,5) │ 'a' mark all │ 'c' clear all │ Enter to finish{C.RESET}\n")
        choice = input(f"  {C.SKY}Toggle>{C.RESET} ").strip().lower()

        if choice == "":
            # Done editing
            done_final = len(data["completed"].get(day_str, []))
            print(f"\n  {C.RESP}Done editing {d.strftime('%d %B %Y')}. {done_final}/{expected} prayers marked. Saved.{C.RESET}")
            break
        elif choice == "a":
            data["completed"][day_str] = available.copy()
            print(f"\n  {C.RESP}All {expected} prayers marked! Saved.{C.RESET}")
            save_data(data)
            continue
        elif choice == "c":
            data["completed"][day_str] = []
            print(f"\n  {C.RESP}All prayers cleared for this day. Saved.{C.RESET}")
            save_data(data)
            continue
        else:
            try:
                indices = [int(x.strip()) for x in choice.split(",")]
                toggled = 0
                for idx in indices:
                    if 1 <= idx <= len(available):
                        prayer = available[idx - 1]
                        display_name = "Jumu'ah" if prayer == "Jumuah" else prayer
                        if prayer in completed:
                            completed.remove(prayer)
                            print(f"  {C.YELLOW}  ○ Removed {display_name}{C.RESET}")
                        else:
                            completed.append(prayer)
                            print(f"  {C.GREEN}  ✓ Added {display_name}{C.RESET}")
                            # Jumu'ah auto-adds Dhuhr
                            extras = apply_jumuah_dhuhr_logic(completed, prayer, is_friday, True)
                            for _, name, note in extras:
                                print(f"  {C.TEAL}  ✓ {name} ({note}){C.RESET}")
                        toggled += 1
                    else:
                        print(f"  {C.RED}  ? Invalid number: {idx}{C.RESET}")
                data["completed"][day_str] = completed
                done_now = len(completed)
                print(f"\n  {C.RESP}Toggled {toggled} prayer(s). Now {done_now}/{expected} completed. Saved.{C.RESET}")
                save_data(data)
            except ValueError:
                print(f"\n  {C.RESP}Invalid input. Use numbers separated by commas.{C.RESET}")
                continue

    # Clean up empty days
    if not data["completed"].get(day_str):
        data["completed"].pop(day_str, None)
        save_data(data)


def bulk_mark_menu(data):
    """Mark prayers for a date range at once."""
    print(f"\n  {C.MAUVE}{C.BOLD}Bulk mark prayers{C.RESET}")
    print(f"  {C.GRAY}Mark the same prayers across a range of dates{C.RESET}\n")

    start_input = input(f"  {C.SKY}Start date (YYYY-MM-DD):{C.RESET} ").strip()
    end_input = input(f"  {C.SKY}End date   (YYYY-MM-DD):{C.RESET} ").strip()

    try:
        start_d = date.fromisoformat(start_input)
        end_d = date.fromisoformat(end_input)
    except ValueError:
        print(f"\n  {C.RESP}Invalid date format. Use YYYY-MM-DD. No changes made.{C.RESET}\n")
        return

    if start_d > end_d:
        start_d, end_d = end_d, start_d

    obligation_start = get_start_date(data)
    if end_d < obligation_start:
        print(f"\n  {C.RESP}Date range is before your obligation start. No changes made.{C.RESET}\n")
        return

    start_d = max(start_d, obligation_start)
    end_d = min(end_d, date.today())

    print(f"\n  {C.GRAY}Which prayers to mark?{C.RESET}")
    print(f"  {C.GRAY}'a' for all 5 daily + Jumu'ah on Fridays{C.RESET}")
    print(f"  {C.GRAY}Or comma-separated: 1=Fajr 2=Dhuhr 3=Asr 4=Maghrib 5=Isha 6=Jumuah{C.RESET}\n")

    choice = input(f"  {C.SKY}Prayers>{C.RESET} ").strip().lower()

    if choice == "a":
        selected = PRAYERS + ["Jumuah"]
    else:
        try:
            all_options = PRAYERS + ["Jumuah"]
            indices = [int(x.strip()) for x in choice.split(",")]
            selected = [all_options[i-1] for i in indices if 1 <= i <= 6]
        except (ValueError, IndexError):
            print(f"\n  {C.RESP}Invalid input. No changes made.{C.RESET}\n")
            return

    if not selected:
        print(f"\n  {C.RESP}No prayers selected. No changes made.{C.RESET}\n")
        return

    count = 0
    d = start_d
    while d <= end_d:
        day_str = d.isoformat()
        if day_str not in data["completed"]:
            data["completed"][day_str] = []

        for p in selected:
            if p == "Jumuah" and d.weekday() != 4:
                continue
            if p not in data["completed"][day_str]:
                data["completed"][day_str].append(p)
                count += 1

        if not data["completed"][day_str]:
            data["completed"].pop(day_str, None)

        d += timedelta(days=1)

    save_data(data)
    days_count = (end_d - start_d).days + 1
    print(f"\n  {C.RESP}Bulk mark complete! {count:,} prayers marked across {days_count:,} days. Saved.{C.RESET}")


def motivation_message(data):
    """Show an encouraging message based on progress."""
    stats, _, _ = get_stats(data)
    total_done = sum(s["done"] for s in stats.values())
    total_owed = sum(s["owed"] for s in stats.values())

    if total_owed == 0:
        return

    pct = total_done / total_owed * 100

    messages = [
        (0,    f"{C.YELLOW}Every journey begins with a single step. You've got this!{C.RESET}"),
        (1,    f"{C.PEACH}Alhamdulillah! You've started. Keep going!{C.RESET}"),
        (5,    f"{C.PEACH}MashaAllah, {total_done:,} prayers completed! Consistency is key.{C.RESET}"),
        (10,   f"{C.GREEN}SubhanAllah! 10% done. You're building momentum!{C.RESET}"),
        (25,   f"{C.GREEN}Quarter of the way there! Allah sees your effort.{C.RESET}"),
        (50,   f"{C.GREEN}{C.BOLD}Halfway! MashaAllah, what an achievement!{C.RESET}"),
        (75,   f"{C.MAUVE}{C.BOLD}75%! The finish line is in sight, keep pushing!{C.RESET}"),
        (90,   f"{C.MAUVE}{C.BOLD}SubhanAllah! So close! Almost there!{C.RESET}"),
        (99.9, f"{C.YELLOW}{C.BOLD}Just a few more... you can do it!{C.RESET}"),
        (100,  f"{C.GREEN}{C.BOLD}Allahu Akbar! All prayers completed! May Allah accept!{C.RESET}"),
    ]

    msg = messages[0][1]
    for threshold, m in messages:
        if pct >= threshold:
            msg = m

    print(f"  {msg}")
    print()


def print_today_quickview(data):
    """One-liner today status shown on home screen."""
    status = get_today_status(data)
    if status is None:
        return
    done, expected, remaining = status
    today = date.today()
    day_abbr = today.strftime("%a %d %b")
    if done == expected:
        print(f"  {C.GREEN}✓ Today ({day_abbr}): all {expected} prayers done. MashaAllah!{C.RESET}")
    elif done == 0:
        remaining_str = ", ".join(remaining)
        print(f"  {C.RED}Today ({day_abbr}): 0/{expected} — {remaining_str} all remaining{C.RESET}")
    else:
        remaining_str = ", ".join(remaining)
        print(f"  {C.YELLOW}Today ({day_abbr}): {done}/{expected} done  {C.GRAY}— {remaining_str} remaining{C.RESET}")
    print()


def print_most_missed(data):
    """Print most-missed prayer for current + last month (feature 2.3)."""
    cur_label, cur_results = get_most_missed(data, "current_month")
    last_label, last_results = get_most_missed(data, "last_month")

    def worst(results):
        if not results:
            return None, 0
        p = min(results, key=results.get)
        return p, results[p]

    cur_worst, cur_pct = worst(cur_results)
    last_worst, last_pct = worst(last_results)

    if cur_worst:
        pct_str = f"{cur_pct*100:.0f}%"
        color = C.RED if cur_pct < 0.5 else (C.YELLOW if cur_pct < 0.8 else C.GREEN)
        print(f"  {C.BLUE}Most missed ({cur_label})  {color}{cur_worst} {C.GRAY}({pct_str} completion){C.RESET}")
    if last_worst and last_label != cur_label:
        pct_str = f"{last_pct*100:.0f}%"
        color = C.RED if last_pct < 0.5 else (C.YELLOW if last_pct < 0.8 else C.GREEN)
        print(f"  {C.BLUE}Most missed ({last_label})  {color}{last_worst} {C.GRAY}({pct_str} completion){C.RESET}")
    if cur_worst or last_worst:
        print()


def print_summary(data):
    """Print weekly/monthly summary (feature 2.1)."""
    s = get_weekly_monthly_summary(data)
    today = date.today()

    print(f"\n  {C.MAUVE}{C.BOLD}Summary{C.RESET}\n")
    print_divider()
    print()

    # This week
    week_pct = s["week_done"] / s["week_owed"] * 100 if s["week_owed"] else 0
    wcolor = C.GREEN if week_pct >= 80 else (C.YELLOW if week_pct >= 50 else C.RED)
    week_start = today - timedelta(days=today.weekday())
    print(f"  {C.LAVEN}This week  {C.GRAY}(Mon {week_start.strftime('%d %b')} – today){C.RESET}")
    print(f"  {C.WHITE}{s['week_done']:,}{C.GRAY}/{s['week_owed']:,} prayers  {wcolor}{week_pct:.0f}%{C.RESET}")
    print()

    # This month
    month_pct = s["month_done"] / s["month_owed"] * 100 if s["month_owed"] else 0
    mcolor = C.GREEN if month_pct >= 80 else (C.YELLOW if month_pct >= 50 else C.RED)
    print(f"  {C.LAVEN}This month  {C.GRAY}({today.strftime('%B')}){C.RESET}")
    print(f"  {C.WHITE}{s['month_done']:,}{C.GRAY}/{s['month_owed']:,} prayers  {mcolor}{month_pct:.0f}%{C.RESET}")
    if s["best_day"]:
        bday = s["best_day"]
        print(f"  {C.GRAY}Best day: {C.PEACH}{bday.strftime('%a %d %b')}{C.GRAY} ({s['best_day_count']} prayers){C.RESET}")
    print()

    # Streaks
    streak = s["daily_streak"]
    longest = s["longest_streak"]
    sc = C.GREEN if streak >= 7 else (C.YELLOW if streak >= 3 else C.GRAY)
    print(f"  {C.LAVEN}Daily streak{C.RESET}  {C.GRAY}(all 5 prayed){C.RESET}")
    print(f"  {sc}{streak} day{'s' if streak != 1 else ''} current{C.GRAY}  •  best ever: {longest} day{'s' if longest != 1 else ''}{C.RESET}")
    print()

    # Most-missed this month & last
    print_divider()
    print()
    print_most_missed(data)


    """Show an encouraging message based on progress."""
    stats, _, _ = get_stats(data)
    total_done = sum(s["done"] for s in stats.values())
    total_owed = sum(s["owed"] for s in stats.values())

    if total_owed == 0:
        return

    pct = total_done / total_owed * 100

    messages = [
        (0,    f"{C.YELLOW}Every journey begins with a single step. You've got this!{C.RESET}"),
        (1,    f"{C.PEACH}Alhamdulillah! You've started. Keep going!{C.RESET}"),
        (5,    f"{C.PEACH}MashaAllah, {total_done:,} prayers completed! Consistency is key.{C.RESET}"),
        (10,   f"{C.GREEN}SubhanAllah! 10% done. You're building momentum!{C.RESET}"),
        (25,   f"{C.GREEN}Quarter of the way there! Allah sees your effort.{C.RESET}"),
        (50,   f"{C.GREEN}{C.BOLD}Halfway! MashaAllah, what an achievement!{C.RESET}"),
        (75,   f"{C.MAUVE}{C.BOLD}75%! The finish line is in sight, keep pushing!{C.RESET}"),
        (90,   f"{C.MAUVE}{C.BOLD}SubhanAllah! So close! Almost there!{C.RESET}"),
        (99.9, f"{C.YELLOW}{C.BOLD}Just a few more... you can do it!{C.RESET}"),
        (100,  f"{C.GREEN}{C.BOLD}Allahu Akbar! All prayers completed! May Allah accept!{C.RESET}"),
    ]

    msg = messages[0][1]
    for threshold, m in messages:
        if pct >= threshold:
            msg = m

    print(f"  {msg}")
    print()


def setup_wizard():
    """First-time setup."""
    clear()
    banner()
    print_bismillah()

    print(f"  {C.MAUVE}Welcome! Let's set up your prayer tracker.{C.RESET}\n")

    # Name (optional, 5.3)
    name_input = input(f"  {C.SKY}Your name (optional, press Enter to skip):{C.RESET} ").strip()
    name = name_input[:40] if name_input else ""  # cap at 40 chars

    print()

    # Date of birth
    while True:
        dob_input = input(f"  {C.SKY}Your date of birth (YYYY-MM-DD):{C.RESET} ").strip()
        try:
            dob = date.fromisoformat(dob_input)
            if dob > date.today():
                print(f"  {C.RED}That's in the future!{C.RESET}\n")
                continue
            break
        except ValueError:
            print(f"  {C.RED}Invalid format. Please use YYYY-MM-DD{C.RESET}\n")

    # Puberty age
    print(f"\n  {C.GRAY}Prayer becomes obligatory at puberty.{C.RESET}")
    print(f"  {C.GRAY}Default is age 15 if unsure.{C.RESET}\n")

    while True:
        age_input = input(f"  {C.SKY}Age of obligation{C.RESET} [{C.GRAY}15{C.RESET}]: ").strip()
        if age_input == "":
            puberty_age = 15
            break
        try:
            puberty_age = int(age_input)
            if 7 <= puberty_age <= 20:
                break
            print(f"  {C.RED}Please enter an age between 7 and 20{C.RESET}\n")
        except ValueError:
            print(f"  {C.RED}Please enter a number{C.RESET}\n")

    data = init_data(dob, puberty_age, name)
    save_data(data)

    start = get_start_date(data)
    feb29_note = ""
    if dob.month == 2 and dob.day == 29 and not calendar.isleap(start.year):
        feb29_note = f"\n  {C.GRAY}(Feb 29 DOB → obligation start moved to Mar 1 {start.year} — not a leap year){C.RESET}"
    greeting = f" {name}," if name else ""
    print(f"\n  {C.RESP}Setup complete{greeting}! Tracking {days_since_start(data):,} days of prayers from {start}.{C.RESET}{feb29_note}\n")

    input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")
    return data


def settings_menu(data):
    """Change DOB or puberty age without losing progress."""
    print(f"\n  {C.MAUVE}{C.BOLD}Settings{C.RESET}\n")
    cur_name = data.get("name", "") or "(not set)"
    print(f"  {C.BLUE}Name                 {C.WHITE}{cur_name}{C.RESET}")
    print(f"  {C.BLUE}Current DOB          {C.WHITE}{data['dob']}{C.RESET}")
    print(f"  {C.BLUE}Current puberty age  {C.WHITE}{data['puberty_age']}{C.RESET}")
    print(f"  {C.BLUE}Obligation from      {C.WHITE}{data['start_date']}{C.RESET}")
    print()
    print(f"  {C.PEACH}[1]{C.RESET} {C.GRAY}Change name{C.RESET}")
    print(f"  {C.PEACH}[2]{C.RESET} {C.GRAY}Change date of birth{C.RESET}")
    print(f"  {C.PEACH}[3]{C.RESET} {C.GRAY}Change age of obligation{C.RESET}")
    print(f"  {C.PEACH}[4]{C.RESET} {C.GRAY}Change both DOB and age{C.RESET}")
    print(f"  {C.PEACH}[0]{C.RESET} {C.GRAY}Cancel{C.RESET}")
    print()

    choice = input(f"  {C.SKY}Option>{C.RESET} ").strip()

    if choice == "0" or choice == "":
        print(f"\n  {C.RESP}No changes made. Settings unchanged.{C.RESET}")
        return data

    if choice == "1":
        name_input = input(f"\n  {C.SKY}New name (Enter to clear):{C.RESET} ").strip()
        data["name"] = name_input[:40]
        save_data(data)
        label = data["name"] if data["name"] else "(cleared)"
        print(f"\n  {C.RESP}Name updated to: {label}{C.RESET}")
        return data

    new_dob = date.fromisoformat(data["dob"])
    new_age = data["puberty_age"]

    if choice in ("2", "4"):
        while True:
            dob_input = input(f"\n  {C.SKY}New date of birth (YYYY-MM-DD){C.RESET} [{C.GRAY}{data['dob']}{C.RESET}]: ").strip()
            if dob_input == "":
                break
            try:
                new_dob = date.fromisoformat(dob_input)
                if new_dob > date.today():
                    print(f"  {C.RED}That's in the future!{C.RESET}")
                    continue
                break
            except ValueError:
                print(f"  {C.RED}Invalid format. Use YYYY-MM-DD{C.RESET}")

    if choice in ("3", "4"):
        while True:
            age_input = input(f"\n  {C.SKY}New age of obligation{C.RESET} [{C.GRAY}{data['puberty_age']}{C.RESET}]: ").strip()
            if age_input == "":
                break
            try:
                new_age = int(age_input)
                if 7 <= new_age <= 20:
                    break
                print(f"  {C.RED}Please enter an age between 7 and 20{C.RESET}")
            except ValueError:
                print(f"  {C.RED}Please enter a number{C.RESET}")

    new_start = obligation_start_date(new_dob, new_age)

    # Show what will change
    print(f"\n  {C.YELLOW}{C.BOLD}Review changes:{C.RESET}")
    print(f"  {C.GRAY}DOB:             {data['dob']}  →  {C.WHITE}{new_dob.isoformat()}{C.RESET}")
    print(f"  {C.GRAY}Puberty age:     {data['puberty_age']}  →  {C.WHITE}{new_age}{C.RESET}")
    print(f"  {C.GRAY}Obligation from: {data['start_date']}  →  {C.WHITE}{new_start.isoformat()}{C.RESET}")
    print()
    print(f"  {C.GRAY}Your completed prayer marks will be kept.{C.RESET}")
    print(f"  {C.GRAY}(Marks before the new start date won't count toward stats){C.RESET}\n")

    confirm = input(f"  {C.SKY}Apply changes? (yes/no):{C.RESET} ").strip().lower()
    if confirm == "yes":
        data["dob"] = new_dob.isoformat()
        data["puberty_age"] = new_age
        data["start_date"] = new_start.isoformat()
        save_data(data)
        print(f"\n  {C.RESP}Settings updated successfully! Now tracking from {new_start.isoformat()}.{C.RESET}")
    else:
        print(f"\n  {C.RESP}Changes discarded. Your settings remain the same.{C.RESET}")

    return data


def hard_reset(data):
    """Multi-step reset to prevent accidental data loss."""
    import random

    stats, _, _ = get_stats(data)
    total_done = sum(s["done"] for s in stats.values())

    print(f"\n  {C.RED}{C.BOLD}⚠  DANGER ZONE  ⚠{C.RESET}")
    print(f"\n  {C.RED}This will permanently erase ALL your data:{C.RESET}")
    print(f"  {C.GRAY}  • Your date of birth & settings{C.RESET}")
    print(f"  {C.GRAY}  • {C.PINK}{total_done:,}{C.GRAY} completed prayer marks{C.RESET}")
    print(f"  {C.GRAY}  • Everything. Gone forever.{C.RESET}")
    print()

    # Step 1: type "I want to reset"
    print(f"  {C.RED}Type exactly:{C.RESET}  {C.YELLOW}{C.BOLD}I want to reset{C.RESET}\n")
    confirm1 = input(f"  {C.RED}>{C.RESET} ").strip()
    if confirm1 != "I want to reset":
        print(f"\n  {C.RESP}Didn't match. Reset cancelled. Your data is safe.{C.RESET}")
        return data

    # Step 2: verify identity by entering DOB
    print(f"\n  {C.RED}To verify your identity, enter your date of birth:{C.RESET}\n")
    dob_input = input(f"  {C.RED}DOB (YYYY-MM-DD)>{C.RESET} ").strip()
    if dob_input != data["dob"]:
        print(f"\n  {C.RESP}DOB doesn't match. Reset cancelled. Your data is safe.{C.RESET}")
        return data

    # Step 3: type a random confirmation phrase
    phrases = [
        "DELETE MY DATA",
        "ERASE EVERYTHING",
        "NO GOING BACK",
        "DESTROY ALL PROGRESS",
        "PERMANENT DELETE",
    ]
    phrase = random.choice(phrases)

    print(f"\n  {C.RED}To confirm, type exactly:{C.RESET}  {C.YELLOW}{C.BOLD}{phrase}{C.RESET}\n")
    confirm2 = input(f"  {C.RED}Type here>{C.RESET} ").strip()

    if confirm2 != phrase:
        print(f"\n  {C.RESP}Phrase didn't match. Reset cancelled. Your data is safe.{C.RESET}")
        return data

    # Step 4: 5-second countdown with option to abort
    import time
    print(f"\n  {C.RED}{C.BOLD}FINAL COUNTDOWN — Press Ctrl+C to abort!{C.RESET}\n")
    try:
        for i in range(5, 0, -1):
            print(f"  {C.RED}  Deleting in {i}...{C.RESET}", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n\n  {C.RESP}Aborted! Your data is safe. Nothing was deleted.{C.RESET}")
        return data

    # Step 5: final RESET
    print(f"\n  {C.RED}{C.BOLD}LAST CHANCE.{C.RESET}")
    confirm3 = input(f"  {C.RED}Type 'RESET' to destroy everything:{C.RESET} ").strip()

    if confirm3 != "RESET":
        print(f"\n  {C.RESP}Reset cancelled. Your {total_done:,} prayer marks are safe.{C.RESET}")
        return data

    # Actually reset
    DATA_FILE.unlink(missing_ok=True)
    print(f"\n  {C.RESP}All data has been erased. Starting fresh setup...{C.RESET}\n")
    input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")
    return setup_wizard()


def print_heatmap(data, year=None):
    """Display a GitHub-style heatmap for a full year.
    3 states only: empty (0 prayers), amber (some), teal (all done).
    """
    if year is None:
        year = date.today().year

    today      = date.today()
    start      = get_start_date(data)

    # Colours: 3 states
    COL_NONE   = C.GRAY          # 0 prayers
    COL_SOME   = C.YELLOW        # 1–(n-1) prayers
    COL_FULL   = C.TEAL          # all done
    COL_FUTURE = C.GRAY + C.DIM  # future / before start
    BLOCK      = "█"

    MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
              "Jul","Aug","Sep","Oct","Nov","Dec"]

    print(f"\n  {C.MAUVE}{C.BOLD}Prayer heatmap — {year}{C.RESET}\n")

    for mi, month_name in enumerate(MONTHS):
        month_num = mi + 1
        # days in this month (handle leap years)
        if month_num == 12:
            days_in_month = (date(year + 1, 1, 1) - date(year, 12, 1)).days
        else:
            days_in_month = (date(year, month_num + 1, 1) - date(year, month_num, 1)).days

        row = f"  {C.BLUE}{month_name}{C.RESET} "

        for day in range(1, days_in_month + 1):
            try:
                d = date(year, month_num, day)
            except ValueError:
                continue

            if d > today or d < start:
                row += f"{COL_FUTURE}{BLOCK}{C.RESET}"
                continue

            is_friday = d.weekday() == 4
            expected  = 6 if is_friday else 5
            done      = len(data["completed"].get(d.isoformat(), []))

            if done == 0:
                row += f"{COL_NONE}{BLOCK}{C.RESET}"
            elif done >= expected:
                row += f"{COL_FULL}{BLOCK}{C.RESET}"
            else:
                row += f"{COL_SOME}{BLOCK}{C.RESET}"

        print(row)

    # Legend
    print()
    print(f"  {C.GRAY}legend   "
          f"{COL_NONE}{BLOCK}{C.RESET} none   "
          f"{COL_SOME}{BLOCK}{C.RESET} some   "
          f"{COL_FULL}{BLOCK}{C.RESET} all done{C.RESET}")
    print()


def print_help():
    """Display help/commands."""
    print(f"\n  {C.MAUVE}{C.BOLD}Commands{C.RESET}\n")
    cmds = [
        ("today / t",        "Quick-mark today's prayers (interactive)"),
        ("today a",          "Mark all of today's prayers at once"),
        ("stats / s",        "Show prayer overview & progress"),
        ("summary",          "Weekly/monthly summary & streaks"),
        ("cal / c",          "Show calendar for current month"),
        ("cal YYYY-MM",      "Show calendar for specific month"),
        ("day / d",          "Show detail for a specific day"),
        ("mark / m",         "Mark prayers — interactive"),
        ("mark DATE",        "Mark prayers for a date"),
        ("mark DATE a",      "Quick-mark all prayers for date"),
        ("mark DATE 1,3",    "Quick-toggle specific prayers"),
        ("mark yesterday",   "Mark yesterday's prayers"),
        ("mark -3",          "Mark prayers 3 days ago"),
        ("heatmap / hm",      "Full-year prayer heatmap"),
        ("heatmap YYYY",      "Heatmap for a specific year"),
        ("settings",         "Change name, DOB or puberty age"),
        ("reset",            "Reset all data (5-step confirm)"),
        ("help / h",         "Show this help message"),
        ("quit / q",         "Exit the tracker"),
    ]
    for cmd, desc in cmds:
        print(f"  {C.PEACH}{cmd:<20}{C.RESET} {C.GRAY}{desc}{C.RESET}")
    print()
    print(f"  {C.GRAY}Dates accept: YYYY-MM-DD  •  today  •  yesterday  •  -1  •  -3  etc.{C.RESET}")
    print()


def main_loop(data):
    """Main interactive loop."""
    show_help = False
    while True:
        if show_help:
            show_help = False
            print(f"  {C.GRAY}Type a command from above, or press Enter for home{C.RESET}\n")
        else:
            clear()
            banner(data)
            print_today_quickview(data)
            motivation_message(data)
            print_stats_table(data)
            print_most_missed(data)

            today = date.today()
            print_calendar(data, today.year, today.month)

            print_divider()
            print()
            print(f"  {C.GRAY}Type a command or 'help' for options{C.RESET}\n")

        try:
            cmd = input(f"  {C.MAUVE}~>{C.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n\n  {C.YELLOW}Assalamu Alaikum! May Allah accept your prayers.{C.RESET}\n")
            sys.exit(0)

        cmd_lower = cmd.lower()

        # ── Quit (1.6: exit nudge) ───────────────────────────────────
        if cmd_lower in ("q", "quit", "exit"):
            status = get_today_status(data)
            if status:
                done, expected, remaining = status
                if done < expected:
                    remaining_str = ", ".join(remaining)
                    print(f"\n  {C.YELLOW}You haven't logged all of today's prayers yet.{C.RESET}")
                    print(f"  {C.GRAY}{done}/{expected} done — {remaining_str} remaining.{C.RESET}")
                    confirm = input(f"\n  {C.SKY}Still exit? (y/n):{C.RESET} ").strip().lower()
                    if confirm not in ("y", "yes"):
                        print(f"\n  {C.RESP}Good — let's get those prayers logged first!{C.RESET}\n")
                        input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")
                        continue
            print(f"\n  {C.RESP}Session ended. Assalamu Alaikum! May Allah accept your prayers.{C.RESET}\n")
            break

        # ── Today command (1.5 bonus: instant today marking) ────────
        elif cmd_lower in ("today", "t") or cmd_lower.startswith("today "):
            parts = cmd_lower.split(None, 1)
            if len(parts) == 1:
                mark_prayers_menu(data, prefill_date=date.today().isoformat())
            else:
                # "today a" or "today 1,3"
                quick_mark(data, date.today().isoformat(), parts[1])
            print()
            input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")

        # ── Stats ────────────────────────────────────────────────────
        elif cmd_lower in ("stats", "s"):
            clear()
            banner(data)
            print_stats_table(data)
            print(f"\n  {C.RESP}Showing your full prayer statistics above.{C.RESET}\n")
            input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")

        # ── Summary (2.1) ────────────────────────────────────────────
        elif cmd_lower == "summary":
            clear()
            banner(data)
            print_summary(data)
            print(f"  {C.RESP}Weekly & monthly summary shown above.{C.RESET}\n")
            input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")

        # ── Heatmap (2.5) ────────────────────────────────────────────
        elif cmd_lower in ("heatmap", "hm") or cmd_lower.startswith("heatmap ") or cmd_lower.startswith("hm "):
            parts = cmd_lower.split()
            yr = None
            if len(parts) > 1:
                try:
                    yr = int(parts[1])
                    if not (2000 <= yr <= 2100):
                        raise ValueError
                except ValueError:
                    print(f"\n  {C.RESP}Invalid year '{parts[1]}'. Use a 4-digit year e.g. heatmap 2025.{C.RESET}\n")
                    input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")
                    continue
            clear()
            banner(data)
            print_heatmap(data, yr)
            print(f"  {C.RESP}Showing heatmap for {yr or date.today().year}. Grey = none, amber = partial, teal = all done.{C.RESET}\n")
            input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")

        # ── Mark (with relative date support, 1.4 alias m) ──────────
        elif cmd_lower in ("mark", "m") or cmd_lower.startswith("mark ") or cmd_lower.startswith("m "):
            # Normalise alias: "m" → "mark", "m DATE" → "mark DATE"
            if cmd_lower.startswith("m ") and not cmd_lower.startswith("mark"):
                cmd_lower = "mark " + cmd_lower[2:]
            parts = cmd_lower.split(None, 2)
            if len(parts) == 1:
                mark_prayers_menu(data)
            else:
                # Resolve relative date in parts[1]
                resolved = parse_relative_date(parts[1])
                if resolved is None:
                    print(f"\n  {C.RESP}Invalid date '{parts[1]}'. Use YYYY-MM-DD, today, yesterday, -1, -3, etc.{C.RESET}\n")
                    input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")
                    continue
                date_str = resolved.isoformat()
                if len(parts) == 2:
                    mark_prayers_menu(data, prefill_date=date_str)
                else:
                    quick_mark(data, date_str, parts[2])
            print()
            input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")

        # ── Calendar (1.4 alias c) ───────────────────────────────────
        elif cmd_lower in ("cal", "c") or cmd_lower.startswith("cal ") or cmd_lower.startswith("c "):
            if cmd_lower.startswith("c ") and not cmd_lower.startswith("cal"):
                cmd_lower = "cal " + cmd_lower[2:]
            parts = cmd_lower.split()
            if len(parts) == 1:
                y, m = date.today().year, date.today().month
            else:
                try:
                    ym = parts[1].split("-")
                    y, m = int(ym[0]), int(ym[1])
                except (ValueError, IndexError):
                    print(f"\n  {C.RESP}Invalid format. Use: cal YYYY-MM (e.g. cal 2026-03).{C.RESET}\n")
                    input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")
                    continue
            clear()
            banner(data)
            for offset in [-1, 0, 1]:
                nm = m + offset
                ny = y
                if nm < 1:
                    nm = 12; ny -= 1
                elif nm > 12:
                    nm = 1; ny += 1
                print_calendar(data, ny, nm)
            print(f"  {C.RESP}Showing 3-month calendar view. Green = all done, peach = partial.{C.RESET}\n")
            input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")

        # ── Day detail (1.4 alias d) ─────────────────────────────────
        elif cmd_lower in ("day", "d"):
            date_input = input(f"\n  {C.SKY}Date (YYYY-MM-DD / today / yesterday / -N){C.RESET} [{C.GRAY}{date.today()}{C.RESET}]: ").strip()
            if date_input == "":
                d = date.today()
            else:
                d = parse_relative_date(date_input)
                if d is None:
                    print(f"\n  {C.RESP}Invalid date format.{C.RESET}\n")
                    input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")
                    continue
            print_day_detail(data, d)
            day_str = d.isoformat()
            done = len(data["completed"].get(day_str, []))
            is_fri = d.weekday() == 4
            exp = 6 if is_fri else 5
            start = get_start_date(data)
            if d >= start and d <= date.today():
                print(f"  {C.RESP}Showing prayer detail for {d.strftime('%d %B %Y')}. {done}/{exp} completed.{C.RESET}\n")
            input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")

        # ── Bulk (1.4 alias b) ───────────────────────────────────────
        elif cmd_lower in ("bulk", "b"):
            bulk_mark_menu(data)
            print()
            input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")

        # ── Settings ─────────────────────────────────────────────────
        elif cmd_lower == "settings":
            data = settings_menu(data)
            print()
            input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")

        # ── Reset ────────────────────────────────────────────────────
        elif cmd_lower == "reset":
            data = hard_reset(data)
            print()
            input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")

        # ── Help (1.4 alias h) ───────────────────────────────────────
        elif cmd_lower in ("help", "h"):
            clear()
            banner(data)
            print_help()
            print(f"  {C.RESP}All available commands shown above. Type one to get started.{C.RESET}\n")
            show_help = True
            continue

        elif cmd_lower == "":
            continue

        else:
            print(f"\n  {C.RESP}Unknown command: '{cmd}'. Type 'help' to see available commands.{C.RESET}\n")
            input(f"  {C.GRAY}Press Enter to continue...{C.RESET}")


def main():
    """Entry point."""
    try:
        data = load_data()
        if data is None:
            data = setup_wizard()
        main_loop(data)
    except KeyboardInterrupt:
        print(f"\n\n  {C.RESP}Session interrupted. Assalamu Alaikum! May Allah accept your prayers.{C.RESET}\n")


if __name__ == "__main__":
    main()