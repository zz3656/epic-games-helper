# ⚠️ This repository has been renamed

> **This image is no longer maintained.**
> Please use the new repository: **[zz3656/epic-games-helper](https://hub.docker.com/r/zz3656/epic-games-helper)**

The project was rebranded from `epic-games-claimer` to `epic-games-helper`
to better reflect what the tool actually does — a **helper**, not a
fully-automatic claimer (Epic's purchase API requires browser session cookies
that cannot be forged server-side).

### What changed

- ✅ Same codebase
- ✅ Same Docker image tags (`latest`, semver tags)
- ✅ Same data volume layout
- ✅ Multi-arch (linux/amd64 + linux/arm64)

### How to migrate

Just update your `docker run` / `docker-compose.yml`:

```diff
- image: zz3656/epic-games-claimer:latest
+ image: zz3656/epic-games-helper:latest
```

```diff
- container_name: epic-games-claimer
+ container_name: epic-games-helper
```

Persistent data in `/app/data` is fully compatible — no migration needed.

### Why is this not really "automatic"?

Epic's `POST /store/purchase` returns `HTTP 403` without a browser session
(cookies + XSRF + hCaptcha). The new repo at
**`zz3656/epic-games-helper`** tracks the weekly free games, marks the ones
you already own, and generates a **one-click checkout URL** per game.

---

> **GitHub:** [zz3656/epic-games-helper](https://github.com/zz3656/epic-games-helper)
> **Docker Hub:** [zz3656/epic-games-helper](https://hub.docker.com/r/zz3656/epic-games-helper)