# 🎮 Epic Games Free Games Helper

> **Track Epic's weekly free games · history archive · no login required.**
>
> Weekly free game tracker · historical gift records · pure HTTP API · ~150 MB image.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker Pulls](https://img.shields.io/docker/pulls/zz3656/epic-games-helper.svg?style=flat)](https://hub.docker.com/r/zz3656/epic-games-helper)
[![Multi-arch](https://img.shields.io/badge/arch-amd64%20%7C%20arm64-lightgrey.svg)](https://hub.docker.com/r/zz3656/epic-games-helper)

---

## ⚡ What is this?

`epic-games-helper` is a **lightweight HTTP API + Web UI** for tracking Epic Games weekly free games.

- ✅ Tracks weekly free games (Epic's public catalog API, no login needed)
- ✅ Next-week preview (shows upcoming free games one week ahead)
- ✅ Permanent history archive (grouped by ISO week)
- ✅ One-click store links to Epic's product pages
- ✅ No Chromium / Playwright / browser automation
- ✅ Image size ~150 MB

## ✨ Features

| Feature | Status |
|---------|--------|
| Weekly free game tracker | ✅ |
| Next-week preview | ✅ |
| History archive (per-week grouping) | ✅ |
| Epic store links | ✅ |
| Compact horizontal history cards | ✅ |
| First-letter fallback for missing covers | ✅ |
| Fully responsive UI (mobile/tablet) | ✅ |
| APScheduler weekly check (Fri 00:05 BJ) | ✅ |
| Fingerprint comparison (only record on changes) | ✅ |
| Multi-arch Docker image | ✅ |
| REST API + Swagger UI | ✅ |
| Docker Compose support | ✅ |
| GitHub Actions CI | ✅ |

### Will NOT be implemented

| Feature | Reason |
|---------|--------|
| Auto-claim (zero-click) | Epic needs browser session cookies, XSRF, hCaptcha — cannot be forged |
| Account login / Device auth | Not needed — free games data is public |
| Full game library | Epic library-service API requires OAuth not allowed for localhost |

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
