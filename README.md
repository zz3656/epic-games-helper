# 🎮 Epic Games Free Games Helper

> Weekly free-game tracker & one-click checkout helper for Epic Games.
> Track what's free, what's already in your library, and jump straight to the claim page.

🇨🇳 [中文说明](README-zh-CN.md)

---

## 📌 What is this?

`epic-games-helper` is a lightweight HTTP API + Web UI that:

- 📡 **Tracks** Epic's weekly free games (every Thursday refresh)
- 🗂️ **Cross-references** with your Epic library (already-owned detection)
- 🎯 **Generates** a one-click checkout URL per game
- ⏰ **Schedules** notifications for weekly drops

> **Important:** Epic Games' purchase endpoints **cannot** be fully automated without a
> browser session (cookies, XSRF, hCaptcha). This tool therefore **cannot directly claim
> games for you** — but it does everything it can *around* that, so claiming is **one click**.

See [Roadmap](#-roadmap) for what's done and what's planned.

---

## ✨ Features

### ✅ Already implemented

- 🔑 **Epic Device Code OAuth** — log in once in your own browser, get a permanent token (no password storage, no hCaptcha)
- 🗓️ **Weekly free-games list** — auto-fetched from Epic's public catalog API (`freeGamesPromotions`)
- 📚 **Library cross-check** — uses Epic's `library-service` API to mark games you already own
- 🖼️ **Rich game cards** — cover image, title, original price, free-window dates, "end in N days" badge
- 🎯 **One-click checkout URL** — generated per game; click opens the Epic purchase page with the offer pre-filled
- ⏰ **Scheduled checks** — APScheduler weekly trigger (configurable day/hour)
- 🔌 **REST API** — `/docs` Swagger UI out of the box
- 🛡️ **Fernet-encrypted token storage** (AES-128-CBC + HMAC) with `0600` file permissions
- 🐳 **Multi-arch Docker image** (`linux/amd64` + `linux/arm64`)

### 🚧 Roadmap — what we are working toward

- 🎮 **True automatic claim** — investigate alternative paths (TrustedServer policy, GQL mutations, or browser fallback) to actually POST `/store/purchase` end-to-end
- 👥 **Multi-account support** — currently single-slot credential store; redesign for N accounts
- 🪟 **Built-in browser fallback** — embedded headless Chromium path as last resort if API paths are blocked
- 📲 **Push notifications** — push the new weekly drop to your phone (Telegram/email/webhook) the moment it goes live
- 🌍 **Per-region support** — locale-aware (currently hard-coded `zh-CN/CN`)

---

## 🚀 Quick Start

### 1. Run

```bash
docker run -d \
  --name epic-helper \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  zz3656/epic-games-helper:latest
```

### 2. Authorize

Open **http://localhost:8000**:

1. Click **"🔑 Epic 设备码授权"** (or "Epic Device Code Authorization")
2. Copy the `user_code`, click the Epic link that opens
3. Log into your Epic account in your own browser and approve the device
4. The Web UI auto-detects success and saves the token

That's it. Future weekly drops will be tracked automatically.

---

## 🐳 Docker Compose

```yaml
services:
  epic-helper:
    image: zz3656/epic-games-helper:latest
    container_name: epic-games-helper
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
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "1.0"
```

> 📌 **Multi-arch image**: `linux/amd64` and `linux/arm64` (Synology, QNAP, Unraid, Raspberry Pi 4+)

---

## 🔐 Privacy & Security

| Storage | Encryption | File |
|---------|------------|------|
| Device Auth Token | Fernet (AES-128-CBC + HMAC) | `/app/data/device_auth.enc` (`0600`) |
| Master Key | Plaintext | `/app/data/.env` (`0600`) |

**Only stores the OAuth token — never your password.**

---

## ⚙️ Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `EPIC_MASTER_KEY` | *auto-generated* | Fernet key (set explicitly to persist tokens across container recreations) |
| `TZ` | `Asia/Shanghai` | Timezone for scheduler |
| `SCHEDULE_DAY` | `thu` | Trigger day (`mon`–`sun`) |
| `SCHEDULE_HOUR` | `17` | Trigger hour (`0`–`23`) |
| `SCHEDULE_MINUTE` | `0` | Trigger minute (`0`–`59`) |
| `LOG_LEVEL` | `INFO` | Log level |
| `AUTO_CLAIM_ENABLED` | `false` | Auto-enable auto-claim on boot |

---

## 🛠️ API

Swagger docs at **http://localhost:8000/docs**.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/free-games` | GET | Current week free games + ownership status + checkout URL |
| `/api/device-auth/status` | GET | Whether Device Auth is configured |
| `/api/device-auth/account-info` | GET | Validate stored account is still usable |
| `/api/device-auth/request` | POST | Start Device Auth flow |
| `/api/device-auth/poll/{code}` | GET | Poll auth status |
| `/api/device-auth/claim-now` | POST | Generate claim links for this week's games |
| `/api/claim/progress/{id}` | GET | Poll claim progress |
| `/api/device-auth` | DELETE | Revoke authorization |
| `/api/auto-claim/toggle` | POST | Toggle auto-claim |
| `/api/history` | GET | Claim history |

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────┐
│  Web UI (Browser)                                   │
│  • Device Auth section                              │
│  • Per-account game library (owned / claimable)      │
│  • One-click checkout button per game               │
└──────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────┐
│  FastAPI Backend (port 8000)                        │
│  • /api/device-auth/*      OAuth flow               │
│  • /api/free-games         weekly games + library   │
│  • /api/device-auth/claim-now  generate checkout URL│
└──────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────┐
│  EpicAPIClient (pure HTTP, no browser)              │
│  • freeGamesPromotions   → this week free games     │
│  • library-service       → already-owned check      │
│  • /store/purchase (read-only,  for true auto-claim)│
└──────────────────────────────────────────────────────┘
```

---

## 📁 Project Layout

```
epic-games-helper/
├── app/
│   ├── main.py                # FastAPI entry
│   ├── epic_api.py            # 🎯 Pure HTTP Epic client
│   ├── api_device_auth.py     # Device Auth + free-games endpoints
│   ├── scheduler.py           # APScheduler weekly trigger
│   ├── credential_store.py    # Fernet encryption
│   ├── storage.py             # History persistence
│   ├── result.py              # Data models
│   ├── config.py              # Env config
│   └── static/
│       ├── device_auth.js     # Frontend logic
│       └── style.css
├── scripts/
│   └── entrypoint.sh          # Container entry
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 🐛 Troubleshooting

**Authorization keeps failing** — open the "🛠 Debug" panel in the Web UI; test buttons print the actual Epic API response.

**`Master key mismatch` after container restart** —
```bash
rm ./data/device_auth.enc
# re-authorize via the Web UI
```

**`HTTP 403` on `/store/purchase`** — this is expected; Epic requires browser session cookies we cannot forge. Use the generated checkout URL instead (one click).

---

## 🙏 Credits & Inspirations

- **[claabs/epicgames-freegames-node](https://github.com/claabs/epicgames-freegames-node)** — the original "use Device Code OAuth, generate checkout URL" approach; this project is a Python re-implementation.
- **[MixV2/EpicResearch](https://github.com/MixV2/EpicResearch)** — comprehensive reverse-engineered Epic API docs.
- **[xMistt/rebootpy](https://github.com/xMistt/rebootpy)** — Python reference for User-Agent + auth headers.
- **[Heroic-Games-Launcher/legendary](https://github.com/Heroic-Games-Launcher/legendary)** — `library-service` API endpoint shape.
- **[LeleDerGrasshalmi/FortniteEndpointsDocumentation](https://github.com/LeleDerGrasshalmi/FortniteEndpointsDocumentation)** — community endpoint docs.

---

## ⚠️ Disclaimer

For educational purposes. Please comply with [Epic Games ToS](https://www.epicgames.com/site/en-US/terms-of-service). The author is not responsible for any account action.

## 📝 License

MIT