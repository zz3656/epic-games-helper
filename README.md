# 🎮 Epic Games Free Games Helper

> **Weekly free game tracker · history archive · zero dependencies.**
>
> Track what Epic gives away each week, see your claim history, and jump to Epic's store page.
>
> No login. No browser. No captcha. ~150 MB image.

🇨🇳 [中文说明](README-zh-CN.md)

---

## 📌 What is this?

`epic-games-helper` is a **lightweight HTTP API + Web UI** for tracking Epic Games weekly free games.

- 📡 **Tracks** Epic's weekly free games (refreshed every Friday 00:00 Beijing time)
- 📅 **Previews** next week's upcoming free games
- 🗂️ **Records** every weekly drop into a permanent history
- 🎯 **One-click links** to Epic's store page per game (launch directly to the product page)

> **No login required.** The free games list comes from Epic's public catalog API — no credentials needed.

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
| ❌ | Account login | Not needed — free games data is public. No entitlements or ownership queries |
| ❌ | Full game library | Epic's `library-service` API requires OAuth flow Epic doesn't allow for localhost |
| ❌ | Multi-account support | Single-app design |

---

## 🚀 Quick Start

### 1. Run with Docker

```bash
docker run -d \
  --name epic-helper \
  -p 8080:8080 \
  -v $(pwd)/logs:/app/logs \
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
      - ./logs:/app/logs
    security_opt:
      - no-new-privileges:true
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "1.0"
```

> 📌 **Multi-arch**: `linux/amd64` + `linux/arm64` (Synology, QNAP, Unraid, Raspberry Pi 4+)

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

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────┐
│  Web UI (Browser)                                          │
│  • Epic-styled design (pure black + #0078F2)               │
│  • Weekly free games grid                                  │
│  • History archive (per-week grouping)                     │
│  • Debug panel + API test buttons                          │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│  FastAPI Backend (port 8080)                               │
│  • /api/free-games             weekly + upcoming games     │
│  • /api/history                claim history               │
│  • /api/scheduler/*            manual trigger              │
│  • APScheduler                 Friday 00:05 weekly check   │
└────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────┐
│  EpicAPIClient (pure HTTP, no browser)                     │
│  • freeGamesPromotions          → weekly + upcoming games  │
└────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Layout

```
epic-games-helper/
├── app/
│   ├── main.py                # FastAPI entry
│   ├── epic_api.py            # Pure HTTP Epic client (freeGamesPromotions)
│   ├── api_device_auth.py     # (kept for backwards compat)
│   ├── scheduler.py           # APScheduler weekly check + fingerprint
│   ├── credential_store.py    # (kept for backwards compat)
│   ├── storage.py             # History persistence (deque + JSON file)
│   ├── result.py              # Data models
│   ├── config.py              # Env config
│   └── static/
│       ├── device_auth.js     # Page init + utilities (~130 lines)
│       ├── free_games.js      # Game card rendering + history (~260 lines)
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

- **[claabs/epicgames-freegames-node](https://github.com/claabs/epicgames-freegames-node)** — Device Code OAuth + checkout URL approach
- **[MixV2/EpicResearch](https://github.com/MixV2/EpicResearch)** — Epic API documentation

---

## ⚠️ Disclaimer

For educational purposes. Please comply with [Epic Games ToS](https://www.epicgames.com/site/en-US/terms-of-service). The author is not responsible for any account action.

## 📝 License

MIT
