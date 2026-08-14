#!/usr/bin/env python3
"""Convert the LeanCloud/MiniValine export into Waline rows.

This replaces the manual step in Waline's docs (paste the JSON into their web
converter and click a button). Reads _leancloud_backup/*.json produced by
leancloud_export.py and emits either:

  --format pgsql   _leancloud_backup/waline_import.sql   (for Neon / production)
  --format sqlite  writes rows straight into a waline.sqlite file (local testing)

Both formats go through the same build_rows() mapping on purpose: the mapping is
the error-prone part of this migration, so there is exactly one implementation of
it rather than one per dialect.

Two conversions are not obvious and are the whole reason this script exists:

1. Valine references replies by the parent's string objectId (pid/rid). Waline uses
   an integer autoincrement id. We assign ids in createdAt order and remap pid/rid
   through that table, so the reply threading survives.
2. Valine stored paths without a leading slash ("about/"), but the Waline client
   queries by window.location.pathname ("/about/"). Without normalising, every
   imported comment and view count would be orphaned from its page.
"""

import argparse
import json
import os
import re
import sqlite3
import sys

# MiniValine renders "@someone" mentions as <a href='#<objectId>'>, so the 24-hex
# LeanCloud ids are baked into the stored comment HTML as well as into pid/rid.
OBJECT_ID_ANCHOR = re.compile(r"#([0-9a-f]{24})\b")

BACKUP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "_leancloud_backup")

COMMENT_COLS = ("id", "comment", "insertedAt", "ip", "link", "mail", "nick",
                "pid", "rid", "status", "ua", "url", "createdAt", "updatedAt")
COUNTER_COLS = ("id", "time", "url")


def ts(v):
    """ISO-8601 UTC -> 'YYYY-MM-DD HH:MM:SS' (Waline stores naive UTC)."""
    if not v:
        return None
    return v.replace("T", " ").split(".")[0].rstrip("Z").strip()


def path(v):
    """Normalise a Valine path to the pathname the Waline client will query with."""
    if not v:
        return "/"
    v = v.strip()
    return v if v.startswith("/") else "/" + v


def build_rows():
    """Return (comment_rows, counter_rows, stats) as plain tuples, dialect-free."""
    with open(os.path.join(BACKUP, "Comment.json"), encoding="utf-8") as f:
        comments = json.load(f)
    with open(os.path.join(BACKUP, "Counter.json"), encoding="utf-8") as f:
        counters = json.load(f)

    # Ids must be assigned in insertion order so a parent always exists before the
    # child that references it.
    comments.sort(key=lambda c: c.get("createdAt") or "")
    id_of = {c["objectId"]: i + 1 for i, c in enumerate(comments)}

    def relink(body):
        """Repoint '@mention' anchors in the stored HTML at the new integer ids.

        Remapping pid/rid alone is not enough: the anchors live inside the comment
        body, so without this every '@someone' link in an imported comment would
        point at an element id that no longer exists.
        """
        if not body:
            return body, 0
        hits = [0]

        def sub(m):
            new = id_of.get(m.group(1))
            if new is None:
                return m.group(0)
            hits[0] += 1
            return "#%d" % new

        return OBJECT_ID_ANCHOR.sub(sub, body), hits[0]

    crows, orphans, replies, relinked = [], 0, 0, 0
    for c in comments:
        pid = id_of.get(c.get("pid"))
        rid = id_of.get(c.get("rid"))
        # A pid pointing at a comment missing from the export would silently hide
        # the reply in Waline's tree, so surface it rather than dropping it.
        if c.get("pid"):
            if pid is None:
                orphans += 1
                print("WARN  comment %s: parent %s missing, promoting to top level"
                      % (c["objectId"], c["pid"]))
            else:
                replies += 1
        body, n = relink(c.get("comment"))
        relinked += n
        crows.append((
            id_of[c["objectId"]], body, ts(c.get("createdAt")),
            c.get("ip"), c.get("link"), c.get("mail"), c.get("nick"),
            pid, rid, "approved", c.get("ua"), path(c.get("url")),
            ts(c.get("createdAt")), ts(c.get("updatedAt")),
        ))

    # Valine can hold several Counter rows per path; sum them so no views are lost.
    views = {}
    for k in counters:
        p = path(k.get("url") or k.get("xid"))
        views[p] = views.get(p, 0) + int(k.get("time") or 0)
    krows = [(i, n, p) for i, (p, n) in enumerate(sorted(views.items()), start=1)]

    stats = {"comments": len(crows), "replies": replies, "orphans": orphans,
             "relinked": relinked, "pages": len(krows), "views": sum(views.values())}
    return crows, krows, stats


def lit(v):
    """Quote a Python value as a SQL literal."""
    if v is None or v == "":
        return "NULL"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def emit_pgsql(crows, krows):
    out = os.path.join(BACKUP, "waline_import.sql")
    lines = [
        "-- Generated by py_scripts/leancloud_to_waline.py -- do not edit by hand.",
        "-- Run the official assets/waline.pgsql schema FIRST, then this file.",
        "BEGIN;",
        "",
    ]
    for r in crows:
        lines.append("INSERT INTO wl_comment (%s) VALUES (%s);"
                     % (", ".join(COMMENT_COLS), ", ".join(lit(v) for v in r)))
    lines.append("")
    for r in krows:
        lines.append("INSERT INTO wl_counter (%s) VALUES (%s);"
                     % (", ".join(COUNTER_COLS), ", ".join(lit(v) for v in r)))
    # Explicit-id inserts do not advance the sequences, so the next real comment
    # would collide with id 1. Resync them.
    lines += [
        "",
        "SELECT setval('wl_comment_seq', %d);" % max(len(crows), 1),
        "SELECT setval('wl_counter_seq', %d);" % max(len(krows), 1),
        "",
        "COMMIT;",
        "",
    ]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out


def emit_sqlite(crows, krows, db_path):
    con = sqlite3.connect(db_path)
    # Table names are capitalised in Waline's SQLite schema but lowercase in pgsql.
    con.execute("DELETE FROM wl_Comment")
    con.execute("DELETE FROM wl_Counter")
    con.executemany(
        "INSERT INTO wl_Comment (%s) VALUES (%s)"
        % (", ".join(COMMENT_COLS), ", ".join("?" * len(COMMENT_COLS))), crows)
    con.executemany(
        "INSERT INTO wl_Counter (%s) VALUES (%s)"
        % (", ".join(COUNTER_COLS), ", ".join("?" * len(COUNTER_COLS))), krows)
    con.commit()
    con.close()
    return db_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", choices=("pgsql", "sqlite"), default="pgsql")
    ap.add_argument("--db", help="path to waline.sqlite (required for --format sqlite)")
    args = ap.parse_args()

    crows, krows, stats = build_rows()

    if args.format == "pgsql":
        target = emit_pgsql(crows, krows)
    else:
        if not args.db:
            sys.exit("--format sqlite requires --db /path/to/waline.sqlite")
        target = emit_sqlite(crows, krows, args.db)

    for k in ("comments", "replies", "orphans", "relinked", "pages", "views"):
        print("%-9s %d" % (k, stats[k]))
    print("wrote     %s" % target)


if __name__ == "__main__":
    main()
