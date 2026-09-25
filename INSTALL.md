# Installation guide

> For full usage documentation see [README.md](README.md).

## Steps

### 1. Create the folder and virtual environment

```bash
cd ~/venvs/gmail-llm
python3 -m venv venv
```

### 2. Install dependencies

```bash
venv/bin/pip install -r requirements.txt
```

### 3. Store credentials in 1Password

Download the OAuth client JSON from Google Cloud Console, then store it in the
`Gmail LLM` item (vault `Private`) instead of leaving it on disk:

```bash
op item create --category="API Credential" --title="Gmail LLM" --vault=Private \
    "credentials_json[password]=$(cat /path/to/downloaded.json)"
```

Override the item with `GMAIL_OP_ITEM=op://<vault>/<item>` if you use another one.

### 4. Make the shell script executable

```bash
chmod +x gmail_export.sh
```

### 5. Run

```bash
./gmail_export.sh "label:inbox after:2024/01/01"
```

The browser will open for Google authentication on the first run.  
The resulting token is written back to the `token_json` field of the same
1Password item — no re-authentication needed afterwards, and nothing on disk.

---

## Deactivating the environment (if using Python directly)

```bash
deactivate
```
