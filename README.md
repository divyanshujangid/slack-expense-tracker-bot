# Slack Expense Tracker Bot

This bot lets you log expenses in a Slack channel using simple messages like `299 - lunch` and automatically appends them to a Google Sheet.

## Features

- Post `amount - description` in Slack and have it instantly logged to Google Sheets.
- Supports multiple expenses in a single message (one per line).
- Built in Python (Flask), ready for cloud deployment (Railway/Render/Fly.io).
- No manual work once deployed—just message, and your Google Sheet updates in real-time!

## Setup

### 1. Google Service Account & Sheet

- Create a Google Service Account and download `credentials.json` (follow [Google’s guide](https://developers.google.com/workspace/guides/create-credentials)).
- Share your target Google Sheet with the service account’s email as **Editor**.
- Copy your Google Sheet ID.

### 2. Environment

- Clone this repo.
- Place your `credentials.json` in the root folder (never commit this file).
- Install requirements:

pip install -r requirements.txt


### 3. Slack Setup

- Create a Slack app, add the following Bot Scopes:
- `channels:history`
- `chat:write`
- Subscribe to bot events:
- `message.channels`
- Set the Event Subscription URL to:  

https://your-app.up.railway.app/slack/events

- Invite the bot to your channel.

### 4. Deploy

- Deploy on [Railway](https://railway.app), [Render](https://render.com), or [Fly.io](https://fly.io).
- Set up your repo to deploy, Railway will use the `Procfile` automatically.

## Usage

1. Post messages in Slack in this format:

299 - lunch
1200 - client dinner

2. Each line logs as a row in your Google Sheet!

## Security

- Keep your `credentials.json` secret and **never** commit it to Git.

---

## Want more features (like invoice file uploads)? Open an issue or contribute!

# slack-expense-tracker-bot
