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

// 过滤掉无意义的占位描述（避免显示"已赠送 · 历史免费游戏"这种无语义文案）
function cleanDescription(desc) {
    if (!desc) return "";
    const t = String(desc).trim();
    if (!t) return "";
    if (/^(已赠送[\s\S]*历史[\s\S]*免费[\s\S]*|历史[\s\S]*免费[\s\S]*游戏?)$/i.test(t)) return "";
    return t;
}

// 渐变背景色盘（基于标题哈希选择，保证同一游戏每次颜色一致）
function pickGradient(title) {
    const P = [["#0078F2","#00C6FF"],["#7B2FF7","#F107A3"],["#F7971E","#FFD200"],["#11998E","#38EF7D"],["#E53935","#FF7043"],["#5B247A","#1Bced8"],["#0F2027","#2C5364"],["#3A1C71","#D76D77"],["#134E5E","#71B280"],["#F12711","#F5AF19"],["#8E2DE2","#4A00E0"],["#1F4037","#99F2C8"]];
    let h = 0;
    for (let i = 0; i < (title || "").length; i++) h = (h * 31 + title.charCodeAt(i)) >>> 0;
    const [a, b] = P[h % P.length];
    return `linear-gradient(135deg, ${a} 0%, ${b} 100%)`;
}

// 文本封面：当没有真实封面时，用游戏名生成专业渐变封面
function renderGeneratedCover(title, tag) {
    const i = (title || "?").trim().charAt(0).toUpperCase() || "?";
    const g = pickGradient(title);
    const t = tag ? `<span class="cover-tag">${escapeHtml(tag)}</span>` : "";
    return `<div class="game-cover-generated" style="background:${g};">${t}<div class="cover-initial">${escapeHtml(i)}</div><div class="cover-title">${escapeHtml(title || "")}</div></div>`;
}

// onerror 回调：图片加载失败时用渐变文字封面替换
// 注意：不能用 this.outerHTML 嵌入复杂 HTML（会因双引号/换行问题被 HTML 解析器截断），
// 必须先使用 setAttribute('onerror','') 避免重入，然后用 parentNode.replaceChild 替换。
function onCoverError(img, title, tag) {
    if (img.getAttribute("data-fallback") === "1") return;  // 避免重入
    img.setAttribute("data-fallback", "1");
    img.removeAttribute("onerror");
    // 构建替代 div
    const tmp = document.createElement("div");
    tmp.innerHTML = renderGeneratedCover(title, tag || "");
    const replacement = tmp.firstElementChild;
    if (replacement && img.parentNode) {
        img.parentNode.replaceChild(replacement, img);
    }
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

        const games = data.free_games || [], upcoming = data.upcoming_free_games || [];
        currentWeeklyGames = games; currentUpcomingGames = upcoming;
        const parts = [];
        if (games.length > 0) parts.push(`本周 ${games.length} 款免费`);
        if (upcoming.length > 0) parts.push(`下周 ${upcoming.length} 款预告`);
        weeklyFreeHint.textContent = parts.length > 0 ? parts.join(' · ') : "本周暂无免费游戏";
        const allGames = [...games.map(g => ({ game: g, isUpcoming: false })), ...upcoming.map(g => ({ game: g, isUpcoming: true }))];
        if (allGames.length > 0) weeklyFreeGrid.insertAdjacentHTML("beforeend", renderFreeGameCards(allGames.map(g => g.game), allGames.map(g => g.isUpcoming)));
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

async function loadPromotions() {
    if (!weeklyPromoGrid) return;
    weeklyPromoHint.textContent = "加载中…";
    weeklyPromoGrid.innerHTML = "";
    try {
        const resp = await fetchWithTimeout("/api/promotions", 15000);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || "未知错误");
        const promotions = data.promotions || [];
        if (promotions.length > 0) {
            weeklyPromoHint.textContent = `${promotions.length} 款`;
            weeklyPromoGrid.innerHTML = renderPromoCards(promotions);
        } else {
            weeklyPromoHint.textContent = "暂无促销";
            weeklyPromoGrid.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🏷️</div><div>当前暂无促销活动</div></div>`;
        }
    } catch (err) {
        weeklyPromoHint.textContent = "加载失败";
        weeklyPromoGrid.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><div>加载促销游戏失败</div><div class="mt-1 text-warning" style="font-size:12px;">${escapeHtml(String(err.message || err))}</div></div>`;
    }
}

function renderPromoCards(games) {
    return games.map(g => {
        const discountBadge = g.discount_percent > 0 ? `<span class="promo-discount-badge">-${g.discount_percent}%</span>` : "";
        const coverSrc = proxyCoverUrl(g.image_url);
        const cover = g.image_url
            ? `<img class="game-cover" src="${escapeHtml(coverSrc)}" alt="${escapeHtml(g.title)}" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="onCoverError(this, '${escapeHtml(g.title).replace(/'/g, "\\'")}', '促销')">${discountBadge}`
            : renderGeneratedCover(g.title, "促销") + discountBadge;
        const priceHtml = g.current_price && g.original_price ? `<div class="game-price-row"><span class="original">${escapeHtml(g.original_price)}</span><span class="promo-current">${escapeHtml(g.current_price)}</span></div>` : "";
        const desc = cleanDescription(g.description);
        return `<div class="game-card promo-card" data-offer-id="${escapeHtml(g.offer_id)}">${cover}<div class="game-info"><h3 class="game-title game-title-single-line"><span class="game-title-text">${escapeHtml(g.title)}</span></h3>${priceHtml}${desc ? `<div class="game-description">${escapeHtml(desc)}</div>` : ""}<div class="game-actions"><a class="btn-claim-card preview" href="${escapeHtml(g.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">查看详情</a></div></div></div>`;
    }).join("");
}

// ============ 渲染免费游戏卡片 ============
function renderFreeGameCards(games, isUpcoming) {
    return games.map((g, i) => {
        const gameIsUpcoming = isUpcoming[i];
        const daysLeft = daysUntilEnd(g.end_date);
        const datesHtml = g.start_date || g.end_date ? `<div class="game-dates"><span class="free">🆓 ${escapeHtml(formatDates(g.start_date, g.end_date))}</span>${daysLeft !== null && daysLeft > 0 && daysLeft <= 3 ? ` <span class="end-soon">仅剩 ${daysLeft} 天</span>` : ""}</div>` : "";
        const priceHtml = g.original_price ? `<div class="game-price-row"><span class="original">${escapeHtml(g.original_price)}</span><span class="free">免费</span></div>` : `<div class="game-price-row"><span class="free">🆓 免费</span></div>`;

        // 封面：有真实封面就用真实封面，加 onerror 兜底为渐变封面；无封面直接用渐变封面
        // 走本地代理 /api/cover-proxy，避免国内访问 cdn1.epicgames.com 超时
        const coverSrc = proxyCoverUrl(g.image_url);
        const cover = g.image_url
            ? `<img class="game-cover" src="${escapeHtml(coverSrc)}" alt="${escapeHtml(g.title)}" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="onCoverError(this, '${escapeHtml(g.title).replace(/'/g, "\\'")}', '')">`
            : renderGeneratedCover(g.title);

        const badge = gameIsUpcoming
            ? `<span class="game-status-badge upcoming">下周免费</span>`
            : `<span class="game-status-badge free">现在免费</span>`;

        // 现在免费：蓝色实底按钮“可领取”，href 优先 checkout_url
        // 下周预告：描边按钮“查看详情”，href 用商店页 URL
        const actionUrl = gameIsUpcoming
            ? g.url
            : (g.checkout_url || g.url);
        const actionClass = gameIsUpcoming
            ? 'btn-claim-card preview'
            : 'btn-claim-card';
        const actionLabel = gameIsUpcoming ? "查看详情" : "可领取";
        const actionBtn = `<a class="${actionClass}" href="${escapeHtml(actionUrl || "")}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${actionLabel}</a>`;

        const description = cleanDescription(g.description);

        return `
            <div class="game-card ${gameIsUpcoming ? "upcoming" : ""}" data-offer-id="${escapeHtml(g.offer_id)}">
                ${cover}
                <div class="game-info">
                    <h3 class="game-title game-title-single-line"><span class="game-title-text">${escapeHtml(g.title)}</span>${badge}</h3>
                    ${datesHtml}
                    ${priceHtml}
                    ${description ? `<div class="game-description">${escapeHtml(description)}</div>` : ""}
                    <div class="game-actions">${actionBtn}</div>
                </div>
            </div>
        `;
    }).join("");
}

// ============ 历史赠送记录（分页）============
const HISTORY_PAGE_SIZES = [16, 32, 64, 128, 0]; // 0 = 全部
let historyPageSize = HISTORY_PAGE_SIZES[0];
try { historyPageSize = parseInt(localStorage.getItem('historyPageSize') || '16') || HISTORY_PAGE_SIZES[0]; } catch(e) {}
if (!HISTORY_PAGE_SIZES.includes(historyPageSize)) historyPageSize = 16;
let currentHistoryGames = [], currentHistoryPage = 1, totalPages = 1;
let coverMap = {}, coverMapLoaded = false, coverMapApplied = false, pagerContainer = null;
let priceMap = {}, priceMapLoaded = false;

// 从历史游戏的 pageSlug 推断运行平台（PC / Android / iOS）
// 根据 fix_history_urls.py 的修复结果：mobile 专属游戏的 pageSlug 带 -android-<hex> 或 -ios-<hex>
// PC 游戏不带这些后缀
function getGamePlatform(game) {
    const url = (game && game.url) || "";
    if (!url) return "PC";
    // 从 pageSlug 里判断（适配 negtive eg /zh-CN 等路径）
    if (/-ios-[a-f0-9]{6,8}$/i.test(url)) return "iOS";
    if (/-android-[a-f0-9]{6,8}$/i.test(url)) return "Android";
    return "PC";
}

// 把 Epic CDN 封面图代理到本地后端（国内访问 cdn1.epicgames.com 慢）
function proxyCoverUrl(url) {
    if (!url) return "";
    // 已经是本地或非 http 链接就直接返回
    if (!/^https?:\/\//i.test(url)) return url;
    // 只代理 Epic 相关 CDN，其他站点的图不动
    if (!/epicgames\.com|unrealengine\.com/i.test(url)) return url;
    return `/api/cover-proxy?url=${encodeURIComponent(url)}`;
}

async function loadCoverMap() {
    if (coverMapLoaded) return;
    try { const resp = await fetchWithTimeout("/api/cover-map", 10000);
        if (resp.ok) { const data = await resp.json();
            if (data.success && data.map && Object.keys(data.map).length > 0) {
                coverMap = data.map;
                if (currentHistoryGames.length > 0 && !coverMapApplied) renderHistoryPage({ applyCoverMap: true });
            }
        }
    } catch (e) { /* ignore */ }
    finally { coverMapLoaded = true; }
}

// 预加载游戏价格映射（当前商店价格）
async function loadPriceMap() {
    if (priceMapLoaded) return;
    try {
        const resp = await fetchWithTimeout("/api/history-prices", 10000);
        if (resp.ok) {
            const data = await resp.json();
            if (data.success && data.prices && Object.keys(data.prices).length > 0) {
                priceMap = data.prices;
                let touched = false;
                for (const game of currentHistoryGames) {
                    const pm = lookupPrice(game);
                    if (pm && !game.original_price) { game.original_price = pm; touched = true; }
                }
                if (touched) { coverMapApplied = true; renderHistoryPage(); }
            }
        }
    } catch (e) { /* ignore */ }
    finally { priceMapLoaded = true; }
}
function lookupPrice(game) {
    const t = game.title;
    const u = game.url || "";
    if (priceMap[t]) { const e = priceMap[t]; return e.current_price || e.original_price; }
    const m = u.match(/p\/([^/]+)/);
    if (m && priceMap[m[1]]) { const e = priceMap[m[1]]; return e.current_price || e.original_price; }
    for (const k of Object.keys(priceMap)) {
        const e = priceMap[k], s = (e.title || k).toLowerCase();
        if (s === t.toLowerCase() || s.includes(t.toLowerCase()) || t.toLowerCase().includes(s))
            return e.current_price || e.original_price;
    }
    return null;
}

async function loadWeeklyHistory() {
    if (!weeklyHistoryGrid) return;
    weeklyHistoryGrid.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⏳</div><div>加载中…</div></div>`;

    // 并行加载封面映射和价格映射
    loadCoverMap();
    loadPriceMap();

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
                <div>暂无历史赠送</div>
                <div class="mt-1 text-muted" style="font-size:12px;">定时任务检测到免费游戏变化后即自动记录</div>
            </div>`;
            return;
        }

        const seen = new Set(), all = [];
        for (const item of items) for (const game of (item.games || [])) {
            const dk = game.offer_id || `t:${game.title}`;
            if (seen.has(dk)) continue;
            seen.add(dk);
            all.push({ title: game.title, url: game.url, image_url: game.image_url || "", end_date: game.end_date || "", original_price: game.original_price || "", description: game.description || "", offer_id: game.offer_id || "", week_started_at: item.started_at, week_id: item.week_id || "" });
        }
        all.sort((a, b) => (b.week_started_at || "").localeCompare(a.week_started_at || ""));
        for (const game of all) { const cm = coverMap[game.title]; if (cm) { if (!game.image_url && cm.thumbnail) game.image_url = cm.thumbnail; if (!game.description && cm.description) game.description = cm.description; } }
        currentHistoryGames = all;
        currentHistoryPage = 1;
        coverMapApplied = false;  // 新一轮数据，重置 coverMap 应用标志

        // 顶部信息
        const totalCount = all.length;
        const firstWeek = all[totalCount - 1]?.week_id || "—";
        const lastWeek = all[0]?.week_id || "—";
        document.getElementById("weekly-history-meta").textContent =
            `${totalCount} 款 · ${firstWeek} ~ ${lastWeek}`;

        renderHistoryPage();
    } catch (err) {
        weeklyHistoryGrid.innerHTML = `<div class="empty-state">
            <div class="empty-state-icon">⚠️</div>
            <div>加载历史记录失败</div>
            <div class="mt-1 text-warning" style="font-size:12px;">${escapeHtml(String(err.message || err))}</div>
        </div>`;
    }
}

function renderHistoryPage(options = {}) {
    const total = currentHistoryGames.length;
    const size = historyPageSize === 0 ? total : historyPageSize;
    totalPages = Math.ceil(total / size) || 1;
    if (currentHistoryPage > totalPages) currentHistoryPage = totalPages;
    // 应用 cover-map（仅当 cover-map 已加载完成，且还未应用于本次数据）。
    // 两种触发路径：
    //   1. 外部传 applyCoverMap=true（由 loadCoverMap 完成后调用）
    //   2. coverMap 已就绪但本轮还没应用（竞态保护）
    if (!coverMapApplied && coverMapLoaded && Object.keys(coverMap).length > 0) options.applyCoverMap = true;
    if (options.applyCoverMap && !coverMapApplied) {
        let touched = false;
        for (const game of currentHistoryGames) { const cm = coverMap[game.title];
            if (cm) { if (!game.image_url && cm.thumbnail) { game.image_url = cm.thumbnail; touched = true; }
                if (!game.description && cm.description) game.description = cm.description; } }
        if (touched) coverMapApplied = true;
    }

    const startIdx = (currentHistoryPage - 1) * size;
    const endIdx = Math.min(startIdx + size, total);
    const gamesHtml = currentHistoryGames.slice(startIdx, endIdx).map(renderHistoryCard).join("");
    weeklyHistoryGrid.innerHTML = `<div class="weekly-history-grid">${gamesHtml}</div>`;
    renderPager(total, startIdx, endIdx, size);
}

function renderPager(total, startIdx, endIdx, size) {
    if (pagerContainer) { pagerContainer.remove(); pagerContainer = null; }
    if (totalPages <= 1 && historyPageSize === 0) return;
    pagerContainer = document.createElement("div");
    pagerContainer.className = "history-pager";
    const go = (p) => { currentHistoryPage = p; renderHistoryPage(); weeklyHistorySection.scrollIntoView({ behavior: "smooth", block: "start" }); };

    // 左侧：页面大小设置 + 页码跳转
    const leftGroup = document.createElement("div");
    leftGroup.className = "history-pager-left";

    // 每页显示数量选择
    const sizeLabel = document.createElement("span");
    sizeLabel.className = "history-page-size-label";
    sizeLabel.textContent = "每页显示：";
    const sizeSelect = document.createElement("select");
    sizeSelect.className = "history-page-size-select";
    HISTORY_PAGE_SIZES.forEach(s => {
        const opt = document.createElement("option");
        opt.value = s;
        opt.textContent = s === 0 ? "全部" : s;
        if (s === historyPageSize) opt.selected = true;
        sizeSelect.appendChild(opt);
    });
    sizeSelect.addEventListener("change", () => {
        historyPageSize = parseInt(sizeSelect.value, 10);
        try { localStorage.setItem('historyPageSize', String(historyPageSize)); } catch(e) {}
        currentHistoryPage = 1;
        renderHistoryPage();
    });
    leftGroup.appendChild(sizeLabel);
    leftGroup.appendChild(sizeSelect);

    // 上一页
    const prevBtn = document.createElement("button");
    prevBtn.className = "btn-pager"; prevBtn.textContent = "← 上一页";
    prevBtn.disabled = currentHistoryPage <= 1;
    prevBtn.addEventListener("click", () => { if (currentHistoryPage > 1) go(currentHistoryPage - 1); });
    leftGroup.appendChild(prevBtn);

    // 页码跳转
    const pageSelect = document.createElement("select"); pageSelect.className = "history-page-select";
    for (let i = 1; i <= totalPages; i++) { const opt = document.createElement("option"); opt.value = i; opt.textContent = `${i} / ${totalPages}`; if (i === currentHistoryPage) opt.selected = true; pageSelect.appendChild(opt); }
    pageSelect.addEventListener("change", () => { const t = parseInt(pageSelect.value, 10); if (t !== currentHistoryPage) go(t); });
    leftGroup.appendChild(pageSelect);

    // 下一页
    const nextBtn = document.createElement("button");
    nextBtn.className = "btn-pager"; nextBtn.textContent = "下一页 →";
    nextBtn.disabled = currentHistoryPage >= totalPages;
    nextBtn.addEventListener("click", () => { if (currentHistoryPage < totalPages) go(currentHistoryPage + 1); });
    leftGroup.appendChild(nextBtn);

    // 右侧：游戏范围信息
    const infoText = document.createElement("span");
    infoText.className = "history-pager-info";
    infoText.textContent = `${startIdx + 1}-${endIdx} / ${total} 款`;

    pagerContainer.appendChild(leftGroup);
    pagerContainer.appendChild(infoText);
    weeklyHistoryGrid.parentNode.insertBefore(pagerContainer, weeklyHistoryGrid.nextSibling);
}

// ============ 渲染历史赠送游戏卡片 ============
// 显示封面、标题、免费时段、原价、游戏描述
function renderHistoryCard(game) {
    const datesHtml = game.end_date
        ? `<div class="game-dates">
               <span class="free">🆓 ${escapeHtml(formatDates(game.week_started_at, game.end_date))}</span>
               <span class="week-tag">${escapeHtml(game.week_id || "")}</span>
           </div>`
        : game.week_started_at
            ? `<div class="game-dates">
                   <span class="free">🆓 ${escapeHtml(formatDate(game.week_started_at))}</span>
                   <span class="week-tag">${escapeHtml(game.week_id || "")}</span>
               </div>`
            : "";
    // 历史卡片：显示该游戏在 Epic 商店的当前售价（如果能查到）
    const priceHtml = game.original_price && game.original_price !== ''
        ? `<div class="game-price-row"><span class="history-current-price">${escapeHtml(game.original_price)}</span></div>`
        : '';

    // 封面：优先使用真实封面（onerror 兑底为渐变封面），无封面时用渐变封面
    // 走本地代理 /api/cover-proxy，避免国内访问 cdn1.epicgames.com 超时
    const coverSrc = proxyCoverUrl(game.image_url);
    const cover = game.image_url
        ? `<img class="game-cover" src="${escapeHtml(coverSrc)}" alt="${escapeHtml(game.title)}" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="onCoverError(this, '${escapeHtml(game.title).replace(/'/g, "\\'")}', '已赠送')">`
        : renderGeneratedCover(game.title, "已赠送");

    // 过滤占位描述（如 "已赠送 · 历史免费游戏"）
    const description = cleanDescription(game.description);

    // 运行平台角标（PC / Android / iOS）
    const platform = getGamePlatform(game);
    const platformBadge = `<span class="game-platform-badge platform-${platform.toLowerCase()}">${escapeHtml(platform)}</span>`;

    // 历史卡片：使用 preview（描边）样式，点击跳到 Epic 商品页
    return `<div class="game-card" data-offer-id="${escapeHtml(game.offer_id)}">${cover}<div class="game-info"><h3 class="game-title game-title-single-line"><span class="game-title-text">${escapeHtml(game.title)}</span>${platformBadge}</h3>${datesHtml}${priceHtml}${description ? `<div class="game-description">${escapeHtml(description)}</div>` : `<div class="game-description game-description-empty">&nbsp;</div>`}<div class="game-actions"><a class="btn-claim-card preview" href="${escapeHtml(game.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">查看详情</a></div></div></div>`;
}