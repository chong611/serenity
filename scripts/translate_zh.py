#!/usr/bin/env python3
"""Translate tweet texts to Chinese and store them in tweets.text_zh.

Run after each ingest; only rows without a translation are processed:
    python scripts/translate_zh.py
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

from deep_translator import GoogleTranslator

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "serenity.sqlite"


def ensure_column(con):
    cols = [r[1] for r in con.execute("pragma table_info(tweets)")]
    if "text_zh" not in cols:
        con.execute("alter table tweets add column text_zh text")
        con.commit()


def main():
    ap = argparse.ArgumentParser(description="Translate tweets to Chinese")
    ap.add_argument("--pause", type=float, default=0.3, help="seconds between requests")
    args = ap.parse_args()

    con = sqlite3.connect(DB_PATH)
    ensure_column(con)
    rows = con.execute(
        "select tweet_id, text from tweets where text_zh is null and text != '' order by created_at"
    ).fetchall()
    if not rows:
        print("nothing to translate")
        return

    translator = GoogleTranslator(source="auto", target="zh-CN")
    done = 0
    for tweet_id, text in rows:
        try:
            translated = translator.translate(text[:4500])
        except Exception as exc:
            print(f"  failed {tweet_id}: {exc}", file=sys.stderr)
            continue
        con.execute("update tweets set text_zh=? where tweet_id=?", (translated, tweet_id))
        con.commit()
        done += 1
        if done % 20 == 0:
            print(f"translated {done}/{len(rows)}")
        time.sleep(args.pause)
    print(f"translated {done}/{len(rows)} tweets")


if __name__ == "__main__":
    main()
