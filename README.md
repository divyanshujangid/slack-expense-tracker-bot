
# 🚀 Slack Expense Tracker Bot

> *Track your expenses directly from Slack — log them with a simple message, and they magically appear in your Google Sheet, with optional invoice uploads!*

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)  
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)  
[![Deploy to Railway](https://img.shields.io/badge/Deploy-Railway-00BFFF?logo=railway)](https://railway.app)  

---

## ✨ Features

✅ Log expenses by posting **`amount - description`** in Slack — automatically added to Google Sheets  
✅ Supports **multiple expenses** in a single message (one per line)  
✅ Attach an **invoice image or PDF** — uploaded to Google Drive & linked in your Sheet  
✅ Built with **Python (Flask)** — cloud-ready (Railway/Render/Fly.io)  
✅ All configuration via **environment variables** — no sensitive files in repo  
✅ Fully automated — just send a message, and watch the magic happen ✨  

---

## 🛠️ Setup

### 🔗 1. Google Service Account & Google Drive
- Create a Google Service Account ([Google Guide 📄](https://developers.google.com/workspace/guides/create-credentials))
- Download the service account JSON and **base64 encode it**:
  ```bash
  cat credentials.json | base64
  ```
- Share your target Google Sheet & Drive folder with the service account’s email as **Editor**
- Note down:
  - 📄 **Google Sheet ID**
  - 📁 **Drive Folder ID**

---

### ⚙️ 2. Environment Variables
- Clone this repo:
  ```bash
  git clone https://github.com/your-username/slack-expense-tracker-bot
  cd slack-expense-tracker-bot
  ```
- Set these environment variables in Railway/Render/Fly.io (or `.env`):
  ```env
  GOOGLE_CREDS_B64=...          # base64-encoded Google credentials
  SPREADSHEET_ID=...            # Google Sheet ID
  SHARED_DRIVE_ID=...           # Google Drive Folder or Shared Drive ID
  SLACK_BOT_TOKEN=...           # Slack bot token
  INVOICE_FOLDER_ID=...         # (Optional) Folder for invoices
  ```
- Install Python dependencies:
  ```bash
  pip install -r requirements.txt
  ```

---

### 💬 3. Slack Setup
- Create a Slack App → Add Bot Scopes:
  ```
  channels:history
  chat:write
  ```
- Subscribe to bot events:
  ```
  message.channels
  ```
- Set the **Event Subscription URL**:
  ```
  https://your-app.up.railway.app/slack/events
  ```
- Invite the bot to your desired Slack channel 🎉

---

### 🚀 4. Deploy
- Deploy easily on:
  - [Railway](https://railway.app)
  - [Render](https://render.com)
  - [Fly.io](https://fly.io)
- Add the environment variables in the deployment dashboard.
- Railway automatically picks up the `Procfile` if present.

---

## 📝 Usage

> Example Slack messages:
```
299 - lunch  
1200 - client dinner
```

- Optionally attach an image/PDF of your receipt.
- Every expense (with or without invoice) is logged in Google Sheets with a Drive link.

---

## 🔒 Security
⚠️ **Never commit credentials or token files.**  
All secrets are handled via environment variables for your safety.  

---

## 🚧 Want more features?
✅ Open an issue  
✅ Submit a PR  
✅ Help improve this project!  

---

# 📁 slack-expense-tracker-bot

> Happy expense tracking! 💸
