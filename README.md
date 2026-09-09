# 🎮 Epic Games Free Games Auto-Claimer

> Auto-claim Epic Games weekly free games — **device auth only, zero browser, zero captcha**.

🇨🇳 [中文版 README](README-zh-CN.md)

## ✨ Single Auth Method: **Device Code Authorization**

| Feature | Benefit |
|---------|---------|
| ⚡ **One-time authorization** | User logs in once in their browser → tool gets a permanent token |
| 🚫 **No hCaptcha** | Login happens on Epic's official OAuth page |
| 📦 **No Playwright/Chromium** | Pure HTTP API → container drops from ~1GB to ~150MB |
| 🛡️ **No server IP risk** | Browser login is from your IP, not the server |
| ♾️ **Never expires** | Token only revokes when you manually log out |

## 🚀 Quick Start

### 1. Run

```bash
docker run -d \
  --name epic-claimer \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  zz3656/epic-games-claimer:latest
```

### 2. Authorize

Open **http://localhost:8000** in browser:
1. Click "🎯 Epic 设备码登录" section
2. Click "🔑 Epic 设备码授权"
3. Copy `user_code`, click the link to Epic in your browser
4. Log in to your Epic account and authorize the device
5. Web UI will automatically save the token and start using it

After that, weekly auto-claim runs without any further action.

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
      - ./data:/app/data
    security_opt:
      - no-new-privileges:true
```

> 📌 **Multi-arch image**: supports `linux/amd64` and `linux/arm64` (Synology, QNAP, Unraid)

## 🔐 Privacy & Security

| Storage | Encryption | File |
|---------|------------|------|
| Device Auth Token | Fernet (AES-128-CBC) | `/app/data/device_auth.enc` (0600) |
| Master Key | Plain | `/app/data/.env` (0600) |

**Only stores the token — no password.**

## 🛠️ API

API docs at **http://localhost:8000/docs**.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/device-auth/request` | POST | Start Device Auth flow |
| `/api/device-auth/poll/{code}` | GET | Poll Device Auth status |
| `/api/device-auth/status` | GET | Check Device Auth status |
| `/api/device-auth/claim-now` | POST | Manual claim with token |
| `/api/claim/progress/{id}` | GET | Poll claim progress |
| `/api/device-auth` | DELETE | Revoke authorization |
| `/api/device-auth/test/*` | POST | Debug endpoints |
| `/api/auto-claim/toggle` | POST | Toggle auto-claim |
| `/api/history` | GET | Claim history |
| `/api/credentials/status` | GET | Auth status |

## 🐛 Troubleshooting

### Device Auth Fails

Web UI → "🛠 调试选项" → click test buttons — output shows actual error from Epic's API. Common issues:

- **All client_ids failed**: Epic rotated public OAuth clients. Check `app/epic_api.py` for new clients
- **Network blocked**: Container can't reach Epic API. Check firewall/proxy
- **Rate limited**: Too many requests. Wait 10 minutes

### Master Key Mismatch

```
ERROR Decryption failed: master key mismatch
```

Fix:
```bash
rm ./data/device_auth.enc
# Re-authorize via Web UI
```

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────┐
│  Web UI (Browser)                               │
│  • Device Auth section + Manual claim + Auto     │
│  • History + Debug panel                         │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│  FastAPI Backend (port 8000)                     │
│  • /api/device-auth/*   Auth endpoints           │
│  • /api/claim-now        Manual claim            │
│  • /api/auto-claim/toggle Scheduler toggle       │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│  Scheduler (every Thu 17:00)                     │
│  EpicAPIClient → pure HTTP API calls             │
└──────────────────────────────────────────────────┘
```

## 📚 Project Structure

```
epicgames/
├── app/
│   ├── main.py                # FastAPI entry
│   ├── epic_api.py            # 🎯 Pure HTTP API client
│   ├── api_device_auth.py     # Device Auth endpoints
│   ├── scheduler.py           # Scheduled weekly claim
│   ├── credential_store.py    # Fernet encryption
│   ├── storage.py             # Result persistence
│   ├── result.py              # Data models
│   ├── config.py              # Environment config
│   └── static/
│       ├── device_auth.js     # Frontend logic
│       └── style.css
├── scripts/
│   └── entrypoint.sh          # Container entry
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## ⚠️ Disclaimer

- For educational purposes only. Please comply with [Epic Games Terms of Service](https://www.epicgames.com/site/en-US/terms-of-service).
- The author is not responsible for any account bans or damages.

## 📝 License

MIT
