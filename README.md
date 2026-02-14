# Discord Alpha Digest

Automated intelligence pipeline that extracts "alpha" from Discord channels, analyzes it with Gemini Flash, and emails you a daily brief. Runs on GitHub Actions for ~$0.30/month.

## How It Works

```
Discord API → export last 24h of messages
           → Gemini 2.0 Flash analyzes for actionable signals
           → posts digest as GitHub Issue (archive)
           → emails you via Resend (inbox delivery)
```

Zero external Python dependencies — stdlib `urllib` + REST APIs only.

## Channels

| Channel | Server | Cadence | What It Covers |
|---------|--------|---------|----------------|
| **EleutherAI #off-topic** | EleutherAI | Daily + weekly rollup | ML tooling migrations, sentiment shifts on labs/models, papers being implemented, talent signals |
| **tinygrad #general** | tinygrad | Daily + weekly rollup | Kernel optimizations, GPU/TPU/hardware, tinygrad internals, geohot's community |
| **seats.aero #pro-chat** | seats.aero | Daily + weekly rollup | Award sweet spots, credit card moves, program changes, deals/mistake fares, booking strategies |

## Schedule

- **Daily at 2am CST** (8am UTC): Extracts all 3 channels, analyzes each, emails all 3 digests
- **Sunday at 3am CST** (9am UTC): Synthesizes each weekly channel's 7 daily digests into a rollup email

## Setup

### 1. GitHub Secrets

| Secret | What |
|--------|------|
| `DISCORD_TOKEN` | Your Discord user token (from browser network tab → `Authorization` header on any `/messages` request) |
| `GEMINI_API_KEY` | Google AI Studio API key (free tier works) |
| `RESEND_API_KEY` | Resend.com API key (free tier = 3000 emails/month) |

`GITHUB_TOKEN` is provided automatically by GitHub Actions.

### 2. Deploy

```bash
git clone https://github.com/jaisong123/eleuther-digest.git
cd eleuther-digest
# Add secrets in GitHub repo → Settings → Secrets and variables → Actions
# The workflow runs automatically on schedule, or trigger manually from Actions tab
```

### 3. Manual Trigger

From the Actions tab, select "Discord Alpha Digest" → Run workflow → choose `daily` or `weekly`.

## Architecture

### Daily Flow (`python digest.py daily`)

1. For each channel in `CHANNELS`:
   - Export last 24h of messages via Discord REST API (paginated, 100 msgs/page)
   - Format as `[timestamp] username: message` text
   - Send to Gemini 2.0 Flash with channel-specific analysis prompt
   - Post result as GitHub Issue with labels `["digest", "<channel>"]`
   - Email result via Resend

### Weekly Flow (`python digest.py weekly`)

1. For each channel with `cadence: "weekly"`:
   - Fetch last 7 daily digest issues from GitHub API (by label)
   - Concatenate all daily digests
   - Send to Gemini Flash with a rollup prompt that identifies **trends** across the week
   - Post as GitHub Issue with labels `["digest", "<channel>", "weekly"]`
   - Email result via Resend

### Key Design Decisions

- **Map-reduce for volume**: Daily extraction keeps each Gemini call under ~300K chars. Weekly rollup synthesizes 7 already-summarized digests (~10K chars total) — cheap and fast.
- **Discord snowflake IDs**: Timestamps are encoded in Discord message IDs as `(unix_ms - 1420070400000) << 22`. We convert a cutoff datetime to a snowflake to paginate with `?after=`.
- **Browser headers required**: Discord API returns 403 without a `User-Agent` header that looks like a real browser.
- **Gemini anti-repetition**: `frequencyPenalty: 1.5` + `presencePenalty: 0.5` + `maxOutputTokens: 1500` prevents the repetition loop that occurs with large inputs (~300K chars).
- **Resend quirks**: Free tier requires `from: onboarding@resend.dev`. Needs `User-Agent` header to bypass Cloudflare bot detection on GitHub Actions.
- **GitHub Issues as archive**: Every digest is stored as an issue, making them searchable and providing the data source for weekly rollups.

## Digest Format

Each digest follows a Minto Pyramid style:

- **TL;DR**: One bold sentence — the single most important signal
- **Section headers**: Channel-specific (e.g., TOOLING MOVES, AWARD SWEET SPOTS)
- **Every bullet**: `<b>Bold takeaway</b> — Evidence with a direct quote from the chat`

## Cost

| Service | Monthly Usage | Cost |
|---------|--------------|------|
| Gemini 2.0 Flash | ~75K tokens/day input, ~4.5K output | ~$0.30 |
| GitHub Actions | ~34 min/month (free tier = 2000 min) | $0 |
| Resend | ~100 emails/month (free tier = 3000) | $0 |
| **Total** | | **~$0.30/month** |

## Adding a New Channel

Add an entry to the `CHANNELS` dict in `digest.py`:

```python
"my-channel": {
    "name": "Server #channel",
    "guild_id": "...",        # Server ID (Discord developer mode → right-click server)
    "channel_id": "...",      # Channel ID (right-click channel → Copy Channel ID)
    "cadence": "daily",       # "daily" or "weekly"
    "label": "my-channel",    # GitHub issue label
    "email_subject": "My Channel Digest",
    "prompt": """...""",       # Must include {messages}, {date_str}, {msg_count} placeholders
},
```

To get IDs: Discord Settings → Advanced → turn on Developer Mode. Then right-click any server or channel to copy its ID.

## Files

| File | Purpose |
|------|---------|
| `digest.py` | Main script — all extraction, analysis, and delivery logic |
| `backfill.py` | One-off script to backfill the last 7 days of a single channel |
| `.github/workflows/daily-digest.yml` | GitHub Actions workflow (daily + weekly cron) |
