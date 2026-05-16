# Gmail to LLM Exporter

Export Gmail emails matching any search query into JSON or plain-text files, ready to feed into an LLM context window.

---

## Project structure

```
gmail-llm/
├── gmail_export.py    ← main Python script
├── gmail_export.sh    ← shell wrapper (sources venv, runs the script)
├── credentials.json   ← OAuth2 credentials (download from Google Cloud Console)
├── token.json         ← saved auth token (auto-created on first run)
├── requirements.txt   ← Python dependencies
├── output/            ← all exported files land here
└── venv/              ← Python virtual environment
```

---

## Prerequisites

- **Python 3.8+**
- A **Google Cloud project** with the Gmail API enabled
- An **OAuth 2.0 Client ID** (Desktop app type) downloaded as `credentials.json`

### Google Cloud setup (one-time)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create or select a project
3. **APIs & Services → Library** → search *Gmail API* → Enable
4. **APIs & Services → Credentials** → Create Credentials → OAuth 2.0 Client ID → Desktop app
5. Download the JSON file and save it as `credentials.json` in the project folder

---

## Installation

```bash
# 1. Clone / navigate to the project folder
cd ~/venvs/gmail-llm

# 2. Create the virtual environment
python3 -m venv venv

# 3. Install dependencies
venv/bin/pip install -r requirements.txt

# 4. Make the shell script executable (only once)
chmod +x gmail_export.sh
```

> **First run:** the script opens a browser window to authenticate with your Google account.  
> A `token.json` file is saved automatically so you will not be asked again.

---

## Usage

### Via shell script (recommended)

```bash
./gmail_export.sh "GMAIL_QUERY" [options]
```

The shell script automatically activates the venv and writes output to `./output/`.

#### Examples

```bash
# Export up to 50 emails from inbox since 2024 (JSON, default)
./gmail_export.sh "label:inbox after:2024/01/01"

# Export emails from a specific sender, plain text, up to 200
./gmail_export.sh "from:boss@company.com" --max-results 200 --format txt

# Export invoice emails in both formats with a fixed filename
./gmail_export.sh "subject:invoice" --format both --output-file invoices_2024

# Use any Gmail search syntax
./gmail_export.sh "from:@binance.com has:attachment after:2024/06/01" -n 100 -f txt
```

### Via Python directly

```bash
source venv/bin/activate
python gmail_export.py "GMAIL_QUERY" [options]
```

---

## CLI reference

```
positional arguments:
  query                 Gmail search query (same syntax as the Gmail search bar)

options:
  -h, --help            show this help message and exit
  --max-results N, -n N
                        Maximum number of emails to fetch (default: 50)
  --format {json,txt,both}, -f {json,txt,both}
                        Output format: json, txt, or both (default: json)
  --output-dir DIR, -o DIR
                        Output directory (default: ./output relative to script)
  --output-file NAME    Base filename without extension
                        (default: auto-generated as emails_YYYYMMDD_HHMMSS)
```

---

## Output formats

| Format | Best for |
|--------|----------|
| `json` | Programmatic use — structured, one email per object |
| `txt`  | Pasting directly into an LLM context window |
| `both` | Generate both files in a single run |

Output files are always written to the `output/` subfolder.

---

## Gmail query syntax (quick reference)

| Filter | Example |
|--------|---------|
| From sender | `from:user@example.com` |
| To recipient | `to:me@example.com` |
| Subject | `subject:invoice` |
| Label | `label:inbox` |
| Date range | `after:2024/01/01 before:2024/12/31` |
| Has attachment | `has:attachment` |
| Combine filters | `from:boss@company.com subject:report after:2024/06/01` |

Full syntax: https://support.google.com/mail/answer/7190

---

## Tips for LLM use

- **JSON:** load one email at a time, pass to the LLM with a structured prompt
- **TXT:** paste the file content directly into the context window
- Keep `--max-results` at 10–20 for very large emails to avoid hitting token limits
- Use specific date ranges and senders to narrow down results

---

## Security notes

- `credentials.json` and `token.json` are listed in `.gitignore` — never commit them
- The script requests **read-only** access (`gmail.readonly` scope)
- Revoke access any time at [myaccount.google.com/permissions](https://myaccount.google.com/permissions)
