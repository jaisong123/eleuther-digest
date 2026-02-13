#!/usr/bin/env python3
"""
Multi-channel Discord Digest
Extracts daily digests from multiple Discord channels.
EleutherAI: daily email. tinygrad + seats.aero: daily extraction, weekly rollup.
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

# ── Config ──
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "jaison.sunny.george@gmail.com")
DISCORD_EPOCH = 1420070400000
HOURS = int(os.environ.get("HOURS", "24"))

# ── Channel Configs ──
CHANNELS = {
    "eleutherai": {
        "name": "EleutherAI #off-topic",
        "guild_id": "729741769192767510",
        "channel_id": "730095596861521970",
        "cadence": "daily",
        "label": "eleutherai",
        "email_subject": "EleutherAI Alpha Digest",
        "prompt": """You are a sharp intelligence analyst writing a daily brief for a busy exec. They will skim this in 60 seconds. Every word must earn its place.

RULES:
- Under 800 words total.
- EVERY bullet MUST start with a bold actionable takeaway, then a dash, then 1-2 sentences of evidence. NO EXCEPTIONS.
- Format: <b>Takeaway that answers "so what?"</b> — Evidence from the chat with specific names/tools/numbers.
- If you can't explain why someone should care, cut the bullet.
- If a section has nothing, write "Nothing today." One line.
- NEVER repeat a point.

EVERY bullet MUST include a direct quote from the chat as evidence. Format:
<b>Takeaway</b> — Context. As user_x put it: "exact quote from the log."

EXAMPLES OF GOOD BULLETS:
- <b>vllm_mlx is replacing ollama for local model checks</b> — 3 users switched this week. As cat_developer put it: "ollama is too slow for iteration, vllm_mlx just works."
- <b>Codex is hemorrhaging power users to Claude Code</b> — Multiple reports of deleted code and hallucinated TODOs. jerry0478: "codex just removed my entire auth module and replaced it with a TODO."
- <b>DeepSeek R1 reproduction hit a wall on expert routing</b> — MoE load balancing diverges after 10K steps. nruaif: "the routing just collapses, all tokens go to 2 experts."

EXAMPLES OF BAD BULLETS (do NOT write like this):
- "Users are switching to vllm_mlx for inference." (no quote, no "so what")
- "Interest in SNNs remains limited." (vague, no evidence, no names)
- "Codex's quality is questioned, with users reporting issues." (generic, no quote, who said what?)

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
Repos, posts, or tools that sparked real discussion. Include the URL and why it matters.""",
    },
    "tinygrad": {
        "name": "tinygrad #general",
        "guild_id": "1068976834382925865",
        "channel_id": "1068976834928193609",
        "cadence": "weekly",
        "label": "tinygrad",
        "email_subject": "tinygrad Weekly Digest",
        "prompt": """You are a sharp intelligence analyst writing a daily brief for a busy exec. They will skim this in 60 seconds. Every word must earn its place.

RULES:
- Under 800 words total.
- EVERY bullet MUST start with a bold actionable takeaway, then a dash, then 1-2 sentences of evidence. NO EXCEPTIONS.
- Format: <b>Takeaway that answers "so what?"</b> — Evidence from the chat with specific names/tools/numbers.
- If you can't explain why someone should care, cut the bullet.
- If a section has nothing, write "Nothing today." One line.
- NEVER repeat a point.

EVERY bullet MUST include a direct quote from the chat as evidence. Format:
<b>Takeaway</b> — Context. As user_x put it: "exact quote from the log."

DATA: {msg_count} messages from the tinygrad Discord #general on {date_str}. This is geohot's community — hackers, kernel devs, GPU/TPU infra people, and ML engineers who care about performance and open-source AI hardware.

{messages}

OUTPUT (use these exact section headers):

TL;DR
One bold sentence. The single most important signal today. Why it matters.

TINYGRAD & INFRA
Changes to tinygrad itself, new backends, driver hacks, performance wins, kernel optimizations.

GPU/TPU/HARDWARE
New hardware drops, driver issues, price movements, availability signals for GPUs/TPUs/ASICs.

MODEL & TRAINING
Models being trained, fine-tuned, or benchmarked. Interesting training runs or failures.

SENTIMENT SHIFTS
Where the hivemind flipped on a company, chip, framework, or approach.

LINKS WORTH CLICKING
Repos, posts, or tools that sparked real discussion. Include the URL and why it matters.""",
    },
    "seats-aero": {
        "name": "seats.aero #pro-chat",
        "guild_id": "1081857313096343672",
        "channel_id": "1092683036316926022",
        "cadence": "weekly",
        "label": "seats-aero",
        "email_subject": "seats.aero Weekly Digest",
        "prompt": """You are a sharp intelligence analyst writing a daily brief for a travel-hacking exec. They will skim this in 60 seconds. Every word must earn its place.

RULES:
- Under 800 words total.
- EVERY bullet MUST start with a bold actionable takeaway, then a dash, then 1-2 sentences of evidence. NO EXCEPTIONS.
- Format: <b>Takeaway that answers "so what?"</b> — Evidence from the chat with specific names/tools/numbers.
- If you can't explain why someone should care, cut the bullet.
- If a section has nothing, write "Nothing today." One line.
- NEVER repeat a point.

EVERY bullet MUST include a direct quote from the chat as evidence. Format:
<b>Takeaway</b> — Context. As user_x put it: "exact quote from the log."

DATA: {msg_count} messages from the seats.aero Pro Discord on {date_str}. These are serious points/miles enthusiasts, credit card optimizers, and award travel hackers.

{messages}

OUTPUT (use these exact section headers):

TL;DR
One bold sentence. The single most actionable signal today.

AWARD SWEET SPOTS
Routes with unusual availability, new award chart sweet spots, or redemptions people are actually booking.

CREDIT CARD MOVES
New cards, bonus offers, retention offers, product changes, or cards being cancelled/downgraded.

PROGRAM CHANGES
Airline/hotel loyalty program devaluations, new transfer partners, status match opportunities, policy changes.

DEALS & MISTAKE FARES
Specific fares, deals, or pricing errors people are jumping on. Routes and prices.

TIPS & STRATEGIES
Booking tricks, transfer timing, stacking strategies, or manufactured spending techniques that are working.""",
    },
}

WEEKLY_ROLLUP_PROMPT = """You are writing a weekly intelligence rollup for a busy exec. You have 7 daily digests from the past week. Your job is to synthesize them into one concise weekly report.

RULES:
- Under 1000 words.
- Lead with the single biggest signal of the week in a TL;DR.
- Identify TRENDS across the week, not just repeat daily bullets.
- Drop anything that was only mentioned once with no follow-up — it's noise.
- Keep direct quotes from the daily digests where they add color.
- NEVER repeat a point.

DAILY DIGESTS:
{digests}

OUTPUT (use these exact section headers):

TL;DR
One bold sentence. The single most important trend or signal this week.

TOP SIGNALS
The 3-5 most important takeaways from the entire week. These should be things that recurred, escalated, or had real impact.

EMERGING TRENDS
Patterns you see forming across multiple days. What's building momentum?

NOTABLE LINKS
The best 3-5 links from the entire week — only the ones that matter."""


# ── Discord Export ──
def timestamp_to_snowflake(dt):
    ms = int(dt.timestamp() * 1000)
    return (ms - DISCORD_EPOCH) << 22


def fetch_page(channel_id, after_id):
    url = (f"https://discord.com/api/v9/channels/{channel_id}"
           f"/messages?limit=100&after={after_id}")
    headers = {
        "Authorization": DISCORD_TOKEN,
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 Chrome/144.0.0.0 Safari/537.36",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def export_messages(channel_id):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS)
    after_id = timestamp_to_snowflake(cutoff)
    all_msgs = []
    page = 0

    print(f"  Fetching since {cutoff.strftime('%Y-%m-%d %H:%M UTC')}...")
    while True:
        msgs = fetch_page(channel_id, after_id)
        if not msgs:
            break
        msgs.sort(key=lambda m: int(m["id"]))
        all_msgs.extend(msgs)
        after_id = max(int(m["id"]) for m in msgs)
        page += 1
        print(f"    Page {page}: {len(all_msgs)} messages")
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


# ── Gemini Flash ──
def call_gemini(prompt_text):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}")
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


# ── GitHub Issues ──
def post_issue(subject, body, labels):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return
    payload = {"title": subject, "body": body, "labels": labels}
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
    print(f"  Posted: {result['html_url']}")


def fetch_recent_issues(label, days=7):
    """Fetch issues with a given label from the last N days."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"https://api.github.com/repos/{GITHUB_REPO}/issues"
           f"?labels={label}&state=all&since={since}&per_page=30&sort=created&direction=asc")
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ── Markdown to HTML ──
def md_to_html(text):
    lines = text.split("\n")
    html_lines = []
    in_list = False
    for line in lines:
        stripped = line.strip()
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
        elif stripped.startswith("* ") or stripped.startswith("- "):
            if not in_list:
                html_lines.append('<ul style="padding-left:20px">')
                in_list = True
            content = stripped[2:]
            content = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', content)
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
def send_email(subject, body, from_name="Discord Digest"):
    if not RESEND_API_KEY:
        return
    html = md_to_html(body)
    payload = {
        "from": f"{from_name} <onboarding@resend.dev>",
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
            "User-Agent": "DiscordDigest/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            json.loads(resp.read())
        print(f"  Email sent to {EMAIL_TO}")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        print(f"  Resend failed: {e.code} {err_body}")
    except Exception as e:
        print(f"  Resend failed: {e}")


# ── Daily extraction (runs for all channels) ──
def run_daily():
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    mode = os.environ.get("DIGEST_CHANNELS", "all")  # "all", "daily", or specific key

    for key, cfg in CHANNELS.items():
        if mode == "daily" and cfg["cadence"] != "daily":
            continue
        if mode not in ("all", "daily") and mode != key:
            continue

        print(f"\n{'='*50}")
        print(f"{cfg['name']}")
        print(f"{'='*50}")

        messages = export_messages(cfg["channel_id"])
        if not messages:
            print(f"  No messages. Skipping.")
            continue

        text = messages_to_text(messages)
        print(f"  {len(messages)} messages, {len(text)} chars")

        print(f"  Calling Gemini Flash...")
        prompt_text = cfg["prompt"].format(
            messages=text, date_str=date_str, msg_count=len(messages)
        )
        analysis = call_gemini(prompt_text)
        print(f"  Analysis complete.")

        # Post as GitHub issue with channel-specific label
        subject = f"{cfg['email_subject']} — {date_str} ({len(messages)} msgs)"
        post_issue(subject, analysis, ["digest", cfg["label"]])

        # Only email daily channels immediately
        if cfg["cadence"] == "daily":
            send_email(subject, analysis, cfg["email_subject"])

        time.sleep(2)  # be nice between channels


# ── Weekly rollup (runs for weekly channels) ──
def run_weekly():
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for key, cfg in CHANNELS.items():
        if cfg["cadence"] != "weekly":
            continue

        print(f"\n{'='*50}")
        print(f"WEEKLY ROLLUP: {cfg['name']}")
        print(f"{'='*50}")

        # Fetch last 7 daily digests from GitHub issues
        issues = fetch_recent_issues(cfg["label"], days=7)
        if not issues:
            print(f"  No daily digests found. Skipping.")
            continue

        # Build digest text from issue bodies
        digests = []
        for issue in issues:
            # Skip weekly rollup issues
            if "weekly" in issue.get("title", "").lower():
                continue
            digests.append(f"--- {issue['title']} ---\n{issue['body']}")

        if not digests:
            print(f"  No daily digests to roll up. Skipping.")
            continue

        combined = "\n\n".join(digests)
        print(f"  {len(digests)} daily digests, {len(combined)} chars")

        print(f"  Calling Gemini Flash for rollup...")
        prompt_text = WEEKLY_ROLLUP_PROMPT.format(digests=combined)
        rollup = call_gemini(prompt_text)
        print(f"  Rollup complete.")

        subject = f"{cfg['email_subject']} — Week of {date_str} ({len(digests)} days)"
        post_issue(subject, rollup, ["digest", cfg["label"], "weekly"])
        send_email(subject, rollup, cfg["email_subject"])

        time.sleep(2)


# ── Main ──
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if mode == "weekly":
        run_weekly()
    else:
        run_daily()


if __name__ == "__main__":
    main()
