#!/usr/bin/env python3
"""
Gmail to LLM Exporter
Exports emails matching a Gmail search query with full body content.

Usage:
    python gmail_export.py "label:inbox after:2024/01/01" [options]

Run with --help for full CLI reference.
"""

import os
import json
import subprocess
import base64
import re
import html
import argparse
from datetime import datetime
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Gmail allows 6,000 quota units per user per minute and threads.get costs 40,
# so long exports hit 403 rateLimitExceeded. googleapiclient retries those (and
# 429/5xx) with randomized exponential backoff of up to 2**n seconds per retry;
# 7 retries waits up to ~4 min in total, well past the one-minute quota window.
API_RETRIES = 7

# Credentials live in 1Password, not on disk. Override the item with GMAIL_OP_ITEM.
OP_ITEM = os.environ.get('GMAIL_OP_ITEM', 'op://Private/Gmail LLM')
OP_VAULT, OP_TITLE = OP_ITEM[len('op://'):].split('/', 1)
CREDENTIALS_FIELD = 'credentials_json'
TOKEN_FIELD = 'token_json'


def op_read(field):
    """Read a field from the 1Password item. Returns None if unset."""
    result = subprocess.run(
        ['op', 'read', f'op://{OP_VAULT}/{OP_TITLE}/{field}'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def op_write(field, value):
    """Write a field back to the 1Password item."""
    result = subprocess.run(
        ['op', 'item', 'edit', OP_TITLE, '--vault', OP_VAULT, f'{field}[password]={value}'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f'Failed to save {field} to {OP_ITEM}: {result.stderr.strip()}')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Export Gmail emails matching a search query for LLM use.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python gmail_export.py "label:inbox after:2024/01/01"
  python gmail_export.py "from:boss@company.com" --max-results 100 --format txt
  python gmail_export.py "subject:invoice" --format both --output-file invoices
        """
    )
    parser.add_argument(
        'query',
        help='Gmail search query (same syntax as the Gmail search bar)'
    )
    parser.add_argument(
        '--max-results', '-n',
        type=int,
        default=50,
        dest='max_results',
        metavar='N',
        help='Maximum number of emails to fetch (default: 50)'
    )
    parser.add_argument(
        '--threads', '-t',
        action='store_true',
        dest='threads',
        help='Export whole conversation threads (every message in each matching '
             'thread, including your replies), not just messages matching the query'
    )
    parser.add_argument(
        '--format', '-f',
        choices=['json', 'txt', 'both'],
        default='json',
        dest='output_format',
        help='Output format: json, txt, or both (default: json)'
    )
    parser.add_argument(
        '--output-dir', '-o',
        default=os.path.join(SCRIPT_DIR, 'output'),
        dest='output_dir',
        metavar='DIR',
        help='Output directory (default: ./output relative to script)'
    )
    parser.add_argument(
        '--output-file',
        default=None,
        dest='output_file',
        metavar='NAME',
        help='Base filename without extension (default: auto-generated from timestamp)'
    )
    return parser.parse_args()


def authenticate():
    """Authenticate with Gmail API using OAuth2, with credentials from 1Password."""
    creds = None

    stored_token = op_read(TOKEN_FIELD)
    if stored_token:
        creds = Credentials.from_authorized_user_info(json.loads(stored_token), SCOPES)

    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except RefreshError:
                # Refresh token revoked or expired (e.g. apps in "Testing"
                # publishing status expire refresh tokens after 7 days).
                # Discard the stale token and fall back to a fresh login.
                creds = None
                op_write(TOKEN_FIELD, '')

        if not refreshed:
            client_config = op_read(CREDENTIALS_FIELD)
            if not client_config:
                raise RuntimeError(
                    f"{CREDENTIALS_FIELD} not found in {OP_ITEM}\n"
                    "Download the OAuth client JSON from Google Cloud Console > APIs & "
                    "Services > Credentials, then store it with:\n"
                    f"  op item edit '{OP_TITLE}' --vault '{OP_VAULT}' "
                    f"'{CREDENTIALS_FIELD}[password]=<contents of credentials.json>'"
                )
            flow = InstalledAppFlow.from_client_config(json.loads(client_config), SCOPES)
            creds = flow.run_local_server(port=0)

        op_write(TOKEN_FIELD, creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def get_body(payload):
    """Extract plain text body from email payload (handles nested MIME parts)."""
    body = ''

    def _decode(data):
        return base64.urlsafe_b64decode(data + '==').decode('utf-8', errors='replace')

    def _html_to_text(html_content):
        """Basic HTML stripping for LLM readability."""
        text = re.sub(r'<br\s*/?>', '\n', html_content, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        text = html.unescape(text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _extract(part):
        nonlocal body
        mime = part.get('mimeType', '')
        data = part.get('body', {}).get('data', '')

        if mime == 'text/plain' and data:
            body = _decode(data)
            return True  # Prefer plain text, stop searching

        if mime == 'text/html' and data and not body:
            body = _html_to_text(_decode(data))

        for sub in part.get('parts', []):
            if _extract(sub):
                return True
        return False

    _extract(payload)
    return body.strip()


def get_header(headers, name):
    """Get a specific header value by name."""
    for h in headers:
        if h['name'].lower() == name.lower():
            return h['value']
    return ''


def parse_message(detail):
    """Turn a Gmail message resource into a flat email dict."""
    headers = detail['payload'].get('headers', [])
    body = get_body(detail['payload'])
    timestamp = int(detail.get('internalDate', 0)) / 1000
    date_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S') if timestamp else ''

    return {
        'id': detail.get('id', ''),
        'thread_id': detail.get('threadId', ''),
        'date': date_str,
        '_ts': timestamp,
        'from': get_header(headers, 'From'),
        'to': get_header(headers, 'To'),
        'subject': get_header(headers, 'Subject'),
        'labels': detail.get('labelIds', []),
        'snippet': detail.get('snippet', ''),
        'body': body,
    }


def fetch_emails(service, query, max_results):
    """Fetch emails matching the query with full content."""
    print(f"\n🔍 Query: {query}")
    print(f"📦 Max results: {max_results}\n")

    # Get list of matching message IDs
    results = service.users().messages().list(
        userId='me', q=query, maxResults=max_results
    ).execute(num_retries=API_RETRIES)

    messages = results.get('messages', [])
    if not messages:
        print("⚠️  No emails found for this query.")
        return []

    print(f"📬 Found {len(messages)} email(s). Fetching content...")

    emails = []
    for i, msg in enumerate(messages, 1):
        detail = service.users().messages().get(
            userId='me', id=msg['id'], format='full'
        ).execute(num_retries=API_RETRIES)

        email = parse_message(detail)
        emails.append(email)
        print(f"  ✅ [{i}/{len(messages)}] {email['subject'][:60] or '(No subject)'}")

    return emails


def fetch_threads(service, query, max_results):
    """Fetch every message in each thread matching the query (full conversations)."""
    print(f"\n🔍 Query: {query}  (whole threads)")
    print(f"📦 Max threads: {max_results}\n")

    # Gmail caps maxResults at 500 per page, so paginate until we hit the limit.
    threads = []
    page_token = None
    while len(threads) < max_results:
        results = service.users().threads().list(
            userId='me', q=query,
            maxResults=min(500, max_results - len(threads)),
            pageToken=page_token,
        ).execute(num_retries=API_RETRIES)
        threads.extend(results.get('threads', []))
        page_token = results.get('nextPageToken')
        if not page_token:
            break

    threads = threads[:max_results]
    if not threads:
        print("⚠️  No threads found for this query.")
        return []

    print(f"📬 Found {len(threads)} thread(s). Fetching full conversations...")

    emails = []
    for i, th in enumerate(threads, 1):
        detail = service.users().threads().get(
            userId='me', id=th['id'], format='full'
        ).execute(num_retries=API_RETRIES)

        msgs = [parse_message(m) for m in detail.get('messages', [])]
        msgs.sort(key=lambda e: e['_ts'])
        emails.extend(msgs)

        subject = next((m['subject'] for m in msgs if m['subject']), '(No subject)')
        print(f"  ✅ [{i}/{len(threads)}] {subject[:55]} — {len(msgs)} msg(s)")

    print(f"\n🧵 {len(threads)} threads → {len(emails)} total messages")
    return emails


def save_json(emails, output_file):
    """Save emails as JSON (structured, good for programmatic use)."""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(emails, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Saved {len(emails)} emails to {output_file} (JSON)")


def save_txt(emails, output_file, query):
    """Save emails as plain text (great for pasting directly into a LLM context)."""
    txt_file = output_file.replace('.json', '.txt')
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write(f"GMAIL EXPORT — Query: {query}\n")
        f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 70 + "\n\n")

        for i, email in enumerate(emails, 1):
            f.write(f"EMAIL {i} of {len(emails)}\n")
            f.write("-" * 70 + "\n")
            f.write(f"Date:    {email['date']}\n")
            f.write(f"From:    {email['from']}\n")
            f.write(f"To:      {email['to']}\n")
            f.write(f"Subject: {email['subject']}\n")
            f.write(f"Labels:  {', '.join(email['labels'])}\n")
            f.write("\nBODY:\n")
            f.write(email['body'] or "(No body content)\n")
            f.write("\n\n" + "=" * 70 + "\n\n")

    print(f"💾 Saved {len(emails)} emails to {txt_file} (Plain text)")
    return txt_file


def main():
    args = parse_args()

    print("📧 Gmail to LLM Exporter")
    print("=" * 40)

    # Resolve and create output directory
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Build output base path
    if args.output_file:
        base_name = args.output_file
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_name = f"emails_{timestamp}"

    json_path = os.path.join(output_dir, f"{base_name}.json")
    txt_path = os.path.join(output_dir, f"{base_name}.txt")

    service = authenticate()
    print("✅ Authentication successful!")

    if args.threads:
        emails = fetch_threads(service, args.query, args.max_results)
    else:
        emails = fetch_emails(service, args.query, args.max_results)
    if not emails:
        return

    # Drop internal sort key before serializing
    for e in emails:
        e.pop('_ts', None)

    output_files = []

    if args.output_format in ('json', 'both'):
        save_json(emails, json_path)
        output_files.append(json_path)

    if args.output_format in ('txt', 'both'):
        save_txt(emails, txt_path, args.query)
        output_files.append(txt_path)

    # Print summary
    print(f"\n📊 Summary:")
    print(f"   Emails exported : {len(emails)}")
    print(f"   Output directory: {output_dir}")
    for f in output_files:
        print(f"   Output file     : {os.path.basename(f)}")
    print(f"\n💡 Tips for LLM use:")
    print(f"   • JSON: feed programmatically, one email at a time")
    print(f"   • TXT:  paste directly into the LLM context window")
    print(f"   • For large exports, use --max-results 10-20 to stay within token limits")


if __name__ == '__main__':
    main()
