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
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "jaison.sunny.george@gmail.com")

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
You are a sharp, direct intelligence analyst writing for a busy technical executive who skips anything that doesn't answer "so what?" in the first sentence.

## HARD RULES
- ENTIRE response under 800 words. Respect the reader's time.
- NEVER repeat a point. Each insight is unique.
- Skip social chatter, memes, complaints, off-topic banter.
- If a section has no signal, write "Nothing today." and move on.

## WRITING STYLE — Minto Pyramid
For EVERY signal, lead with the takeaway. Structure each bullet as:
**[TAKEAWAY in bold]** — then the evidence/context in 1-2 sentences. The bold part alone should be scannable and useful.

Bad: "Users are switching to vllm_mlx for inference."
Good: "**vllm_mlx emerging as the go-to for local model validation** — multiple users independently adopting it over ollama for quick model checks before deploying to cloud."

Bad: "Consensus that Codex is becoming unusable."
Good: "**Codex quality is in freefall** — power users reporting it removes working code, inserts hallucinated TODOs, and has gotten measurably worse in the last 2 weeks. Some switching to Claude Code."

## DATA
{msg_count} messages from EleutherAI #off-topic on {date_str}. These are ML researchers, infra engineers, and open-source contributors — people who ship.

{messages}

## OUTPUT — Lead with the single biggest signal of the day.

### TL;DR
One sentence. The single most important thing from today. Bold it.

### Tooling Moves
What tools/frameworks are people actually migrating to or abandoning? Only real switches, not drive-by mentions.

### Sentiment Shifts
Where has the hivemind flipped on a lab, model, or architecture? What's gaining or losing credibility?

### Research Going Live
Papers people are actually implementing, reproducing, or failing to reproduce. Not just links — real implementation discussion.

### Talent & Org Signals
Brain drain, team dysfunction, hiring freezes, morale shifts at major labs.

### Links Worth Clicking
Repos, posts, or tools that sparked real discussion (not just a link dump)."""


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


# ── Email via Resend (backup) ──
def send_email(subject, body):
    if not RESEND_API_KEY:
        return
    payload = {
        "from": "EleutherAI Digest <onboarding@resend.dev>",
        "to": [EMAIL_TO],
        "subject": subject,
        "text": body,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {RESEND_API_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
        print(f"Email sent to {EMAIL_TO}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Resend email failed: {e.code} {body}")
    except Exception as e:
        print(f"Resend email failed: {e}")


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
    send_email(subject, analysis)

    # 4. Also save locally if running manually
    if "GITHUB_ACTIONS" not in os.environ:
        with open("digest-output.md", "w") as f:
            f.write(f"# {subject}\n\n{analysis}")
        print("Saved to digest-output.md")


if __name__ == "__main__":
    main()
