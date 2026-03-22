# Daily Kindle Researcher

A GitHub Actions pipeline that reads topics from a Google Sheet, researches them using Claude + web search, generates a Kindle-optimized PDF, and emails it to your Kindle — every weekday morning before your commute.

## Architecture

```
Google Sheet (topics) → GitHub Actions (cron) → Claude API (research + web search) → ReportLab (PDF) → SMTP (email) → Kindle
```

## Your Google Sheet Structure

Create a new Google Sheet with these exact column headers in row 1:

| Topic | Notes | Status | Date Completed |
|-------|-------|--------|----------------|
| CRDT algorithms | Focus on Yjs and Automerge implementations | | |
| eBPF for observability | How Cilium and Pixie use it in production | | |
| Homomorphic encryption | Current performance bottlenecks vs FHE theory | | |
| Speculative decoding in LLMs | | | |
| io_uring vs epoll | Real benchmark data, not just theory | | |

**Columns:**
- **Topic** (A): What to research. Be specific — "CRDT algorithms" is better than "distributed systems".
- **Notes** (B): Optional. Angle, focus areas, or context to steer the research.
- **Status** (C): Leave blank. The script fills in "Done" after delivery.
- **Date Completed** (D): Leave blank. Auto-filled with the delivery date.

The script processes the first row with an empty Status, top to bottom.

## Setup Guide

### 1. Google Cloud Service Account

You need a service account so the script can read/write your Google Sheet.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable the **Google Sheets API** and **Google Drive API**
4. Go to **IAM & Admin → Service Accounts → Create Service Account**
5. Name it something like `kindle-researcher`
6. Click **Create Key → JSON** — download the file
7. Open your Google Sheet → click **Share** → paste the service account email (looks like `kindle-researcher@project-id.iam.gserviceaccount.com`) → give it **Editor** access

The JSON file contents become your `GOOGLE_SHEETS_CREDS_JSON` secret.

### 2. Kindle Send-to-Email Setup

1. Go to [Amazon Manage Your Content and Devices](https://www.amazon.com/hz/mycd/myx#/home/settings/payment)
2. Go to **Preferences → Personal Document Settings**
3. Find your Kindle's email address (e.g., `yourname_abc@kindle.com`) — this is your `KINDLE_EMAIL`
4. Under **Approved Personal Document E-mail List**, add the Gmail address you'll send from

### 3. Gmail App Password

You need an App Password (not your regular Gmail password):

1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** if not already on
3. Go to [App Passwords](https://myaccount.google.com/apppasswords)
4. Create one for "Mail" → copy the 16-character password

This becomes your `SENDER_PASSWORD` secret.

### 4. Anthropic API Key

1. Go to [Anthropic Console](https://console.anthropic.com/)
2. Create an API key
3. This becomes your `ANTHROPIC_API_KEY` secret

### 5. GitHub Repository Setup

1. Create a new GitHub repo
2. Push this project to it
3. Go to **Settings → Secrets and variables → Actions**
4. Add these **Repository Secrets**:

| Secret Name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `GOOGLE_SHEETS_CREDS_JSON` | The entire JSON contents of your service account key file |
| `SPREADSHEET_ID` | The ID from your Google Sheet URL: `https://docs.google.com/spreadsheets/d/{THIS_PART}/edit` |
| `KINDLE_EMAIL` | Your Kindle's email, e.g. `yourname@kindle.com` |
| `SENDER_EMAIL` | Your Gmail address |
| `SENDER_PASSWORD` | Your Gmail App Password |

### 6. Test It

Go to **Actions → Daily Kindle Research → Run workflow** to trigger manually.

Check the action logs, then check your Kindle!

## Adjusting the Schedule

Edit `.github/workflows/daily-research.yml`:

```yaml
# Current: 6:00 AM ET weekdays
- cron: '0 11 * * 1-5'

# 7:30 AM ET weekdays
- cron: '30 12 * * 1-5'

# Every day including weekends
- cron: '0 11 * * *'
```

Note: GitHub Actions cron uses UTC. ET = UTC-4 (summer) / UTC-5 (winter).

## Customization

### Research Depth / Length

In `research_and_send.py`, edit the `RESEARCH_SYSTEM_PROMPT` string. The key line:

```
- Target 2,000–2,500 words total body text (roughly a 15-minute technical read).
```

Change to `3,000–3,500` for longer reads, or `1,000–1,500` for quicker ones.

### PDF Styling

The PDF uses A5 page size with Times Roman — optimized for Kindle screens. To adjust font size, margins, or layout, edit the style definitions in `build_kindle_pdf()`.

### Model Choice

The script uses `claude-sonnet-4-20250514` for a good balance of quality and cost (~$0.01–0.03 per article with web search). Switch to `claude-opus-4-20250514` in the `research_topic()` function for maximum depth.

## Cost Estimate

- **Claude API**: ~$0.01–0.05 per article (Sonnet + web search)
- **GitHub Actions**: Free tier gives 2,000 minutes/month; each run uses ~2–3 minutes
- **Total**: roughly $1–2/month for daily weekday delivery

## Troubleshooting

**"No pending topics found"**: All topics have a Status. Add more rows to your sheet.

**PDF not arriving on Kindle**: Check that your sender email is in Amazon's approved list. Also check your Kindle's email address is correct. PDFs can take a few minutes to sync.

**Claude returns invalid JSON**: The script will crash with a JSON parse error. This is rare but can happen with unusual topics. Re-run manually.

**Google Sheets auth error**: Make sure the service account email has Editor access to the sheet, and both the Sheets API and Drive API are enabled in your GCP project.
