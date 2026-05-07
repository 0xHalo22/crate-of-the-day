#!/usr/bin/env python3
"""
crate-of-the-day: highlight one new-ish rust crate per day.

pulls recently-updated crates from the crates.io public JSON API and
picks one to highlight based on a simple "this looks real" heuristic
(non-trivial description, some minimum download count, non-spam name).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://crates.io/api/v1/crates"
PER_PAGE = 50
USER_AGENT = "crate-of-the-day-bot (hallo@0xhalo22.dev; +https://github.com/0xHalo22/crate-of-the-day)"

ROOT = Path(__file__).resolve().parents[1]
HIGHLIGHTS_DIR = ROOT / "highlights"
LATEST_FILE = ROOT / "latest.md"
# a little state file so we don't highlight the same crate on consecutive days
RECENT_PICKS_FILE = ROOT / ".recent_picks.json"
RECENT_PICKS_WINDOW = 30  # don't repeat a crate within 30 days

# heuristic thresholds for "this crate looks real"
MIN_DOWNLOADS = 100
MIN_DESCRIPTION_LEN = 25


def fetch_json(url: str, attempts: int = 4, base_backoff: float = 2.0) -> dict:
    """fetch a json url with retries.

    crates.io's API is generally reliable but rate-limits aggressive callers.
    we make at most 2 calls per day so we won't hit rate limits, but we still
    want to ride out transient 5xx / network blips."""
    last_err: Exception | None = None
    backoff = base_backoff
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            if attempt < attempts:
                print(f"    fetch attempt {attempt}/{attempts} failed ({type(e).__name__}: {e}); retrying in {backoff:.1f}s")
                time.sleep(backoff)
                backoff *= 2
    raise RuntimeError(f"fetch failed after {attempts} attempts: {last_err}") from last_err


def fetch_page(sort: str, page: int = 1) -> list[dict]:
    params = {"sort": sort, "per_page": str(PER_PAGE), "page": str(page)}
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    data = fetch_json(url)
    return data.get("crates", [])


def load_recent_picks() -> list[str]:
    if not RECENT_PICKS_FILE.exists():
        return []
    try:
        return json.loads(RECENT_PICKS_FILE.read_text())
    except Exception:
        return []


def save_recent_picks(picks: list[str]) -> None:
    # keep only the last N picks
    picks = picks[-RECENT_PICKS_WINDOW:]
    RECENT_PICKS_FILE.write_text(json.dumps(picks, indent=2))


def looks_real(crate: dict) -> bool:
    """filter out obvious test/spam crates."""
    desc = (crate.get("description") or "").strip()
    if len(desc) < MIN_DESCRIPTION_LEN:
        return False
    if (crate.get("downloads") or 0) < MIN_DOWNLOADS:
        return False
    # filter out crates whose names look auto-generated or test-y
    name = (crate.get("name") or "").lower()
    if re.match(r"^(test|foo|bar|hello|example|demo|temp|tmp)[-_\d]", name):
        return False
    if re.match(r"^[a-z]+\d{4,}$", name):  # something1234
        return False
    return True


def pick_crate(crates: list[dict], recent: list[str]) -> dict | None:
    for c in crates:
        if c["name"] in recent:
            continue
        if looks_real(c):
            return c
    return None


def fmt_crate(c: dict, today: str) -> str:
    name = c["name"]
    version = c.get("newest_version") or c.get("max_version") or "?"
    desc = (c.get("description") or "").strip()
    downloads = c.get("downloads", 0)
    recent_downloads = c.get("recent_downloads", 0)
    updated = (c.get("updated_at") or "")[:10]
    repo = c.get("repository") or ""
    homepage = c.get("homepage") or ""
    docs = c.get("documentation") or f"https://docs.rs/{name}"
    crates_url = f"https://crates.io/crates/{name}"

    lines = [
        f"# crate of the day — {today}",
        "",
        f"## [`{name}`]({crates_url}) `v{version}`",
        "",
        f"> {desc}",
        "",
        "| | |",
        "|---|---|",
        f"| **downloads** | {downloads:,} ({recent_downloads:,} in the last 90 days) |",
        f"| **last updated** | {updated} |",
        f"| **docs** | {docs} |",
    ]
    if repo:
        lines.append(f"| **repository** | {repo} |")
    if homepage and homepage != repo:
        lines.append(f"| **homepage** | {homepage} |")
    lines += [
        "",
        f"```toml",
        f"[dependencies]",
        f'{name} = "{version}"',
        f"```",
        "",
        f"_picked at {datetime.now(timezone.utc).isoformat(timespec='seconds')} from the crates.io `recent-updates` feed_",
        "",
    ]
    return "\n".join(lines)


def run_git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, cwd=ROOT)


def main() -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"[crate-of-the-day] picking a crate for {today}")

    # try recent-updates first; if nothing suitable, fall back to new crates
    candidates = fetch_page("recent-updates")
    print(f"  pulled {len(candidates)} recently-updated crates")

    recent = load_recent_picks()
    pick = pick_crate(candidates, recent)
    if pick is None:
        print("  no suitable pick from recent-updates, trying 'new' feed")
        candidates = fetch_page("new")
        pick = pick_crate(candidates, recent)

    if pick is None:
        print("  no suitable crate found today, skipping")
        return 0

    print(f"  picked: {pick['name']} v{pick.get('newest_version')}")

    body = fmt_crate(pick, today)
    HIGHLIGHTS_DIR.mkdir(exist_ok=True)
    highlight_path = HIGHLIGHTS_DIR / f"{today}.md"
    highlight_path.write_text(body, encoding="utf-8")
    LATEST_FILE.write_text(body, encoding="utf-8")
    recent.append(pick["name"])
    save_recent_picks(recent)
    print(f"[crate-of-the-day] wrote {highlight_path} and latest.md")

    if os.environ.get("GITHUB_ACTIONS"):
        run_git("add", str(highlight_path), str(LATEST_FILE), str(RECENT_PICKS_FILE))
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
        )
        if not status.stdout.strip():
            print("[crate-of-the-day] no changes to commit")
            return 0
        msg = f"{today}: {pick['name']} v{pick.get('newest_version')}"
        run_git("commit", "-m", msg)
        print(f"[crate-of-the-day] committed: {msg}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
