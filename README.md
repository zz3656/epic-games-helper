# 🎮 Epic Games Free Games Auto-Claimer

> Auto-claim free games from Epic Games Store weekly, powered by **Docker + Playwright** with a clean web UI and zero credential retention.

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🌐 **Web UI** | Open in browser, no CLI needed |
| 🔓 **One-time Claim** | Enter credentials manually each time; cleared after use |
| 🔁 **Auto-Claim** | Enter once, runs weekly automatically; Fernet (AES-128-CBC) encrypted storage |
| 🐳 **Zero-config Start** | `EPIC_MASTER_KEY` auto-generated on first run |
| ⏰ **Scheduler** | Configurable weekly schedule (default: Thursday 17:00 Beijing time) |
| 📊 **History** | Track past claim results (sanitized) |
| 🛡️ **Secure by Design** | Privileged containers blocked, resource limits, `0600` permission on encrypted files |
| 🖥️ **VNC Support** | Optional VNC for manual hCaptcha solving — accessible through the same port |

## 🚀 Quick Start

### 1. Pull & Run

```bash
docker compose up -d
```

> 💡 **No `.env` needed!** The container auto-generates `EPIC_MASTER_KEY` on first run and stores it in `./data/.env`.

Open in browser: **http://localhost:8000**

### 2. Save Credentials (One-time Setup)

In the Web UI under **"💾 Save Credentials (Encrypted)"**:
1. Enter your Epic Games email and password
2. Check "Enable weekly auto-claim after saving"
3. Click Save

After that, the service automatically logs in and claims free games every week (default: Thursday 17:00 Beijing time).

### 3. Manage Auto-Claim

- **Disable**: Web UI → toggle switch
- **Delete credentials**: Web UI → 🗑 "Delete Credentials" button
- **View history**: Web UI → history table

### 4. Docker Compose Configuration

**Basic (no VNC):**

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

**With VNC (for manual hCaptcha solving):**

```yaml
services:
  epic-claimer:
    image: zz3656/epic-games-claimer:latest
    container_name: epic-games-claimer
    restart: unless-stopped
    # Single port: both API and VNC share port 8000
    # VNC URL: http://server-ip:8000/vnc-viewer
    ports:
      - "8000:8000"
    environment:
      - TZ=Asia/Shanghai
      - SCHEDULE_DAY=thu
      - SCHEDULE_HOUR=17
      - HEADLESS=true
      - AUTO_CLAIM_ENABLED=true
      - ENABLE_VNC=true        # Enable VNC server
      # - VNC_PASSWORD=yourpw  # Optional: set VNC password
    volumes:
      - ./logs:/app/logs
      - ./screenshots:/app/screenshots
      - ./data:/app/data
    security_opt:
      - no-new-privileges:true
```

> 📌 **VNC Access**: Once `ENABLE_VNC=true` is set, open the VNC viewer at `http://your-host:8000/vnc-viewer` in a new browser tab. Click "Start Claim" in the main UI first — the Chrome window will appear during the claim task. Solve any hCaptcha manually in the VNC window.

## 🔐 Privacy & Security

### Data Flow

```
User Browser
   │ HTTPS (credentials in memory)
   ▼
FastAPI Process
   │
   │ Fernet.encrypt()  ←  EPIC_MASTER_KEY from .env
   ▼
/app/data/credentials.enc   ←  Ciphertext (0600 permissions)
   ▲
   │ Fernet.decrypt() (weekly scheduled trigger)
   │
   ▼
In-memory (during claim)
   │
   │ Cleared after claim
   ▼
Reference set to None → GC
```

### Encryption Details

- **Algorithm**: Fernet (**AES-128-CBC** + HMAC-SHA256)
- **File Permissions**: `0600` (root-only in container)
- **Key Source**: `EPIC_MASTER_KEY` in `.env` (never committed)

### Threat Model

| Scenario | Outcome |
|----------|---------|
| Attacker gets `credentials.enc` without key | 🔒 Cannot decrypt — safe |
| Attacker gets `credentials.enc` + key | ⚠️ Full credential leak |
| Attacher attaches to running container | Process in-memory plaintext (runtime only) |
| Log leak | Credentials never written to logs (sanitized) |

### ⚠️ Important

- **`EPIC_MASTER_KEY` is your only line of defense**. Protect it with a password manager, never share it in chats/issues/screenshots, and rotate periodically (changing the key requires re-saving credentials).
- If key leak is suspected: delete credentials → change key → change Epic password.
- **Recommend using a secondary Epic account**, not your main account.

## 📁 Project Structure

```
epicgames/
├── app/
│   ├── main.py                # FastAPI entry + API routes
│   ├── claimer.py             # Playwright claim core
│   ├── claimer_login.py       # Login logic
│   ├── claimer_login_form.py  # Form filling
│   ├── claimer_login_post.py  # POST submission
│   ├── claimer_browser.py     # Browser management
│   ├── claimer_games.py       # Game fetch & claim
│   ├── claimer_captcha.py     # Captcha detection
│   ├── scheduler.py           # APScheduler cron
│   ├── credential_store.py    # 🔒 Fernet encrypted store
│   ├── storage.py             # Result storage
│   ├── config.py              # Environment config
│   ├── api_vnc.py             # VNC status + screenshots API
│   ├── api_vnc_ws.py          # VNC WebSocket proxy
│   └── static/                # Frontend assets + noVNC
├── scripts/
│   ├── build-and-run.sh
│   └── entrypoint.sh          # 🐳 Entrypoint (auto-keygen, VNC setup)
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .env                       # Auto-generated, gitignored
├── requirements.txt
├── logs/                      # Claim logs
├── screenshots/               # Debug screenshots
└── data/                      # Encrypted credentials persistence
```

## ⚙️ Configuration

All configuration via environment variables. `EPIC_MASTER_KEY` is auto-generated on first run and stored in `./data/.env`.

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
| `ENABLE_VNC` | `false` | Start VNC server (for hCaptcha) |
| `VNC_PASSWORD` | *(empty)* | VNC password (empty = no auth) |

## 🛠️ API

API docs at **http://localhost:8000/docs**.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/claim` | POST | Immediate claim (plaintext creds) |
| `/api/claim/verification` | POST | Submit email verification code |
| `/api/credentials` | POST | Save encrypted credentials |
| `/api/credentials` | DELETE | Delete credentials |
| `/api/credentials/status` | GET | Check credential status |
| `/api/auto-claim/toggle` | POST | Toggle auto-claim |
| `/api/history` | GET | Claim history |
| `/api/vnc/status` | GET | VNC server status |
| `/vnc-viewer` | GET | Embedded VNC viewer page |
| `/vnc-ws` | WS | VNC WebSocket proxy |

## 🐛 Troubleshooting

### 1. Login Failed

Epic Games frequently updates their site or triggers CAPTCHA:
- Check `/app/screenshots/login_failed_*.png` for debug screenshots
- Review `docker compose logs -f`
- Set `HEADLESS=false` and enable VNC for manual troubleshooting

### 2. hCaptcha Verification

If Epic presents an hCaptcha during login, the Web UI will show a clear prompt:

1. **Wrong credentials** (🔑): Verify email and password
2. **hCaptcha required** (🧩): Manual solving needed
   - With VNC enabled: Click the blue **"🎯 Click to open noVNC"** button in the failure notification
   - A new tab opens the VNC viewer — manually solve the CAPTCHA in the Chrome window
   - The claim task will auto-resume (waits up to 120s)

Ensure `ENABLE_VNC=true` is set in your environment before starting.

### 3. VNC Shows Black Screen

- Verify `ENABLE_VNC=true` is set in your container environment
- Check container logs: `docker compose logs | grep VNC`
- You should see `ENABLE_VNC=true - starting VNC server...` and `VNC setup complete.`
- If not present, the VNC server was not started — add the environment variable and restart

### 4. Master Key Changed — Credentials Can't Be Decrypted

```
ERROR Decryption failed: master key mismatch
```

Fix: Delete old credentials → Web UI "Delete Credentials" → Re-save with same account.

### 5. Want to Customize the Master Key?

After first run, edit `./data/.env` to set `EPIC_MASTER_KEY`, then restart:
```bash
docker compose restart
```

## ⚠️ Disclaimer

- This project is for educational purposes only. Please comply with [Epic Games Terms of Service](https://www.epicgames.com/site/en-US/terms-of-service).
- Frequent automated actions may trigger account risk controls.
- The author is not responsible for any account bans, data loss, or other damages.

## 📝 License

MIT

## 🏗️ Architecture

```
┌──────────────┐     ┌────────────────┐     ┌──────────────────┐
│  User Browser │────▶│  FastAPI (:8000) │────▶│  Chromium (Playwright) │
└──────────────┘     │                │     └──────────────────┘
                     │  • REST API     │     ┌──────────────────┐
                     │  • Web UI       │────▶│  VNC Server (:5900)│
                     │  • VNC WS Proxy │────▶│  (Xvfb + x11vnc)  │
                     │  • noVNC page   │     └──────────────────┘
                     └────────────────┘
```

Single port architecture: all access (API, Web UI, VNC viewer) goes through port **8000**. No additional port mappings needed for VNC.
