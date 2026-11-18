"""
Zostel Kumbalangi watcher, Nov 21-22 (v2).

Alerts when EITHER is true:
  A) 2+ beds free across "Deluxe 10 Bed Mixed Dorm" + "Deluxe 8 Bed Mixed Dorm"
  B) 1+ bed in a Deluxe 10/8 Bed Mixed Dorm AND 1+ bed in "Deluxe 6 Bed Female Dorm"

Setup:
  pip install playwright requests
  playwright install chromium
  python zostel_watcher_v2.py            # normal run
  python zostel_watcher_v2.py --debug    # one check, saves page text to page_text.txt
"""
import os
import re
import sys
import time
import requests
from playwright.sync_api import sync_playwright

URL = ("https://www.zostel.com/destination/kochi/stay/zostel-kochi-kumbalangi-kmb332"
       "?checkin=2026-11-21&checkout=2026-11-22&rooms=1651@1")

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "change-me")   # set as a GitHub secret
CHECK_EVERY_SECONDS = 600                    # 10 minutes; don't go much lower

MIXED_10 = "Deluxe 10 Bed Mixed Dorm"
MIXED_8 = "Deluxe 8 Bed Mixed Dorm"
FEMALE_6 = "Deluxe 6 Bed Female Dorm"

# True = the 2 beds in condition A must be in the SAME dorm (2 in the 10-bed OR 2 in the 8-bed).
# False = 2 beds may be split across the 10-bed and 8-bed dorms.
SAME_DORM_ONLY = False


def notify(msg, priority="high"):
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=msg.encode("utf-8"),
            headers={"Title": "Zostel Kumbalangi", "Priority": priority},
            timeout=15,
        )
    except Exception as e:
        print("notify failed:", e)


def units_for(text, room_name):
    """Units shown for the check-in date (first column of the date strip) of a room."""
    low = text.lower()
    start = 0
    needle = room_name.lower()
    while True:
        i = low.find(needle, start)
        if i == -1:
            return None
        # first "N units" after the room name = first date column = Nov 21
        m = re.search(r"(\d+)\s*units?", text[i:i + 2500], flags=re.I)
        if m:
            return int(m.group(1))
        start = i + len(needle)


def check(page, debug=False):
    page.goto(URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)  # let the date strips render
    text = page.inner_text("body")
    if debug:
        with open("page_text.txt", "w", encoding="utf-8") as f:
            f.write(text)

    u10 = units_for(text, MIXED_10)
    u8 = units_for(text, MIXED_8)
    f6 = units_for(text, FEMALE_6)
    print(time.strftime("%H:%M:%S"), f"10-bed mixed={u10}, 8-bed mixed={u8}, 6-bed female={f6}")

    if u10 is None and u8 is None and f6 is None:
        print("Could not read any room. Run with --debug and check page_text.txt")
        return None

    u10, u8, f6 = u10 or 0, u8 or 0, f6 or 0
    mixed_total = u10 + u8

    if SAME_DORM_ONLY:
        cond_a = max(u10, u8) >= 2
    else:
        cond_a = mixed_total >= 2
    cond_b = mixed_total >= 1 and f6 >= 1

    if cond_a or cond_b:
        return f"10-bed mixed={u10}, 8-bed mixed={u8}, 6-bed female={f6}"
    return None


def main():
    debug = "--debug" in sys.argv
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        if debug:
            print("Result:", check(page, debug=True))
            browser.close()
            return
        if "--once" in sys.argv:
            # Single check, used by GitHub Actions (the schedule provides the repeat)
            hit = check(page)
            if hit:
                notify(f"Beds available for Nov 21-22! {hit}\n{URL}")
            browser.close()
            return
        notify("Watcher started for Nov 21-22.", priority="default")
        failures = 0
        while True:
            try:
                hit = check(page)
                failures = 0
                if hit:
                    notify(f"Beds available for Nov 21-22! {hit}\n{URL}")
                    break  # remove this line to keep watching after an alert
            except Exception as e:
                failures += 1
                print("check failed:", e)
                if failures == 6:
                    notify("Watcher is failing repeatedly, check the script.", priority="default")
            time.sleep(CHECK_EVERY_SECONDS)
        browser.close()


if __name__ == "__main__":
    main()
