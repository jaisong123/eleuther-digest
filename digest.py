#!/usr/bin/env python3
"""
EleutherAI #off-topic Daily Alpha Digest
Fetches last 24h of messages, runs through Gemini Flash, emails the result.
Zero external dependencies — stdlib only + REST APIs.
"""

import json
import os
import re
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

PROMPT = """You are a sharp intelligence analyst writing a daily brief for a busy exec. They will skim this in 60 seconds. Every word must earn its place.

RULES:
- Under 800 words total.
- EVERY bullet MUST start with a bold actionable takeaway, then a dash, then 1-2 sentences of evidence. NO EXCEPTIONS.
- Format: <b>Takeaway that answers "so what?"</b> — Evidence from the chat with specific names/tools/numbers.
- If you can't explain why someone should care, cut the bullet.
- If a section has nothing, write "Nothing today." One line.
- NEVER repeat a point.

EXAMPLES OF GOOD BULLETS:
- <b>vllm_mlx is replacing ollama for local model checks</b> — 3 independent users switched this week, citing faster iteration loops before cloud deploy.
- <b>Codex is hemorrhaging power users to Claude Code</b> — Multiple reports of Codex deleting working code and hallucinating TODOs. Quality decline accelerated in last 2 weeks.
- <b>DeepSeek R1 reproduction attempt hit a wall on expert routing</b> — User implementing from scratch found their MoE load balancing diverges after 10K steps. No fix yet.

EXAMPLES OF BAD BULLETS (do NOT write like this):
- "Users are switching to vllm_mlx for inference." (no "so what", no evidence)
- "Interest in SNNs remains limited." (vague, no one cares)
- "Concerns about safety researchers leaving." (who? where? why does it matter?)

DATA: {msg_count} messages from EleutherAI #off-topic on {date_str}. These are ML researchers and infra engineers who ship.

{messages}

OUTPUT (use these exact section headers):

TL;DR
One bold sentence. The single most important signal today. Why it matters.

TOOLING MOVES
Real migrations — tools people are actually switching to or abandoning.

SENTIMENT SHIFTS
Where the hivemind flipped on a lab, model, or architecture. What's gaining or losing credibility and why.

RESEARCH GOING LIVE
Papers being implemented or reproduced. Specific details on what worked, what failed.

TALENT & ORG SIGNALS
Brain drain, team dysfunction, morale shifts at specific labs.

LINKS WORTH CLICKING
Repos, posts, or tools that sparked real discussion. Include the URL and why it matters."""


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


# ── Markdown to HTML ──
def md_to_html(text):
    """Convert the subset of markdown Gemini outputs to clean HTML email."""
    lines = text.split("\n")
    html_lines = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        # Section headers
        if stripped.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f'<h3 style="color:#1a1a2e;margin:18px 0 8px 0;font-size:16px">{stripped[4:]}</h3>')
        elif stripped.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f'<h2 style="color:#1a1a2e;margin:20px 0 10px 0;font-size:18px">{stripped[3:]}</h2>')
        # Bullet points
        elif stripped.startswith("* ") or stripped.startswith("- "):
            if not in_list:
                html_lines.append('<ul style="padding-left:20px">')
                in_list = True
            content = stripped[2:]
            # Convert **bold** to <b>bold</b>
            content = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', content)
            # Convert [text](url) to <a>
            content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', content)
            html_lines.append(f'<li style="margin:6px 0">{content}</li>')
        elif stripped == "":
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<br>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            # Convert inline **bold**
            converted = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', stripped)
            converted = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', converted)
            html_lines.append(f'<p style="margin:4px 0">{converted}</p>')
    if in_list:
        html_lines.append("</ul>")
    body_html = "\n".join(html_lines)
    return f'''<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;max-width:600px;line-height:1.5;color:#222">
{body_html}
</div>'''


# ── Email via Resend ──
def send_email(subject, body):
    if not RESEND_API_KEY:
        return
    html = md_to_html(body)
    payload = {
        "from": "EleutherAI Digest <onboarding@resend.dev>",
        "to": [EMAIL_TO],
        "subject": subject,
        "html": html,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "User-Agent": "EleutherDigest/1.0",
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
