#!/usr/bin/env python3
"""
EleutherAI #off-topic Daily Alpha Digest
Fetches last 24h of messages, runs through Gemini Flash, emails the result.
Zero external dependencies — stdlib only + REST APIs.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

# ── Config (from environment / GitHub Secrets) ──
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")  # e.g. "jaisongeorge/eleuther-digest"

CHANNEL_ID = "730095596861521970"  # EleutherAI #off-topic
GUILD_ID = "729741769192767510"
DISCORD_EPOCH = 1420070400000
HOURS = int(os.environ.get("HOURS", "24"))

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


# ── Discord Export ──
def timestamp_to_snowflake(dt):
    ms = int(dt.timestamp() * 1000)
    return (ms - DISCORD_EPOCH) << 22


def fetch_page(after_id):
    url = (f"https://discord.com/api/v9/channels/{CHANNEL_ID}"
           f"/messages?limit=100&after={after_id}")
    req = urllib.request.Request(url, headers=DISCORD_HEADERS)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def export_messages():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS)
    after_id = timestamp_to_snowflake(cutoff)
    all_msgs = []
    page = 0

    print(f"Fetching messages since {cutoff.strftime('%Y-%m-%d %H:%M UTC')}...")
    while True:
        msgs = fetch_page(after_id)
        if not msgs:
            break
        msgs.sort(key=lambda m: int(m["id"]))
        all_msgs.extend(msgs)
        after_id = max(int(m["id"]) for m in msgs)
        page += 1
        print(f"  Page {page}: {len(all_msgs)} messages")
        time.sleep(0.5)

    # Deduplicate
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


# ── Gemini Flash ──
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
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())

    return result["candidates"][0]["content"]["parts"][0]["text"]


# ── Notify via GitHub Issue (GitHub emails you automatically) ──
def post_digest(subject, body):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("No GITHUB_TOKEN — printing to stdout instead:")
        print("=" * 60)
        print(body)
        print("=" * 60)
        return

    payload = {"title": subject, "body": body, "labels": ["digest"]}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    print(f"Posted: {result['html_url']}")


# ── Main ──
def main():
    # 1. Export
    messages = export_messages()
    if not messages:
        print(f"No messages in the last {HOURS}h. Skipping.")
        return

    text = messages_to_text(messages)
    print(f"\n{len(messages)} messages, {len(text)} chars")

    # 2. Analyze
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print("Calling Gemini Flash...")
    analysis = call_gemini(text, date_str, len(messages))
    print("Analysis complete.")

    # 3. Email
    subject = f"EleutherAI Alpha Digest — {date_str} ({len(messages)} msgs)"
    post_digest(subject, analysis)

    # 4. Also save locally if running manually
    if "GITHUB_ACTIONS" not in os.environ:
        with open("digest-output.md", "w") as f:
            f.write(f"# {subject}\n\n{analysis}")
        print("Saved to digest-output.md")


if __name__ == "__main__":
    main()
