# 🎮 Epic Games Free Games Helper

> **Track Epic's weekly free games · identify already-owned titles · one-click checkout.**
> **设备码授权** · 零浏览器 · 零验证码 · 容器 ~150MB。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker Pulls](https://img.shields.io/docker/pulls/zz3656/epic-games-helper.svg?style=flat)](https://hub.docker.com/r/zz3656/epic-games-helper)
[![Multi-arch](https://img.shields.io/badge/arch-amd64%20%7C%20arm64-lightgrey.svg)](https://hub.docker.com/r/zz3656/epic-games-helper)

---

## ⚠️ Important: This is a *helper*, not a full auto-claimer

Epic Games' purchase endpoints require browser session cookies (XSRF, hCaptcha, etc.)
that **cannot** be forged via API. This tool therefore:

- ✅ Tracks the weekly free-games list (every Friday 00:00 Beijing)
- ✅ Previews next week's upcoming free games
- ✅ Generates a **one-click checkout URL** per game (jumps to Epic's product page)
- ✅ Records every weekly drop into a permanent history
- ✅ Pushes webhook notifications (Bark/Server酱/Telegram) when the drop changes
- 🚧 **Cannot** POST `/store/purchase` end-to-end — Epic requires browser session

For most users, one click is good enough.

---

## ✨ Features

Legend: **✅ implemented** · **🚧 in development** · **❌ not implemented (won't do)**

### Core

- ✅ Epic Device Code OAuth — one-time browser login → permanent token (no password, no hCaptcha)
- ✅ Weekly free-game tracker (auto-fetched from `freeGamesPromotions`)
- ✅ Next-week preview (shows upcoming free games one week ahead)
- ✅ One-click checkout URL per game (Epic-compatible `offers=1-{ns}-{id}` format)
- ✅ Rich game cards (cover, title, dates, original price, "ends in N days" badge)
- ✅ Fingerprint comparison — only acts when weekly drop actually changes

### Web UI (Epic-styled)

- ✅ Pure-black canvas + electric-blue accent (`#0078F2`)
- ✅ Sticky top nav with auth status indicator
- ✅ Hero banner with weekly refresh info
- ✅ Compact claim history (per-week grouping, horizontal cards)
- ✅ First-letter placeholder for games without cover images
- ✅ Debug panel with API test buttons
- ✅ Fully responsive (mobile/tablet/desktop)

### Scheduling & Notifications

- ✅ APScheduler weekly trigger (default: Beijing Friday 00:05)
- ✅ Webhook notifications — Bark (iOS) / Server酱 (WeChat) / Telegram Bot / generic webhook
- ✅ Next-run time displayed in the UI
- 🚧 True auto-claim — Epic requires browser session cookies; we cannot forge them

### Persistence & Privacy

- ✅ Fernet-encrypted token storage (AES-128-CBC + HMAC), file mode `0600`
- ✅ Master key auto-generated on first run
- ✅ History persisted in `logs/history.json` (last 100 weekly drops)
- ✅ Logs volume mounted for history persistence
- ✅ **No password ever stored** — only OAuth token

### Infrastructure

- ✅ Multi-arch Docker image (`linux/amd64` + `linux/arm64`)
- ✅ Image size ~150 MB (no Chromium / Playwright / X11 / VNC)
- ✅ REST API with Swagger UI at `/docs`
- ✅ Docker Compose example for one-line deployment
- ✅ GitHub Actions CI (syntax check + compose validation)

### Will NOT be implemented

- ❌ True zero-click auto-claim — Epic needs browser session cookies
- ❌ Multi-account support — single-account design keeps credential store simple
- ❌ Built-in browser fallback — would balloon image from 150 MB to 1 GB+ and add hCaptcha risk
- ❌ Full game library (all purchased games) — Epic's `library-service` API requires OAuth authorization_code flow which Epic does not allow for localhost redirect_uri

---

## 🚀 Quick Start

```bash
docker run -d \
  --name epic-helper \
  -p 8080:8000 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  zz3656/epic-games-helper:latest
```

Open **http://localhost:8080**, then:

1. Click **"开始设备码授权"** (Start Device Code Auth)
2. Copy the `user_code`, click the Epic authorization link
3. Log into Epic in your own browser and approve the device
4. UI auto-detects success → token saved

Future weekly drops are tracked automatically.

### Docker Compose

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
      # Webhook (optional)
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

---

## ⚙️ Environment Variables

| Var | Default | Description |
|-----|---------|-------------|
| `EPIC_MASTER_KEY` | *auto-generated* | Fernet key (set explicitly to persist tokens across container recreations) |
| `TZ` | `Asia/Shanghai` | Timezone for scheduler |
| `SCHEDULE_DAY` | `fri` | Trigger day (`mon`–`sun`, default Friday) |
| `SCHEDULE_HOUR` | `0` | Trigger hour (`0`–`23`, default midnight) |
| `SCHEDULE_MINUTE` | `5` | Trigger minute (`0`–`59`, default :05) |
| `LOG_LEVEL` | `INFO` | Log level |
| `AUTO_CLAIM_ENABLED` | `false` | Auto-enable on boot |
| `NOTIFY_WEBHOOK_TYPE` | _unset_ | Optional: `bark` / `serverchan` / `telegram` / `generic` |
| `NOTIFY_WEBHOOK_URL` | _unset_ | Webhook URL |
| `NOTIFY_WEBHOOK_TOKEN` | _unset_ | Webhook token/secret |

---

## 🔐 Security

- Device Auth Token: Fernet (AES-128-CBC + HMAC), file mode `0600`
- Master key: stored in `.env`, file mode `0600`
- **No password ever stored.**

---

## 🛣️ Multi-arch

| Arch | Supported |
|------|-----------|
| linux/amd64 | ✅ |
| linux/arm64 | ✅ |

Synology, QNAP, Unraid, Raspberry Pi 4+ all work.

---

## 🐛 Troubleshooting

**Authorization keeps failing** — open the **🛠 调试选项** panel at the bottom of the Web UI. Test buttons print the actual Epic API response.

**Click "领取" but Epic shows error** — Epic's frontend JS is failing its `cartOffersValidation` API call. Common causes: (1) browser not logged into Epic, (2) Epic EULA not accepted, (3) 2FA not enabled. Log into Epic in your browser, accept any EULAs, enable 2FA in Epic account settings, then retry.

**`Master key mismatch` after container restart**:
```bash
rm ./data/device_auth.enc
# Re-authorize via Web UI
```

**Webhook notifications not arriving** — open **🛠 调试选项** → click **测试 webhook 推送**. Check the response for the actual error from the webhook provider.

---

## 🙏 Credits

- [claabs/epicgames-freegames-node](https://github.com/claabs/epicgames-freegames-node) — Device Code OAuth + checkout URL approach
- [MixV2/EpicResearch](https://github.com/MixV2/EpicResearch) — Epic API documentation
- [xMistt/rebootpy](https://github.com/xMistt/rebootpy) — Python auth headers reference
- [Heroic-Games-Launcher/legendary](https://github.com/Heroic-Games-Launcher/legendary) — `library-service` endpoint shape

## 📜 License

MIT

---

> GitHub: [zz3656/epic-games-helper](https://github.com/zz3656/epic-games-helper)
> Docker Hub: [zz3656/epic-games-helper](https://hub.docker.com/r/zz3656/epic-games-helper)
