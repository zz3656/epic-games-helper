# 🎮 Epic Games Free Games Auto-Claimer

> Auto-claim Epic Games weekly free games with **Docker + Playwright**, featuring a clean web UI and zero credential retention design.

🇨🇳 [中文版 README](README-zh-CN.md)

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🌐 **Web UI** | Open in browser — no CLI needed |
| 🔓 **One-time Claim** | Enter credentials manually each time; cleared after use |
| 🔁 **Auto-Claim** | Enter once, runs weekly automatically; Fernet (AES-128-CBC) encrypted storage |
| 🐳 **Zero-config Start** | `EPIC_MASTER_KEY` auto-generated on first run |
| ⏰ **Scheduler** | Configurable weekly schedule (default: Thursday 17:00 Beijing time) |
| 📊 **History** | Track past claim results (sanitized) |
| 🛡️ **Secure by Design** | No-new-privileges container, resource limits, `0600` on encrypted files |

## 🚀 Quick Start

### 1. Pull & Run

```bash
docker compose up -d
```

> 💡 **No `.env` needed!** The container auto-generates `EPIC_MASTER_KEY` on first run.

Open in browser: **http://localhost:8000**

### 2. Save Credentials (One-time Setup)

In the Web UI:
1. Enter your Epic Games email and password
2. Check "Enable weekly auto-claim"
3. Click Save

After that, the service automatically claims free games every week.

### 3. Docker Compose

```yaml
services:
  epic-claimer:
    image: zz3656/epic-games-claimer:latest
    container_name: epic-games-claimer
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - TZ=Asia/Shanghai
      - SCHEDULE_DAY=thu
      - SCHEDULE_HOUR=17
      - HEADLESS=true
      - AUTO_CLAIM_ENABLED=true
    volumes:
      - ./logs:/app/logs
      - ./screenshots:/app/screenshots
      - ./data:/app/data
    security_opt:
      - no-new-privileges:true
```

## 🔐 Privacy & Security

- **Fernet encryption** (AES-128-CBC + HMAC-SHA256) for stored credentials
- **0600 file permissions** — only container root can read
- **Zero credential retention** — passwords exist only in memory during claim, then garbage collected
- **Never logged** — credentials are never written to logs

## ⚙️ Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `EPIC_MASTER_KEY` | *auto-generated* | Fernet encryption key |
| `TZ` | `Asia/Shanghai` | Timezone |
| `SCHEDULE_DAY` | `thu` | Day to run (mon-sun) |
| `SCHEDULE_HOUR` | `17` | Hour (0-23) |
| `SCHEDULE_MINUTE` | `0` | Minute (0-59) |
| `HEADLESS` | `true` | Headless browser mode |
| `LOG_LEVEL` | `INFO` | Logging level |
| `AUTO_CLAIM_ENABLED` | `false` | Enable auto-claim on startup |

## 🛠️ API

API docs at **http://localhost:8000/docs**.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/claim` | POST | Immediate claim |
| `/api/claim/verification` | POST | Submit email verification code |
| `/api/credentials` | POST/DELETE | Save/Delete credentials |
| `/api/auto-claim/toggle` | POST | Toggle auto-claim |
| `/api/history` | GET | Claim history |

## 🐛 Troubleshooting

### hCaptcha Verification

If Epic presents an hCaptcha during login, the Web UI will show debug screenshots and clear instructions:

1. **Wrong credentials** — Verify email and password
2. **hCaptcha required** — Login to Epic in your personal browser once to "trust this device", then retry

### Master Key Mismatch

```
ERROR Decryption failed: master key mismatch
```

Fix: Delete credentials via Web UI → Re-save.

## ⚠️ Disclaimer

- For educational purposes only. Please comply with [Epic Games Terms of Service](https://www.epicgames.com/site/en-US/terms-of-service).
- Frequent automated actions may trigger account risk controls.
- The author is not responsible for any account bans or damages.

## 🏗️ Architecture

```
┌──────────────┐     ┌────────────────┐     ┌──────────────────┐
│  User Browser │────▶│  FastAPI (:8000) │────▶│  Chromium         │
│              │     │  • REST API    │     │  (Playwright)      │
│              │     │  • Web UI      │     └──────────────────┘
└──────────────┘     └────────────────┘
```

Single-port architecture — all access through port **8000**.
