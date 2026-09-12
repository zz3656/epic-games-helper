# 🎮 Epic Games Store Tracker

> **Weekly free games · current discounts · history archive · zero login.**
>
> Track Epic Store deals — free games, promotions, and claim history. Pure HTTP API · ~150 MB image.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker Pulls](https://img.shields.io/docker/pulls/zz3656/epic-games-helper.svg?style=flat)](https://hub.docker.com/r/zz3656/epic-games-helper)
[![Multi-arch](https://img.shields.io/badge/arch-amd64%20%7C%20arm64-lightgrey.svg)](https://hub.docker.com/r/zz3656/epic-games-helper)

---

## ⚡ What is this?

`epic-games-helper` is a **lightweight HTTP API + Web UI** for tracking Epic Games Store deals.

- 🏷️ **Discount deals** — current promotions with discount %, price comparison
- 🎮 **Free games** — weekly free games + next week's preview
- 📜 **History archive** — permanent record grouped by ISO week
- 🔗 **One-click store links** — direct navigation to Epic product pages
- 📲 **Notification** — Webhook push (Bark / PushPlus / Server 酱 / Telegram)
- 🚫 **No login · No browser · No captcha**
- 📦 Image size ~150 MB

## ✨ Features

| Feature | Status |
|---------|--------|
| Discount deals tracker (current promotions) | ✅ |
| Weekly free game tracker | ✅ |
| Next-week preview | ✅ |
| History archive (per-week grouping) | ✅ |
| Epic store links | ✅ |
| Compact horizontal history cards | ✅ |
| First-letter fallback for missing covers | ✅ |
| Fully responsive UI (mobile/tablet) | ✅ |
| APScheduler weekly check (Fri 00:05 BJ) | ✅ |
| Fingerprint comparison (only record on changes) | ✅ |
| Webhook notifications (Bark/PushPlus/Server 酱/Telegram) | ✅ |
| Multi-arch Docker image | ✅ |
| REST API + Swagger UI | ✅ |
| Docker Compose support | ✅ |
| GitHub Actions CI | ✅ |

---

## 🚀 Quick Start

```bash
docker run -d \
  --name epic-helper \
  -p 8080:8000 \
  -v $(pwd)/logs:/app/logs \
  --restart unless-stopped \
  zz3656/epic-games-helper:latest
```

Open **http://localhost:8080** — no login, no config.

---

## ⚙️ Environment Variables

| Var | Default | Description |
|-----|---------|-------------|
| `TZ` | `Asia/Shanghai` | Timezone |
| `SCHEDULE_DAY` | `fri` | Trigger day |
| `SCHEDULE_HOUR` | `0` | Trigger hour |
| `SCHEDULE_MINUTE` | `5` | Trigger minute |
| `NOTIFY_WEBHOOK_TYPE` | — | Notification channel: `bark`/`pushplus`/`serverchan`/`telegram`/`generic` |
| `NOTIFY_WEBHOOK_URL` | — | Webhook URL |
| `NOTIFY_WEBHOOK_TOKEN` | — | Token / device key / sendkey / chat_id |

### Notification Channels

| Channel | Config | Notes |
|---------|--------|-------|
| **Bark** | iOS push app | `NOTIFY_WEBHOOK_TOKEN=bark-key` |
| **PushPlus** | WeChat push (recommended) | `NOTIFY_WEBHOOK_TYPE=pushplus`, `PUSHPLUS_CHANNEL=wechat` |
| **Server 酱** | WeChat push | `NOTIFY_WEBHOOK_TYPE=serverchan` |
| **Telegram** | Bot to channel/group | `NOTIFY_WEBHOOK_TYPE=telegram` |

---

## 🛣️ Multi-arch

| Arch | Supported |
|------|-----------|
| linux/amd64 | ✅ |
| linux/arm64 | ✅ |

Synology, QNAP, Unraid, Raspberry Pi 4+ all work.

---

## 📜 License

MIT

---

> GitHub: [zz3656/epic-games-helper](https://github.com/zz3656/epic-games-helper)
> Docker Hub: [zz3656/epic-games-helper](https://hub.docker.com/r/zz3656/epic-games-helper)
