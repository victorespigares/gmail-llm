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

### 3. Place credentials

Download `credentials.json` from Google Cloud Console and put it in `~/venvs/gmail-llm/`.

### 4. Make the shell script executable

```bash
chmod +x gmail_export.sh
```

### 5. Run

```bash
./gmail_export.sh "label:inbox after:2024/01/01"
```

The browser will open for Google authentication on the first run.  
A `token.json` file is saved automatically — no re-authentication needed afterwards.

---

## Deactivating the environment (if using Python directly)

```bash
deactivate
```
