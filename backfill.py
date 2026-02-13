#!/usr/bin/env python3
"""
Backfill: Run the digest for each of the last 7 days in 24h increments.
"""

import json
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

CHANNEL_ID = "730095596861521970"
GUILD_ID = "729741769192767510"
DISCORD_EPOCH = 1420070400000
OUTPUT_DIR = "/Users/jaisongeorge/Downloads/eleuther-digest/backfill"

DISCORD_HEADERS = {
    "Authorization": DISCORD_TOKEN,
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 Chrome/144.0.0.0 Safari/537.36",
    "Referer": f"https://discord.com/channels/{GUILD_ID}/{CHANNEL_ID}",
}

PROMPT = """## ROLE
You are a Senior Technical Intelligence Analyst extracting alpha from ML researcher Discord chats.

## HARD RULES
- Your ENTIRE response must be under 800 words.
- Maximum 5 bullet points per section. Pick only the STRONGEST signals.
- NEVER repeat a bullet point. Each bullet must be unique.
- If a section has no signal, write "No signal." and move on.
- Be terse. One line per bullet. No filler, no hedging.
- Skip social chatter, memes, complaints, and off-topic banter entirely.

## DATA
Raw chat log from EleutherAI #off-topic ({date_str}, {msg_count} messages):

{messages}

## OUTPUT FORMAT

### 1. Silent Migrations (Tooling Alpha)
Tools/libraries/frameworks people are switching to or abandoning.

### 2. Vibe Shifts (Consensus Alpha)
Where group consensus has flipped on a lab, model, or architecture.

### 3. Paper-to-Prod (Research Alpha)
Papers people are actually implementing or reproducing (not just linking).

### 4. Bearish Signals (Talent/Safety Alpha)
Brain drain, morale loss, team failures at major labs.

### 5. Notable Links
GitHub repos, blog posts, or tools that got genuine engagement."""


def ts_to_snowflake(dt):
    return (int(dt.timestamp() * 1000) - DISCORD_EPOCH) << 22

def fetch_page(after_id):
    url = (f"https://discord.com/api/v9/channels/{CHANNEL_ID}"
           f"/messages?limit=100&after={after_id}")
    req = urllib.request.Request(url, headers=DISCORD_HEADERS)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def export_window(start_dt, end_dt):
    after_id = ts_to_snowflake(start_dt)
    before_id = ts_to_snowflake(end_dt)
    all_msgs = []
    page = 0

    while True:
        msgs = fetch_page(after_id)
        if not msgs:
            break
        msgs = [m for m in msgs if int(m["id"]) < before_id]
        if not msgs:
            break
        msgs.sort(key=lambda m: int(m["id"]))
        all_msgs.extend(msgs)
        after_id = max(int(m["id"]) for m in msgs)
        page += 1
        print(f"    Page {page}: {len(all_msgs)} messages", flush=True)
        time.sleep(0.5)

    seen = set()
    unique = []
    for m in all_msgs:
        if m["id"] not in seen:
            seen.add(m["id"])
            unique.append(m)
    unique.sort(key=lambda m: int(m["id"]))
    return unique

def messages_to_text(messages):
    lines = []
    for msg in messages:
        author = msg["author"]["username"]
        ts = msg["timestamp"][:19].replace("T", " ")
        content = msg["content"] or ""
        attachments = [a["url"] for a in msg.get("attachments", [])]
        line = f"[{ts}] {author}: {content}"
        if attachments:
            line += f" [attachments: {', '.join(attachments)}]"
        lines.append(line)
    return "\n".join(lines)

def call_gemini(text, date_str, msg_count):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}")
    prompt_text = PROMPT.format(messages=text, date_str=date_str, msg_count=msg_count)
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1500,
            "frequencyPenalty": 1.5,
            "presencePenalty": 0.5,
        },
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
    return result["candidates"][0]["content"]["parts"][0]["text"]


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    now = datetime.now(timezone.utc)

    for day in range(7, 0, -1):
        start = now - timedelta(days=day)
        end = now - timedelta(days=day - 1)
        date_str = start.strftime("%Y-%m-%d")

        print(f"\n{'='*60}")
        print(f"DAY: {date_str}")
        print(f"{'='*60}")

        messages = export_window(start, end)
        if not messages:
            print(f"  No messages. Skipping.")
            continue

        text = messages_to_text(messages)
        print(f"  {len(messages)} messages, {len(text)} chars")

        txt_path = os.path.join(OUTPUT_DIR, f"{date_str}.txt")
        with open(txt_path, "w") as f:
            f.write(text)

        print(f"  Calling Gemini Flash...")
        try:
            analysis = call_gemini(text, date_str, len(messages))
        except Exception as e:
            print(f"  Gemini error: {e}. Waiting 60s...")
            time.sleep(60)
            analysis = call_gemini(text, date_str, len(messages))

        md_path = os.path.join(OUTPUT_DIR, f"{date_str}-digest.md")
        with open(md_path, "w") as f:
            f.write(f"# EleutherAI Alpha Digest — {date_str}\n")
            f.write(f"**{len(messages)} messages**\n\n")
            f.write(analysis)

        print(f"  Saved: {md_path}")
        time.sleep(2)

    print(f"\n{'='*60}")
    print(f"DONE! All digests in {OUTPUT_DIR}/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
