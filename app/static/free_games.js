// ============ 本周免费游戏 + 下周预告 + 每周赠送记录渲染 ============
// 依赖：device_auth.js 提供的 escapeHtml / fetchWithTimeout
// 全局状态：currentWeeklyGames / currentUpcomingGames（由 device_auth.js 维护）

// 日期格式化
function formatDate(iso) {
    if (!iso) return "";
    try {
        const d = new Date(iso);
        return `${d.getMonth() + 1}/${d.getDate()}`;
    } catch { return ""; }
}

function formatDates(startIso, endIso) {
    const s = formatDate(startIso);
    const e = formatDate(endIso);
    if (!s && !e) return "";
    return `${s} – ${e}`;
}

function daysUntilEnd(endIso) {
    if (!endIso) return null;
    try {
        const end = new Date(endIso);
        const now = new Date();
        const diff = Math.ceil((end - now) / (1000 * 60 * 60 * 24));
        return diff;
    } catch { return null; }
}

// ============ 加载本周免费游戏 + 下周预告 ============
async function loadWeeklyFreeGames() {
    if (!weeklyFreeGrid) return;
    weeklyFreeHint.textContent = "加载中…";
    weeklyFreeGrid.innerHTML = "";

    try {
        const resp = await fetchWithTimeout("/api/free-games", 30000);
        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
        }
        const data = await resp.json();
        if (!data.success) {
            throw new Error(data.error || "未知错误");
        }

        const games = data.free_games || [];
        const upcoming = data.upcoming_free_games || [];
        currentWeeklyGames = games;
        currentUpcomingGames = upcoming;

        // 提示信息
        const parts = [];
        if (games.length > 0) parts.push(`本周 ${games.length} 款免费`);
        if (upcoming.length > 0) parts.push(`下周 ${upcoming.length} 款预告`);
        weeklyFreeHint.textContent = parts.length > 0 ? parts.join(' · ') : "本周暂无免费游戏";

        weeklyFreeGrid.innerHTML = "";

        // 所有游戏卡片混排（下周预告用徽章区分，不再加分区标题）
        const allGames = [
            ...games.map(g => ({ game: g, isUpcoming: false })),
            ...upcoming.map(g => ({ game: g, isUpcoming: true })),
        ];
        if (allGames.length > 0) {
            const html = renderFreeGameCards(allGames.map(g => g.game), allGames.map(g => g.isUpcoming));
            weeklyFreeGrid.insertAdjacentHTML("beforeend", html);
        }
    } catch (err) {
        weeklyFreeHint.textContent = "❌ 加载失败";
        weeklyFreeGrid.innerHTML = `<div class="empty-state">
            <div class="empty-state-icon">⚠️</div>
            <div>加载本周免费游戏失败</div>
            <div class="mt-1 text-warning" style="font-size:12px;">${escapeHtml(String(err.message || err))}</div>
            <div class="mt-1 text-muted" style="font-size:11px;">请检查后端服务是否运行</div>
        </div>`;
    }
}

// ============ 渲染免费游戏卡片 ============
// isUpcoming: true = 下周预告（不可领取，只显示商店页链接）
function renderFreeGameCards(games, isUpcoming) {
    return games.map(g => {
        const daysLeft = daysUntilEnd(g.end_date);
        const datesHtml = g.start_date || g.end_date
            ? `<div class="game-dates">
                   <span class="free">🆓 ${escapeHtml(formatDates(g.start_date, g.end_date))}</span>
                   ${daysLeft !== null && daysLeft > 0 && daysLeft <= 3
                       ? ` <span class="end-soon">仅剩 ${daysLeft} 天</span>` : ""}
               </div>`
            : "";
        const priceHtml = g.original_price
            ? `<div class="game-price-row"><span class="original">${escapeHtml(g.original_price)}</span><span class="free">免费</span></div>`
            : `<div class="game-price-row"><span class="free">🆓 免费</span></div>`;

        const cover = g.image_url
            ? `<img class="game-cover" src="${escapeHtml(g.image_url)}" alt="${escapeHtml(g.title)}" loading="lazy" onerror="this.outerHTML='<div class=&quot;game-cover-placeholder&quot;>🎮</div>'">`
            : `<div class="game-cover-placeholder">🎮</div>`;

        const badge = isUpcoming
            ? `<span class="game-status-badge upcoming">下周免费</span>`
            : `<span class="game-status-badge free">现在免费</span>`;

        // 现在免费：跳转到 Epic 商品页，用户点击 Epic 原生「获取/添加到库」按钮领取
        // 下周预告：仅查看详情，不能领取
        const actionBtn = isUpcoming
            ? `<a class="btn-claim-card preview" href="${escapeHtml(g.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">查看详情</a>`
            : `<a class="btn-claim-card" href="${escapeHtml(g.checkout_url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">🎁 前往领取</a>`;

        return `
            <div class="game-card ${isUpcoming ? "upcoming" : ""}" data-offer-id="${escapeHtml(g.offer_id)}">
                ${cover}
                <div class="game-info">
                    <h3 class="game-title">${escapeHtml(g.title)} ${badge}</h3>
                    ${datesHtml}
                    ${priceHtml}
                    ${g.description ? `<div class="game-description">${escapeHtml(g.description)}</div>` : ""}
                    <div class="game-actions">${actionBtn}</div>
                </div>
            </div>
        `;
    }).join("");
}

// ============ 加载每周赠送记录 ============
// 从 history.json 中按 ISO week 分组提取所有领取过的免费游戏
async function loadWeeklyHistory() {
    if (!weeklyHistoryGrid) return;
    weeklyHistoryGrid.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⏳</div><div>加载中…</div></div>`;

    try {
        const resp = await fetchWithTimeout("/api/history?limit=200", 10000);
        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
        }
        const data = await resp.json();

        const items = (data.items || []).filter(item =>
            item.games && item.games.length > 0
        );

        if (items.length === 0) {
            weeklyHistoryGrid.innerHTML = `<div class="empty-state">
                <div class="empty-state-icon">📜</div>
                <div>暂无记录</div>
                <div class="mt-1 text-muted" style="font-size:12px;">等定时任务检测到本周免费游戏后即自动记录</div>
            </div>`;
            return;
        }

        // 按 ISO week 分组
        const grouped = groupByWeek(items);
        weeklyHistoryGrid.innerHTML = renderWeeklyGroups(grouped);
    } catch (err) {
        weeklyHistoryGrid.innerHTML = `<div class="empty-state">
            <div class="empty-state-icon">⚠️</div>
            <div>加载历史记录失败</div>
            <div class="mt-1 text-warning" style="font-size:12px;">${escapeHtml(String(err.message || err))}</div>
        </div>`;
    }
}

// 把历史记录按"领取日期的 ISO week（年-周）"分组
function groupByWeek(items) {
    const groups = {};  // key: "2026-W37", value: { year, week, items }
    for (const item of items) {
        const d = item.started_at ? new Date(item.started_at) : new Date();
        // ISO week 计算
        const target = new Date(d.valueOf());
        const dayNr = (d.getDay() + 6) % 7;  // 周一为 0
        target.setDate(target.getDate() - dayNr + 3);
        const firstThursday = target.valueOf();
        target.setMonth(0, 1);
        if (target.getDay() !== 4) {
            target.setMonth(0, 1 + ((4 - target.getDay()) + 7) % 7);
        }
        const week = 1 + Math.ceil((firstThursday - target) / 604800000);
        const year = d.getFullYear();

        const key = `${year}-W${String(week).padStart(2, "0")}`;
        if (!groups[key]) {
            groups[key] = {
                year, week, key,
                label: `${year} 年第 ${week} 周`,
                items: [],
            };
        }
        groups[key].items.push(item);
    }

    // 按 key 降序（最新在前）
    return Object.values(groups).sort((a, b) => b.key.localeCompare(a.key));
}

function renderWeeklyGroups(groups) {
    return groups.map(g => {
        // 收集这一周所有领取过的游戏（严格按 offer_id 去重）
        const seen = new Set();
        const games = [];
        for (const item of g.items) {
            for (const game of (item.games || [])) {
                const dedupKey = game.offer_id || `t:${game.title}`;
                if (seen.has(dedupKey)) continue;
                seen.add(dedupKey);
                games.push({
                    title: game.title,
                    url: game.url,
                    image_url: game.image_url || "",
                    end_date: game.end_date || "",
                    original_price: game.original_price || "",
                    status: game.status || "",
                    message: game.message || "",
                    offer_id: game.offer_id || "",
                    week_started_at: item.started_at,
                });
            }
        }

        const gamesHtml = games.map(renderHistoryCard).join("");

        return `
            <div class="week-group">
                <div class="week-group-header">
                    <span class="week-group-title">📅 ${escapeHtml(g.label)}</span>
                    <span class="week-group-count">${games.length} 款游戏</span>
                </div>
                <div class="history-list">
                    ${gamesHtml}
                </div>
            </div>
        `;
    }).join("");
}

// 获取游戏标题首字（中英文兼容）
function getInitial(title) {
    if (!title) return "🎮";
    return title.trim().charAt(0).toUpperCase() || "🎮";
}

// 渲染每周记录中的游戏（水平列表卡片）
function renderHistoryCard(game) {
    const statusInfo = getHistoryStatusInfo(game.status);
    const initial = getInitial(game.title);

    // 封面：优先用图片，失败/缺失时用首字占位
    const cover = game.image_url
        ? `<img class="history-cover" src="${escapeHtml(game.image_url)}" alt="${escapeHtml(game.title)}" loading="lazy" onerror="this.outerHTML='<div class="history-cover-placeholder">${escapeHtml(initial)}</div>'">`
        : `<div class="history-cover-placeholder">${escapeHtml(initial)}</div>`;

    // 第一行：标题 + 状态
    const row1 = `
        <div class="history-row1">
            <h3 class="history-title">${escapeHtml(game.title)}</h3>
            <span class="history-status ${statusInfo.cls}">${statusInfo.icon} ${statusInfo.label}</span>
        </div>
    `;

    // 第二行：日期 + 价格 + 赠送时间
    const row2Parts = [];
    if (game.end_date) {
        row2Parts.push(`<span class="meta-item">🆓 ${escapeHtml(formatDates(game.week_started_at, game.end_date))}</span>`);
    }
    if (game.original_price) {
        row2Parts.push(`<span class="meta-item"><span class="original">${escapeHtml(game.original_price)}</span><span class="free">免费</span></span>`);
    }
    if (game.week_started_at) {
        row2Parts.push(`<span class="meta-item">📅 ${escapeHtml(formatGrantDate(game.week_started_at))}</span>`);
    }
    const row2 = `<div class="history-row2">${row2Parts.join("")}</div>`;

    // 整个卡片是可点击的链接
    if (game.url) {
        return `
            <a class="history-game-card" href="${escapeHtml(game.url)}" target="_blank" rel="noopener" data-offer-id="${escapeHtml(game.offer_id)}">
                ${cover}
                <div class="history-info">${row1}${row2}</div>
                <span class="history-link-arrow">›</span>
            </a>
        `;
    }
    return `
        <div class="history-game-card" data-offer-id="${escapeHtml(game.offer_id)}">
            ${cover}
            <div class="history-info">${row1}${row2}</div>
        </div>
    `;
}

// 状态映射
function getHistoryStatusInfo(status) {
    const map = {
        "available":     { icon: "🆕", label: "待领取",  cls: "owned" },
        "upcoming":      { icon: "📅", label: "下周",    cls: "upcoming" },
        "claimed":       { icon: "✅", label: "已领取",  cls: "success" },
        "already_claimed":{ icon: "🔁", label: "已拥有",  cls: "owned" },
        "needs_manual":  { icon: "👉", label: "待手动",  cls: "manual" },
        "pending":       { icon: "⏳", label: "处理中",  cls: "manual" },
        "failed":        { icon: "❌", label: "失败",    cls: "failed" },
    };
    return map[status] || { icon: "🎯", label: status || "未知", cls: "manual" };
}

// 格式化赠送日期 (ISO → "9月10日 14:30")
function formatGrantDate(iso) {
    if (!iso) return "未知";
    try {
        const d = new Date(iso);
        return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    } catch {
        return iso;
    }
}