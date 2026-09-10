# 🎮 Epic Games Free Games Helper

> **Weekly free-game tracker · one-click checkout helper · zero-browser · zero-captcha · ~150 MB image.**
>
> Track what Epic gives away each week, see your claim history, and get notified the moment a new drop goes live.

🇨🇳 [中文说明](README-zh-CN.md)

---

## 📌 What is this?

`epic-games-helper` is a **lightweight HTTP API + Web UI** that helps you never miss an Epic Games free drop.

- 📡 **Tracks** Epic's weekly free games (refreshed every Friday 00:00 Beijing time)
- 📅 **Previews** next week's upcoming free games
- 🗂️ **Records** every weekly drop you've claimed into a permanent history
- 📲 **Pushes** webhook notifications (Bark / Server酱 / Telegram / generic) the moment a new drop is detected
- 🎯 **Generates** a one-click checkout URL per game (jumps straight to Epic's product page)

> **Important:** Epic Games' purchase endpoints **cannot** be fully automated without a
> browser session (cookies, XSRF, hCaptcha). This tool therefore **does not directly claim
> games for you** — but it does everything *around* that, so claiming is **one click**.

---

## ✨ Features

Legend: **✅ implemented** · **🚧 in development** · **❌ not implemented (won't do)**

### Core

| Status | Feature |
|--------|---------|
| ✅ | **Epic Device Code OAuth** — log in once in your own browser, get a permanent token (no password storage, no hCaptcha) |
| ✅ | **Weekly free-games tracker** — auto-fetched from Epic's public catalog API (`freeGamesPromotions`) |
| ✅ | **Next-week preview** — show upcoming free games already in Epic's API (one week ahead) |
| ✅ | **One-click checkout URL** — generated per game; click jumps to Epic's product page |
| ✅ | **Rich game cards** — cover image, title, original price, free-window dates, "ends in N days" badge |
| ✅ | **Claim URL format** — uses Epic-compatible `offers=1-{namespace}-{offerId}` parameter (avoids `cartOffersValidation` 400) |
| ✅ | **Game page link** — uses Epic's accurate product page slug (`offerMappings[0].pageSlug`) |

### Web UI (Epic-styled)

| Status | Feature |
|--------|---------|
| ✅ | **Pure-black canvas** + electric-blue accent (`#0078F2`) — matches Epic Store's design system |
| ✅ | **Sticky top nav** with auth status indicator |
| ✅ | **Hero banner** with weekly refresh info |
| ✅ | **Device Auth flow** — copy user code, click Epic link, auto-detect success |
| ✅ | **Weekly free games section** with current + upcoming games |
| ✅ | **Compact claim history** — ISO-week grouping, horizontal cards with cover thumbnail, dates, price, status |
| ✅ | **First-letter fallback** for games without cover images |
| ✅ | **Debug panel** with API test buttons |
| ✅ | **Fully responsive** for mobile / tablet |

### Scheduling & Notifications

| Status | Feature |
|--------|---------|
| ✅ | **APScheduler weekly trigger** (default: Beijing Friday 00:05) |
| ✅ | **Fingerprint comparison** — only pushes notifications when the weekly drop actually changes |
| ✅ | **Webhook notifications** — Bark (iOS) / Server酱 (WeChat) / Telegram Bot / generic webhook |
| ✅ | **Next-run time** displayed in the UI (no surprises) |
| ❌ | **True auto-claim** — Epic requires browser session cookies; we cannot forge them. Click "前往领取" and Epic handles the rest. |

### Persistence & Privacy

| Status | Feature |
|--------|---------|
| ✅ | **Fernet-encrypted token storage** (AES-128-CBC + HMAC), file mode `0600` |
| ✅ | **Master key auto-generated** on first run (or set `EPIC_MASTER_KEY` to persist across container recreations) |
| ✅ | **History persisted** in `logs/history.json` (last 100 weekly drops) |
| ✅ | **Logs volume mounted** for history persistence across container restarts |
| ✅ | **No password ever stored** — only OAuth token |

### Infrastructure

| Status | Feature |
|--------|---------|
| ✅ | **Multi-arch Docker image** (`linux/amd64` + `linux/arm64`) — Synology, QNAP, Unraid, Raspberry Pi 4+ |
| ✅ | **Image size ~150 MB** (no Chromium / Playwright / X11 / VNC) |
| ✅ | **REST API** with Swagger UI at `/docs` |
| ✅ | **Docker Compose** example for one-line deployment |
| ✅ | **GitHub Actions CI** — Python syntax check + docker-compose validation on every PR |
| ✅ | **Auto-sync README → Docker Hub** on every push to `main` |

### Will NOT be implemented

| Status | Feature | Reason |
|--------|---------|--------|
| ❌ | True automatic claim (zero-click) | Epic requires browser session cookies, XSRF token, and hCaptcha — cannot be forged via API |
| ❌ | Multi-account support | Single-account design keeps the credential store simple; multi-account needs a different UX (e.g., per-account tabs) |
| ❌ | Built-in browser fallback (Chromium) | Would balloon the image from 150 MB to 1 GB+ and add hCaptcha risk |
| ❌ | Full game library (all purchased games) | Epic's `library-service` API requires OAuth authorization_code flow which Epic does not allow for localhost redirect_uri |
| ❌ | Per-region support | Currently hard-coded `zh-CN/CN`; works globally since Epic's API is region-agnostic for free games |

---

## 🚀 Quick Start

### 1. Run with Docker

```bash
docker run -d \
  --name epic-helper \
  -p 8080:8000 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  zz3656/epic-games-helper:latest
```

### 2. Authorize

Open **http://localhost:8080**:

1. Click **"开始设备码授权"**
2. Copy the `user_code` (e.g. `ABCD EFGH`)
3. Click the **"🌐 打开 Epic 授权页面"** button — Epic's authorization page opens in a new tab
4. Log into your Epic account and paste the user code
5. Click "Allow" — your browser returns to the helper's success page
6. The Web UI auto-detects success and saves the token

That's it. Future weekly drops will be tracked automatically.

### 3. (Optional) Configure notifications

Edit `docker run` command or `docker-compose.yml` to add webhook env vars:

```bash
# Bark (iOS push, free)
-e NOTIFY_WEBHOOK_TYPE=bark \
  -e NOTIFY_WEBHOOK_URL=https://api.day.app \
  -e NOTIFY_WEBHOOK_TOKEN=your_device_key

# Server酱 (WeChat push)
-e NOTIFY_WEBHOOK_TYPE=serverchan \
  -e NOTIFY_WEBHOOK_URL=https://sctapi.ftqq.com \
  -e NOTIFY_WEBHOOK_TOKEN=your_sendkey

# Telegram Bot
-e NOTIFY_WEBHOOK_TYPE=telegram \
  -e NOTIFY_WEBHOOK_URL=https://api.telegram.org/-your_chat_id \
  -e NOTIFY_WEBHOOK_TOKEN=your_bot_token
```

---

## 🐳 Docker Compose

```yaml
services:
  epic-helper:
    image: zz3656/epic-games-helper:latest
    container_name: epic-games-helper
    restart: unless-stopped
    ports:
      - "8080:8000"
    environment:
      - TZ=Asia/Shanghai
      # Epic updates free games at Beijing 00:00 every Friday
      # Default: check at 00:05 (after Epic finishes updating)
      - SCHEDULE_DAY=fri
      - SCHEDULE_HOUR=0
      - SCHEDULE_MINUTE=5
      - AUTO_CLAIM_ENABLED=true
      # Webhook (optional, see Quick Start §3)
      # - NOTIFY_WEBHOOK_TYPE=bark
      # - NOTIFY_WEBHOOK_URL=https://api.day.app
      # - NOTIFY_WEBHOOK_TOKEN=your_device_key
    volumes:
      - ./logs:/app/logs
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

| Storage | Encryption | File | Permissions |
|---------|------------|------|-------------|
| Device Auth Token | Fernet (AES-128-CBC + HMAC) | `/app/data/device_auth.enc` | `0600` |
| Master Key | Plaintext | `/app/data/.env` | `0600` |
| History | JSON | `/app/logs/history.json` | `0644` |

**Only stores the OAuth token — never your password.**

---

## ⚙️ Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `EPIC_MASTER_KEY` | *auto-generated* | Fernet key (set explicitly to persist tokens across container recreations) |
| `TZ` | `Asia/Shanghai` | Timezone for scheduler |
| `SCHEDULE_DAY` | `fri` | Trigger day (`mon`–`sun`, default Friday) |
| `SCHEDULE_HOUR` | `0` | Trigger hour (`0`–`23`, default midnight) |
| `SCHEDULE_MINUTE` | `5` | Trigger minute (`0`–`59`, default :05) |
| `LOG_LEVEL` | `INFO` | Log level (`DEBUG`/`INFO`/`WARNING`/`ERROR`) |
| `AUTO_CLAIM_ENABLED` | `false` | Auto-enable auto-claim on boot |
| `NOTIFY_WEBHOOK_TYPE` | _unset_ | Optional: `bark` / `serverchan` / `telegram` / `generic` |
| `NOTIFY_WEBHOOK_URL` | _unset_ | Webhook URL (for Bark leave empty, token = device key) |
| `NOTIFY_WEBHOOK_TOKEN` | _unset_ | Webhook token/secret |

---

## 🛠️ API

Swagger docs at **http://localhost:8080/docs**.

### Free games & history

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check (includes next-run time + notify status) |
| `/api/free-games` | GET | Current + upcoming free games with cover, dates, prices, checkout URLs |
| `/api/history` | GET | Claim history (last 200 records) |
| `/api/account/games` | GET | Aggregated view (free games + claim history) |

### Device auth

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/device-auth/status` | GET | Whether device auth is configured |
| `/api/device-auth/account-info` | GET | Validate stored account is still usable |
| `/api/device-auth/request` | POST | Start device code auth flow |
| `/api/device-auth/poll/{code}` | GET | Poll auth status |
| `/api/device-auth/cancel/{code}` | DELETE | Cancel pending auth |
| `/api/device-auth` | DELETE | Revoke stored auth |

### Scheduler & testing

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/scheduler/test-run` | POST | Manually trigger the weekly check (debug) |
| `/api/scheduler/test-notify` | POST | Send a test webhook push (debug) |
| `/api/device-auth/test/free-games` | POST | Test free-games API (debug) |
| `/api/device-auth/test/request` | POST | Test device-code request (debug) |
| `/api/device-auth/test/claim` | POST | Test claim URL generation (debug) |

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────┐
│  Web UI (Browser)                                          │
│  • Epic-styled design (pure black + #0078F2)               │
│  • Device Auth flow + auto-polling                         │
│  • Weekly games + next-week preview                        │
│  • Claim history (per-week grouping)                       │
│  • Debug panel + webhook status                            │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│  FastAPI Backend (port 8000)                               │
│  • /api/device-auth/*          OAuth flow                  │
│  • /api/free-games             weekly + upcoming games     │
│  • /api/history                claim history               │
│  • /api/scheduler/*            manual trigger + webhook    │
│  • APScheduler                 Friday 00:05 weekly check   │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│  EpicAPIClient (pure HTTP, no browser)                     │
│  • freeGamesPromotions          → weekly + upcoming games  │
│  • /store/purchase?offers=...   → checkout URL              │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│  Notifier (webhook push)                                   │
│  • Bark / Server酱 / Telegram / generic webhook            │
│  • Fingerprint comparison: only fires on real changes      │
└────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Layout

```
epic-games-helper/
├── app/
│   ├── main.py                # FastAPI entry
│   ├── epic_api.py            # Pure HTTP Epic client (freeGamesPromotions)
│   ├── api_device_auth.py     # Device Auth + free-games API endpoints
│   ├── scheduler.py           # APScheduler weekly check + fingerprint
│   ├── notifier.py            # Webhook push (Bark/Server酱/Telegram/generic)
│   ├── credential_store.py    # Fernet encryption
│   ├── storage.py             # History persistence (deque + JSON file)
│   ├── result.py              # Data models
│   ├── config.py              # Env config
│   └── static/
│       ├── device_auth.js     # Main frontend logic (~330 lines)
│       ├── free_games.js      # Game card rendering + history (~210 lines)
│       └── style.css          # Epic design system (~22 KB)
├── scripts/
│   └── entrypoint.sh          # Container entry
├── .github/workflows/
│   ├── ci.yml                 # Python syntax + compose validation
│   ├── docker-image.yml       # Multi-arch Docker build + push
│   └── sync-readme-to-dockerhub.yml  # Auto-sync README → Docker Hub
├── Dockerfile
├── docker-compose.yml
├── README.md                  # English
└── README-zh-CN.md            # 中文
```

---

## 🐛 Troubleshooting

**Authorization keeps failing** — open the **🛠 调试选项** panel at the bottom of the Web UI. Test buttons print the actual Epic API response and any errors.

**Click "领取" but Epic shows "在尝试处理您的请求时发生错误"** — Epic's frontend JS is failing its `cartOffersValidation` API call. Common causes: (1) browser not logged into Epic, (2) Epic EULA not accepted, (3) 2FA not enabled on the Epic account. Log into Epic in your browser, accept any EULAs, enable 2FA in your Epic account security settings, then retry.

**`Master key mismatch` after container restart**:
```bash
rm ./data/device_auth.enc
# Re-authorize via Web UI
```

**Webhook notifications not arriving** — open the **🛠 调试选项** panel → click **测试 webhook 推送**. Check the response for the actual error from the webhook provider.

**Container won't start** — check `docker logs epic-games-helper`. Common issue: port `8080` already in use; change the left side of the `-p` mapping.

---

## 🙏 Credits & Inspirations

- **[claabs/epicgames-freegames-node](https://github.com/claabs/epicgames-freegames-node)** — the original "use Device Code OAuth, generate checkout URL" approach; this project is a Python re-implementation.
- **[MixV2/EpicResearch](https://github.com/MixV2/EpicResearch)** — comprehensive reverse-engineered Epic API docs.
- **[xMistt/rebootpy](https://github.com/xMistt/rebootpy)** — Python reference for User-Agent + auth headers.
- **[Heroic-Games-Launcher/legendary](https://github.com/Heroic-Games-Launcher/legendary)** — library-service API endpoint shape.

---

## ⚠️ Disclaimer

For educational purposes. Please comply with [Epic Games ToS](https://www.epicgames.com/site/en-US/terms-of-service). The author is not responsible for any account action.

## 📝 License

MIT
