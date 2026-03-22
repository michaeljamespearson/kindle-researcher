#!/usr/bin/env python3
"""
Daily Kindle Researcher
-----------------------
Reads topics from a Google Sheet, researches them via Claude API + web search,
generates a Kindle-friendly PDF, and emails it to your Kindle device.
"""

import os
import sys
import json
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText

import anthropic
import gspread
from google.oauth2.service_account import Credentials
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether
)
from reportlab.lib.colors import HexColor


# ── Config from environment ──────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GOOGLE_SHEETS_CREDS_JSON = os.environ["GOOGLE_SHEETS_CREDS_JSON"]
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
KINDLE_EMAIL = os.environ["KINDLE_EMAIL"]
SENDER_EMAIL = os.environ["SENDER_EMAIL"]
SENDER_PASSWORD = os.environ["SENDER_PASSWORD"]  # Gmail App Password
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))


# ── Google Sheets ────────────────────────────────────────────────────────────

def get_sheet():
    """Connect to the Google Sheet and return the first worksheet."""
    creds_dict = json.loads(GOOGLE_SHEETS_CREDS_JSON)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(SPREADSHEET_ID).sheet1


def get_next_topic(sheet):
    """Find the first row where Status is empty. Returns (row_index, topic, notes)."""
    records = sheet.get_all_records()
    for i, row in enumerate(records):
        if not row.get("Status", "").strip():
            return (i + 2, row["Topic"], row.get("Notes", ""))  # +2: header + 0-index
    return None


def mark_done(sheet, row_index, pdf_date):
    """Mark a topic row as completed."""
    sheet.update_cell(row_index, 3, "Done")           # Column C: Status
    sheet.update_cell(row_index, 4, pdf_date)          # Column D: Date Completed


# ── Claude Research ──────────────────────────────────────────────────────────

RESEARCH_SYSTEM_PROMPT = """You are a technical research writer producing Kindle-readable deep dives.

Your audience: a software engineer with experience in AI/ML, security, and distributed systems.

OUTPUT FORMAT — respond with valid JSON only, no markdown fences:
{
  "title": "Article title",
  "subtitle": "One-line subtitle",
  "sections": [
    {
      "heading": "Section Heading",
      "body": "Paragraph text. Use <b>bold</b> and <i>italic</i> for emphasis. Multiple paragraphs separated by \\n\\n."
    }
  ],
  "key_takeaways": ["takeaway 1", "takeaway 2", "takeaway 3"],
  "further_reading": ["resource 1", "resource 2"]
}

REQUIREMENTS:
- Target 2,000–2,500 words total body text (roughly a 15-minute technical read).
- 5–7 sections covering: conceptual foundation, how it works technically, 
  current state of the art, practical applications, limitations/open problems, 
  and where things are headed.
- Write at a technical depth appropriate for someone who can read papers but 
  wants an efficient synthesis, not a textbook chapter.
- Use concrete examples, real system names, and specific numbers where possible.
- Be opinionated — flag what matters and what's overhyped.
- Do NOT include any markdown formatting. Only use <b> and <i> HTML tags for emphasis.
"""


def research_topic(topic, notes=""):
    """Call Claude with web search to research a topic and return structured JSON."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_prompt = f"Research this topic in depth: {topic}"
    if notes:
        user_prompt += f"\n\nAdditional context/angle: {notes}"

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=RESEARCH_SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Extract text from response (may have multiple content blocks due to tool use)
    text_parts = [block.text for block in response.content if block.type == "text"]
    raw_text = "\n".join(text_parts).strip()

    # Clean potential markdown fences
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]
    if raw_text.endswith("```"):
        raw_text = raw_text.rsplit("```", 1)[0]
    raw_text = raw_text.strip()

    return json.loads(raw_text)


# ── PDF Generation ───────────────────────────────────────────────────────────

def build_kindle_pdf(research: dict, output_path: str):
    """
    Generate a Kindle-friendly PDF from structured research.
    Uses A5 page size (close to Kindle screen ratio), serif font, generous margins.
    """
    page_w, page_h = A5
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A5,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    # Custom styles optimized for e-ink reading
    title_style = ParagraphStyle(
        "KindleTitle",
        parent=styles["Title"],
        fontName="Times-Bold",
        fontSize=20,
        leading=24,
        spaceAfter=6,
        alignment=TA_CENTER,
    )
    subtitle_style = ParagraphStyle(
        "KindleSubtitle",
        parent=styles["Normal"],
        fontName="Times-Italic",
        fontSize=11,
        leading=14,
        spaceAfter=20,
        alignment=TA_CENTER,
        textColor=HexColor("#555555"),
    )
    heading_style = ParagraphStyle(
        "KindleHeading",
        parent=styles["Heading2"],
        fontName="Times-Bold",
        fontSize=13,
        leading=16,
        spaceBefore=16,
        spaceAfter=8,
        textColor=HexColor("#1a1a1a"),
    )
    body_style = ParagraphStyle(
        "KindleBody",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=15,
        spaceAfter=8,
        alignment=TA_JUSTIFY,
    )
    takeaway_style = ParagraphStyle(
        "KindleTakeaway",
        parent=body_style,
        leftIndent=12,
        bulletIndent=0,
        spaceAfter=4,
    )
    footer_style = ParagraphStyle(
        "KindleFooter",
        parent=styles["Normal"],
        fontName="Times-Italic",
        fontSize=9,
        leading=12,
        textColor=HexColor("#888888"),
    )
    date_style = ParagraphStyle(
        "KindleDate",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=HexColor("#999999"),
        spaceAfter=12,
    )

    story = []

    # Title page
    story.append(Spacer(1, 30))
    story.append(Paragraph(research["title"], title_style))
    story.append(Paragraph(research.get("subtitle", ""), subtitle_style))
    today = datetime.date.today().strftime("%B %d, %Y")
    story.append(Paragraph(f"Researched on {today}", date_style))
    story.append(Spacer(1, 10))

    # Sections
    for section in research["sections"]:
        story.append(Paragraph(section["heading"], heading_style))
        paragraphs = section["body"].split("\n\n")
        for para in paragraphs:
            para = para.strip()
            if para:
                story.append(Paragraph(para, body_style))

    # Key Takeaways
    story.append(Spacer(1, 12))
    story.append(Paragraph("Key Takeaways", heading_style))
    for i, point in enumerate(research.get("key_takeaways", []), 1):
        story.append(Paragraph(f"{i}. {point}", takeaway_style))

    # Further Reading
    if research.get("further_reading"):
        story.append(Spacer(1, 12))
        story.append(Paragraph("Further Reading", heading_style))
        for item in research["further_reading"]:
            story.append(Paragraph(f"\u2022 {item}", takeaway_style))

    # Footer
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Generated by Daily Kindle Researcher \u2022 Claude + Web Search",
        footer_style,
    ))

    doc.build(story)
    print(f"PDF generated: {output_path}")


# ── Kindle Delivery ──────────────────────────────────────────────────────────

def send_to_kindle(pdf_path: str, subject: str):
    """Email the PDF to a Kindle device via Send-to-Kindle."""
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = KINDLE_EMAIL
    msg["Subject"] = subject  # Kindle uses subject as document title

    msg.attach(MIMEText("Your daily research article is attached.", "plain"))

    with open(pdf_path, "rb") as f:
        attachment = MIMEApplication(f.read(), _subtype="pdf")
        filename = os.path.basename(pdf_path)
        attachment.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(attachment)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)

    print(f"Sent to Kindle: {KINDLE_EMAIL}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=== Daily Kindle Researcher ===")

    # 1. Get next topic
    sheet = get_sheet()
    result = get_next_topic(sheet)
    if not result:
        print("No pending topics found. Add more to your spreadsheet!")
        sys.exit(0)

    row_index, topic, notes = result
    print(f"Topic: {topic} (row {row_index})")

    # 2. Research it
    print("Researching...")
    research = research_topic(topic, notes)
    print(f"Article: {research['title']} ({len(research['sections'])} sections)")

    # 3. Generate PDF
    safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)
    safe_name = safe_name.strip().replace(" ", "_")[:60]
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    pdf_path = f"/tmp/{today_str}_{safe_name}.pdf"
    build_kindle_pdf(research, pdf_path)

    # 4. Send to Kindle
    send_to_kindle(pdf_path, research["title"])

    # 5. Mark done
    mark_done(sheet, row_index, today_str)
    print(f"Marked row {row_index} as done.")
    print("=== Complete ===")


if __name__ == "__main__":
    main()
