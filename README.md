# 🎮 Epic Games Free Games Helper

> **Weekly free game tracker · history archive · zero dependencies.**
>
> Track what Epic gives away each week, see your claim history, and jump to Epic's store page.
>
> User auth & webhook notifications · per-user push channels · no browser · ~150 MB image.

🇨🇳 [中文说明](README-zh-CN.md)

---

## 📌 What is this?

`epic-games-helper` is a **lightweight HTTP API + Web UI** for tracking Epic Games weekly free games.

- 📡 **Tracks** Epic's weekly free games (refreshed every Friday 00:00 Beijing time)
- 📅 **Previews** next week's upcoming free games
- 🗂️ **Records** every weekly drop into a permanent history
- 🎯 **One-click links** to Epic's store page per game (launch directly to the product page)
- 👤 **User accounts** — register, login, configure per-user notification channels
- 📲 **Webhook push** — notify via Bark, Server 酱, PushPlus, Telegram Bot, or custom webhook

> **No login required to browse.** The free games list comes from Epic's public catalog API. Login is optional — needed only for push notifications.

---

## ✨ Features

**✅ implemented** · **🚧 in development** · **❌ won't do**

### Core

| Status | Feature |
|--------|---------|
| ✅ | **Weekly free-game tracker** — auto-fetched from Epic's public `freeGamesPromotions` API |
| ✅ | **Next-week preview** — show upcoming free games already in Epic's API (one week ahead) |
| ✅ | **Compact claim history** — ISO-week grouping, horizontal cards with cover thumbnail, dates, price |
| ✅ | **First-letter fallback** for games without cover images |
| ✅ | **Epic store link** — uses product page slug (`offerMappings[0].pageSlug`) for accurate navigation |
| ✅ | **One-click store link** — goes directly to Epic's product page |

### Web UI (Epic-styled)

| Status | Feature |
|--------|---------|
| ✅ | **Pure-black canvas** + electric-blue accent (`#0078F2`) — matches Epic Store design |
| ✅ | **Sticky nav** with connection status |
| ✅ | **Hero banner** with weekly update info |
| ✅ | **Discount deals grid** — cover, title, discount %, prices, store link |
| ✅ | **Free games grid** — cover, title, dates, original price, store link |
| ✅ | **History archive** — grouped by ISO week, horizontal cards, one per line |
| ✅ | **Fully responsive** for mobile / tablet |
| ✅ | **Debug panel** with API test buttons |

### Scheduling

| Status | Feature |
|--------|---------|
| ✅ | **APScheduler weekly trigger** (default: Beijing Friday 00:05) |
| ✅ | **Fingerprint comparison** — only records history when the weekly drop actually changes |
| ✅ | **Next-run time** displayed in health API |

### Multi-User & Notifications

| Status | Feature |
|--------|---------|
| ✅ | **User registration & login** — JWT-based auth, stored in `data/users.json` |
| ✅ | **Per-user push configuration** — each user configures their own notification channel |
| ✅ | **Webhook push** when new free games are detected — supports 5 channels: |
| | &nbsp;&nbsp;&nbsp;&nbsp;• **Bark** (iOS push) |
| | &nbsp;&nbsp;&nbsp;&nbsp;• **Server 酱** (WeChat) |
| | &nbsp;&nbsp;&nbsp;&nbsp;• **PushPlus** (WeChat / DingTalk / Feishu / Email) |
| | &nbsp;&nbsp;&nbsp;&nbsp;• **Telegram Bot** (group/channel) |
| | &nbsp;&nbsp;&nbsp;&nbsp;• **Generic Webhook** (custom POST JSON) |
| ✅ | **Global + per-user push** — both global (`NOTIFY_WEBHOOK_*`) and per-user push are sent on detection |
| ✅ | **Test push** button in UI to verify configuration |
| ✅ | **Logout** from UI |

### Infrastructure

| Status | Feature |
|--------|---------|
| ✅ | **Multi-arch Docker image** (`linux/amd64` + `linux/arm64`) |
| ✅ | **Image size ~150 MB** (no Chromium / Playwright / X11) |
| ✅ | **REST API** with Swagger UI at `/docs` |
| ✅ | **Docker Compose** example for one-line deployment |
| ✅ | **GitHub Actions CI** — syntax check + compose validation on every PR |

### Will NOT be implemented

| Status | Feature | Reason |
|--------|---------|--------|
| ❌ | True auto-claim | Epic requires browser session cookies, XSRF token, hCaptcha — cannot be forged via API |
| ❌ | Full game library | Epic's `library-service` API requires OAuth flow Epic doesn't allow for localhost |

---

## 🚀 Quick Start

### 1. Run with Docker

```bash
docker run -d \
  --name epic-helper \
  -p 8080:8080 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  zz3656/epic-games-helper:latest
```

### 2. Open in browser

Go to **http://localhost:8080** — that's it. No login, no config.

The page shows:
- **Weekly free games** — cover, title, dates, price, store link
- **History archive** — every past weekly drop, grouped by week

### 3. (Optional) Configure schedule

```bash
docker run -d \
  --name epic-helper \
  -p 8080:8080 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  -e TZ=Asia/Shanghai \
  -e SCHEDULE_DAY=fri \
  -e SCHEDULE_HOUR=0 \
  -e SCHEDULE_MINUTE=5 \
  --restart unless-stopped \
  zz3656/epic-games-helper:latest
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
      - "8080:8080"
    environment:
      - TZ=Asia/Shanghai
      # Epic updates free games at Beijing 00:00 every Friday
      - SCHEDULE_DAY=fri
      - SCHEDULE_HOUR=0
      - SCHEDULE_MINUTE=5
    volumes:
      - ./logs:/app/logs       # 历史记录 + 封面映射
      - ./data:/app/data       # 用户数据 + 配置密钥
    security_opt:
      - no-new-privileges:true
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "1.0"
```

> 📌 **Multi-arch**: `linux/amd64` + `linux/arm64` (Synology, QNAP, Unraid, Raspberry Pi 4+)

### 💾 Data Persistence

All data is persisted to host directories via Docker volumes:

| Volume | Contents |
|--------|----------|
| `./logs:/app/logs` | Claim history (`history.json`), cover map |
| `./data:/app/data` | User accounts (`users.json`), `.env` config |

> **Never lose your data:** As long as you keep the `./logs` and `./data` directories, your history and user accounts will survive container rebuilds and image updates.

---

## 🛠️ API

Swagger docs at **http://localhost:8080/docs**.

### Deals & free games

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check (includes next-run time) |
| `/api/free-games` | GET | Current + upcoming free games with cover, dates, prices, store links |
| `/api/promotions` | GET | Current store discounts with cover, title, discount %, prices, store links |
| `/api/history` | GET | Claim history (last 200 records) |
| `/api/history/latest` | GET | Latest history entry |

### Scheduler & testing

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/scheduler/test-run` | POST | Manually trigger the weekly check (debug) |

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/register` | POST | Register a new user |
| `/api/auth/login` | POST | Login (returns JWT token) |
| `/api/auth/logout` | POST | Logout |
| `/api/auth/me` | GET | Get current user info |
| `/api/auth/push-config` | GET | Get current user's push config |
| `/api/auth/push-config` | PUT | Update push config |
| `/api/auth/test-push` | POST | Test push notification |

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────┐
│  Web UI (Browser)                                          │
│  • Epic-styled design (pure black + #0078F2)               │
│  • Weekly free games grid                                  │
│  • History archive (per-week grouping)                     │
│  • Login / Register modal                                  │
│  • Push settings modal (per-user channel config)           │
│  • Debug panel + API test buttons                          │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│  FastAPI Backend (port 8080)                               │
│  • /api/free-games             weekly + upcoming games     │
│  • /api/promotions             store discounts             │
│  • /api/history                claim history               │
│  • /api/auth/*                 register/login/push config  │
│  • /api/scheduler/*            manual trigger              │
│  • APScheduler                 Friday 00:05 weekly check   │
│  • Notifier                    webhook push (multi-ctx)    │
│  • UserStore                   JSON-based user DB          │
│  • JWT Auth                    token-based auth            │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│  EpicAPIClient (pure HTTP, no browser)                     │
│  • freeGamesPromotions          → weekly + upcoming games  │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│  Push Channels                                               │
│  • Server 酱 (WeChat) / Telegram Bot                         │
│  • Global + per-user channels                              │
└────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Layout

```
epic-games-helper/
├── app/
│   ├── main.py                # FastAPI entry
│   ├── epic_api.py            # Pure HTTP Epic client (freeGamesPromotions)
│   ├── scheduler.py           # APScheduler weekly check + fingerprint + push
│   ├── notifier.py            # Webhook push (Server 酱 / Telegram)
│   ├── storage.py             # History persistence (deque + JSON file)
│   ├── user_store.py          # User data store (JSON + bcrypt)
│   ├── auth.py                # JWT auth module
│   ├── api_users.py           # User management API (register/login/push config)
│   ├── result.py              # Data models
│   ├── config.py              # Env config
│   └── static/
│       ├── device_auth.js     # Page init + utilities (~130 lines)
│       ├── free_games.js      # Game card rendering + history (~260 lines)
│       ├── auth_core.js       # Auth core (login/register modal)
│       ├── auth_settings.js   # Push settings modal + user UI
│       └── style.css          # Epic design system (~20 KB)
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

**Clicking store link but Epic shows error** — Epic's frontend JS is failing its `cartOffersValidation` API call. Common causes: (1) browser not logged into Epic, (2) Epic EULA not accepted, (3) 2FA not enabled. Log into Epic in your browser, accept any EULAs, enable 2FA in Epic account settings, then retry.

**Container won't start** — check `docker logs epic-games-helper`. Common issue: port `8080` already in use; change the left side of the `-p` mapping.

---

## 🙏 Credits

- **[MixV2/EpicResearch](https://github.com/MixV2/EpicResearch)** — Epic `freeGamesPromotions` API endpoint & response structure documentation

---

## ⚠️ Disclaimer

For educational purposes. Please comply with [Epic Games ToS](https://www.epicgames.com/site/en-US/terms-of-service). The author is not responsible for any account action.

## 📝 License

MIT
