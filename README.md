# 🎮 Epic Games Free Games Auto-Claimer

> Auto-claim Epic Games weekly free games — **zero browser, zero captcha**, with persistent device auth.

🇨🇳 [中文版 README](README-zh-CN.md)

## ✨ Two Ways to Authenticate

This project supports **two authentication modes** — pick whichever fits your needs:

### 🎯 Recommended: **Device Auth (Zero-Captcha)**

> Inspired by [claabs/epicgames-freegames-node](https://github.com/claabs/epicgames-freegames-node) — uses Epic's official OAuth device code flow.

| Feature | Benefit |
|---------|---------|
| ⚡ **One-time authorization** | User logs in once in their browser → tool gets a permanent device auth token |
| 🚫 **No hCaptcha** | Login happens on Epic's official OAuth page, no automation fingerprints |
| 📦 **No Playwright/Chromium** | Pure HTTP API calls → container drops from ~1GB to ~150MB |
| 🛡️ **No server IP risk** | Browser login is from your IP, not the server |
| ♾️ **Never expires** | Token only revokes when you manually log out |

### 🔐 Alternative: **Username/Password (Browser Automation)**

For users who can't use Device Auth or want quick testing. Uses Playwright with stealth anti-detection — but will encounter hCaptcha occasionally.

| Pros | Cons |
|------|------|
| Simple one-step login | May trigger hCaptcha (auto-resolved if possible) |
| Works behind any network | Requires Playwright + Chromium (~1GB container) |

## 🚀 Quick Start

### 1. Pull & Run

```bash
docker compose up -d
```

> 💡 **No `.env` needed!** The container auto-generates `EPIC_MASTER_KEY` on first run.

Open in browser: **http://localhost:8000**

### 2. Authenticate (Pick One)

**Option A — Device Auth (Recommended):**
1. Web UI → "🎯 Epic 设备码登录" section
2. Click "🔑 Epic 设备码授权"
3. Copy the `user_code`, click the link to Epic in your browser
4. Log in to your Epic account and authorize the device
5. Web UI will automatically save the token and start using it

**Option B — Username/Password:**
1. Web UI → "🔁 保存凭证 · 每周自动领取" section
2. Enter Epic email + password
3. Click "💾 保存凭证（加密）"

### 3. Wait for Auto-Claim

Default schedule: **Thursday 17:00 Beijing time** weekly. View history anytime.

## 🐳 Docker Compose

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
      - AUTO_CLAIM_ENABLED=true
    volumes:
      - ./logs:/app/logs
      - ./screenshots:/app/screenshots
      - ./data:/app/data
    security_opt:
      - no-new-privileges:true
```

> 📌 **Multi-arch image**: supports `linux/amd64` and `linux/arm64` (Synology, QNAP, etc.)

## 🔐 Privacy & Security

| Storage | Encryption | File |
|---------|------------|------|
| Device Auth Token | Fernet (AES-128-CBC) | `/app/data/device_auth.enc` (0600) |
| Username/Password | Fernet (AES-128-CBC) | `/app/data/credentials.enc` (0600) |
| Master Key | Plain | `/app/data/.env` (0600) |

**Device Auth mode** stores only `{account_id, device_id, secret, access_token, refresh_token}` — **no password**, no credentials needed for re-claim.

## 🛠️ API

API docs at **http://localhost:8000/docs**.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/claim` | POST | Manual claim (username/password) |
| `/api/device-auth/request` | POST | Start Device Auth flow |
| `/api/device-auth/poll/{code}` | GET | Poll Device Auth status |
| `/api/device-auth/status` | GET | Check Device Auth status |
| `/api/device-auth/test/free-games` | POST | Debug: test free games API |
| `/api/device-auth/test/request` | POST | Debug: test device code request |
| `/api/device-auth/test/claim` | POST | Debug: test claim flow with token |
| `/api/credentials` | POST/DELETE | Save/Delete username/password |
| `/api/auto-claim/toggle` | POST | Toggle auto-claim |
| `/api/history` | GET | Claim history |

## 🐛 Troubleshooting

### Device Auth Fails

Web UI → "🛠 调试选项" → "测试免费游戏 API" / "测试申请 device code" — the output shows the actual error from Epic's API. Common issues:

- **Client ID expired**: Epic rotates public client IDs. Update `EPIC_CLIENT_ID` in `app/epic_api.py`
- **Network blocked**: Container can't reach Epic API. Check firewall/proxy
- **Rate limited**: Too many requests. Wait 10 minutes

### Browser Mode (Username/Password) hCaptcha

If Epic presents hCaptcha:
1. Auto-click will be attempted (3 retries, 8s wait each)
2. If still not passed, container will wait 30 seconds for Epic's server to validate
3. If still failing, the error message shows specific guidance

### Master Key Mismatch

```
ERROR Decryption failed: master key mismatch
```

Fix: Web UI → "Delete Credentials" → Re-save.

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Web UI (Browser)                                        │
│  • Device Auth section + Debug panel                     │
│  • Username/Password section                             │
│  • Auto-claim toggle + History                           │
└──────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────┐
│  FastAPI Backend (port 8000)                             │
│  • /api/device-auth/*    Device Auth flow                │
│  • /api/claim             Manual claim                    │
│  • /api/credentials       Save/load encrypted creds       │
└──────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────┐
│  Scheduler (auto-selects)                                │
│                                                          │
│  Has Device Auth?                                        │
│    YES → EpicAPIClient (pure HTTP, zero captcha)         │
│    NO  → EpicClaimer (Playwright + stealth)              │
└──────────────────────────────────────────────────────────┘
```

## 📚 Project Structure

```
epicgames/
├── app/
│   ├── main.py                # FastAPI entry
│   ├── claimer.py             # Playwright claim core
│   ├── claimer_login.py       # Login logic + hCaptcha
│   ├── claimer_captcha.py     # hCaptcha auto-resolve
│   ├── claimer_games.py       # Game fetch + claim (browser)
│   ├── epic_api.py            # 🎯 Pure HTTP API client (device auth)
│   ├── api_device_auth.py     # Device Auth endpoints
│   ├── api_vnc.py             # VNC status (legacy, unused)
│   ├── credential_store.py    # Fernet encryption
│   ├── scheduler.py           # Auto-selects mode
│   └── ...
├── scripts/
│   └── entrypoint.sh
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## ⚠️ Disclaimer

- For educational purposes only. Please comply with [Epic Games Terms of Service](https://www.epicgames.com/site/en-US/terms-of-service).
- Frequent automated actions may trigger account risk controls.
- The author is not responsible for any account bans or damages.

## 📝 License

MIT
