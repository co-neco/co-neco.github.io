#!/usr/bin/env python3
"""Full export of the LeanCloud comment backend via the REST API.

LeanCloud shuts down on 2027-01-12, so this pulls every row out of the classes
the Shoka theme relies on (Comment = MiniValine comments, Counter = per-post
read counts) and writes them to _leancloud_backup/ as JSON.

The dump contains commenter emails and IP addresses, so _leancloud_backup/ is
gitignored. Do not commit it.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request

# These are LeanCloud *client* credentials: MiniValine shipped them in the page
# JavaScript, so every visitor to the blog already had them. They are kept as
# defaults so the export stays runnable, and can be overridden via the environment.
APP_ID = os.environ.get("LC_APP_ID", "0PN8lgYA6cq6o1hCj51lm8gI-gzGzoHsz")
APP_KEY = os.environ.get("LC_APP_KEY", "9PNRp6NQe1F0o9a0GQoYQM7u")
BASE = "https://shared.lc-cn-n1-shared.com/1.1/classes"

# LeanCloud caps limit at 1000 per request.
PAGE = 1000

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "_leancloud_backup")


def request(path, params):
    url = path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "X-LC-Id": APP_ID,
        "X-LC-Key": APP_KEY,
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def export_class(name):
    """Page through a class with a stable sort so rows can't be skipped."""
    total = request(BASE + "/" + name, {"count": 1, "limit": 0}).get("count", 0)
    print("%-8s reported %d rows" % (name, total))

    rows, skip = [], 0
    while True:
        batch = request(BASE + "/" + name, {
            "limit": PAGE,
            "skip": skip,
            "order": "createdAt",
        }).get("results", [])
        if not batch:
            break
        rows.extend(batch)
        skip += len(batch)
        print("%-8s fetched %d/%d" % (name, len(rows), total))
        if len(batch) < PAGE:
            break
        time.sleep(0.3)

    # objectId is the primary key; a duplicate here means paging went wrong.
    ids = [r.get("objectId") for r in rows]
    if len(set(ids)) != len(ids):
        sys.exit("%s: duplicate objectIds, paging is unreliable" % name)
    if len(rows) != total:
        print("%-8s WARNING: got %d rows but count said %d" % (name, len(rows), total))

    path = os.path.join(OUT_DIR, name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print("%-8s wrote %d rows -> %s" % (name, len(rows), path))
    return rows


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    summary = {}
    for name in ("Comment", "Counter"):
        summary[name] = len(export_class(name))
    print("\ndone:", summary)


if __name__ == "__main__":
    main()
