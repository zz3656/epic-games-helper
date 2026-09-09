# 🎮 Epic Games Free Games Helper

> Track Epic Games weekly free games · identify already-owned titles · one-click checkout.
> **设备码授权** · 零浏览器 · 零验证码 · 容器 ~150MB。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://www.docker.com/)
[![Docker Pulls](https://img.shields.io/docker/pulls/zz3656/epic-games-helper.svg?style=flat)](https://hub.docker.com/r/zz3656/epic-games-helper)
[![Multi-arch](https://img.shields.io/badge/arch-amd64%20%7C%20arm64-lightgrey.svg)](https://hub.docker.com/r/zz3656/epic-games-helper)

---

## ⚠️ Important: This is a *helper*, not a full auto-claimer

Epic Games' purchase endpoints require browser session cookies (XSRF, hCaptcha, etc.)
that **cannot** be forged via API. This tool therefore:

- ✅ Tracks the weekly free-games list
- ✅ Cross-references with your library (marks already-owned)
- ✅ Generates a **one-click checkout URL** per game
- 🚧 **Cannot** POST `/store/purchase` end-to-end (planned, see roadmap below)

For most users, one click is good enough. For everyone else: roadmap below.

---

## ✨ Features

### ✅ Implemented

- 🔑 **Device Code OAuth** — one-time browser login → permanent token (no password, no hCaptcha)
- 🗓️ **Weekly free-game tracker** — auto-fetched from `freeGamesPromotions`
- 📚 **Library cross-check** — marks already-owned via `library-service` API
- 🖼️ **Rich game cards** — cover, title, dates, original price, "end in N days"
- 🎯 **One-click checkout URL** per game
- ⏰ **Scheduled weekly check** via APScheduler
- 🔌 **REST API** with Swagger UI at `/docs`
- 🛡️ **Fernet-encrypted token storage** (AES-128-CBC + HMAC), `0600` permissions
- 🐳 **Multi-arch** image: `linux/amd64` + `linux/arm64`

### 🚧 Roadmap (in priority order)

- 🎮 **True auto-claim** — investigate TrustedServer policy / GQL mutations / headless Chromium fallback to POST `/store/purchase` for real
- 👥 **Multi-account support** — redesign credential store for N accounts
- 📲 **Push notifications** — Telegram / email / webhook the moment a new drop goes live
- 🌍 **Per-region support** — currently hard-coded `zh-CN/CN`

---

## 🚀 Quick Start

```bash
docker run -d \
  --name epic-helper \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  zz3656/epic-games-helper:latest
```

Then open **http://localhost:8000** and:

1. Click **"🔑 Epic 设备码授权"**
2. Copy the `user_code`, click the Epic auth link
3. Log into Epic in your own browser and approve the device
4. UI auto-detects success → token saved

Weekly drops are now tracked automatically.

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

---

## ⚙️ Environment Variables

| Var | Default | Description |
|-----|---------|-------------|
| `EPIC_MASTER_KEY` | *auto-generated* | Fernet key (set explicitly to persist tokens across container recreations) |
| `TZ` | `Asia/Shanghai` | Timezone for scheduler |
| `SCHEDULE_DAY` | `thu` | Trigger day (`mon`–`sun`) |
| `SCHEDULE_HOUR` | `17` | Trigger hour |
| `SCHEDULE_MINUTE` | `0` | Trigger minute |
| `LOG_LEVEL` | `INFO` | Log level |
| `AUTO_CLAIM_ENABLED` | `false` | Auto-enable on boot |

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

**Authorization keeps failing** — open the "🛠 Debug" panel in the Web UI; test buttons print the actual Epic API response.

**`Master key mismatch` after container restart**:
```bash
rm ./data/device_auth.enc
# Re-authorize via Web UI
```

**`HTTP 403` on `/store/purchase`** — expected. Epic needs browser session cookies we can't forge. Use the generated checkout URL (one click).

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