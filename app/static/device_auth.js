// ============ Device Auth 设备码授权 + 整合的"立即领取"和"自动领取" ============
let deviceAuthPollTimer = null;
let currentDeviceCode = null;

// ============ 元素引用 ============
const startDeviceAuthBtn = document.getElementById("start-device-auth-btn");
const deleteDeviceAuthBtn = document.getElementById("delete-device-auth-btn");
const cancelDeviceAuthBtn = document.getElementById("cancel-device-auth-btn");
const deviceAuthFlow = document.getElementById("device-auth-flow");
const deviceAuthStatus = document.getElementById("device-auth-status");
const deviceAuthStatusText = document.getElementById("device-auth-status-text");
const deviceCodeValue = document.getElementById("device-code-value");
const verificationUriLink = document.getElementById("verification-uri-link");
const deviceAuthPollMsg = document.getElementById("device-auth-poll-msg");
const deviceAuthResult = document.getElementById("device-auth-result");
const startDeviceAuthBtnText = startDeviceAuthBtn.querySelector(".btn-text");
const startDeviceAuthBtnSpinner = startDeviceAuthBtn.querySelector(".btn-spinner");

// 整合的"立即领取"和"自动领取"区域
const manualClaimSection = document.getElementById("manual-claim-section");
const autoClaimSection = document.getElementById("auto-claim-section");
const claimNowBtn = document.getElementById("claim-now-btn");
const manualClaimResult = document.getElementById("manual-claim-result");
const autoSwitch = document.getElementById("auto-switch");
const autoStatusText = document.getElementById("auto-status-text");

// 进度轮询定时器
let claimProgressTimer = null;

// 本账号游戏库（仅在已授权时显示）
const accountGamesSection = document.getElementById("account-games-section");
const accountGamesGrid = document.getElementById("account-games-grid");
const accountGamesHint = document.getElementById("account-games-hint");

// ============ 启动设备码授权 ============
startDeviceAuthBtn.addEventListener("click", async () => {
    startDeviceAuthBtn.disabled = true;
    startDeviceAuthBtnText.hidden = true;
    startDeviceAuthBtnSpinner.hidden = false;
    deviceAuthResult.hidden = true;

    try {
        const resp = await fetch("/api/device-auth/request", { method: "POST" });
        const data = await resp.json();
        if (!resp.ok) {
            showDeviceAuthResult({ success: false, error: data.detail || "申请失败" });
            return;
        }

        currentDeviceCode = data.device_code;
        deviceCodeValue.textContent = data.user_code;
        verificationUriLink.href = data.verification_uri_complete || data.verification_uri;
        deviceAuthFlow.hidden = false;
        deviceAuthPollMsg.textContent = "等待你在浏览器完成授权...";

        if (deviceAuthPollTimer) clearInterval(deviceAuthPollTimer);
        deviceAuthPollTimer = setInterval(() => pollDeviceAuth(data.device_code), 3000);
    } catch (err) {
        showDeviceAuthResult({ success: false, error: `网络错误: ${err.message}` });
    } finally {
        startDeviceAuthBtn.disabled = false;
        startDeviceAuthBtnText.hidden = false;
        startDeviceAuthBtnSpinner.hidden = false;  // 注意：这里要 hide
        startDeviceAuthBtnSpinner.hidden = true;
    }
});

// ============ 轮询 device auth 状态 ============
async function pollDeviceAuth(deviceCode) {
    try {
        const resp = await fetch(`/api/device-auth/poll/${encodeURIComponent(deviceCode)}`);
        const data = await resp.json();
        const status = data.status;

        if (status === "success") {
            clearInterval(deviceAuthPollTimer);
            deviceAuthPollTimer = null;
            currentDeviceCode = null;
            deviceAuthFlow.hidden = true;
            showDeviceAuthResult({
                success: true,
                message: `✓ Epic 授权成功！账号 ${data.account_id} 已绑定`,
            });
            await refreshDeviceAuthStatus();
        } else if (status === "expired") {
            clearInterval(deviceAuthPollTimer);
            deviceAuthPollTimer = null;
            currentDeviceCode = null;
            deviceAuthFlow.hidden = true;
            showDeviceAuthResult({ success: false, error: "授权码已过期，请重新申请" });
            await refreshDeviceAuthStatus();
        } else if (status === "error") {
            clearInterval(deviceAuthPollTimer);
            deviceAuthPollTimer = null;
            deviceAuthFlow.hidden = true;
            showDeviceAuthResult({ success: false, error: data.message || "授权失败" });
        }
    } catch (err) {
        console.warn("轮询失败:", err);
    }
}

// ============ 取消授权 ============
cancelDeviceAuthBtn.addEventListener("click", async () => {
    if (deviceAuthPollTimer) clearInterval(deviceAuthPollTimer);
    deviceAuthPollTimer = null;
    if (currentDeviceCode) {
        try {
            await fetch(`/api/device-auth/cancel/${encodeURIComponent(currentDeviceCode)}`, { method: "DELETE" });
        } catch (e) {}
        currentDeviceCode = null;
    }
    deviceAuthFlow.hidden = true;
});

// ============ 撤销已保存的 device auth ============
deleteDeviceAuthBtn.addEventListener("click", async () => {
    if (!confirm("确定撤销 Epic 设备授权吗？\n撤销后需要重新授权才能继续自动领取。")) return;
    try {
        const resp = await fetch("/api/device-auth", { method: "DELETE" });
        if (resp.ok) {
            showDeviceAuthResult({ success: true, message: "设备授权已撤销" });
            await refreshDeviceAuthStatus();
        } else {
            const data = await resp.json();
            showDeviceAuthResult({ success: false, error: data.detail || "撤销失败" });
        }
    } catch (err) {
        showDeviceAuthResult({ success: false, error: `网络错误: ${err.message}` });
    }
});

// ============ 立即领取（设备码已授权时） ============
claimNowBtn.addEventListener("click", async () => {
    const claimId = "manual-" + Date.now();
    claimNowBtn.disabled = true;
    claimNowBtn.querySelector(".btn-text").hidden = true;
    claimNowBtn.querySelector(".btn-spinner").hidden = false;
    manualClaimResult.hidden = true;

    try {
        const resp = await fetch("/api/device-auth/claim-now", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ claim_id: claimId }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            showManualClaimResult({ error: data.detail || "领取失败" });
            return;
        }

        // 开始轮询进度
        if (claimProgressTimer) clearInterval(claimProgressTimer);
        claimProgressTimer = setInterval(() => pollClaimProgress(claimId), 2000);
        // 立即查一次
        pollClaimProgress(claimId);
    } catch (err) {
        showManualClaimResult({ error: `网络错误: ${err.message}` });
    }
});

async function pollClaimProgress(claimId) {
    try {
        const resp = await fetch(`/api/claim/progress/${claimId}`);
        if (resp.status === 404) {
            clearInterval(claimProgressTimer);
            claimProgressTimer = null;
            showManualClaimResult({ error: "任务不存在或已过期" });
            claimNowBtn.disabled = false;
            claimNowBtn.querySelector(".btn-text").hidden = false;
            claimNowBtn.querySelector(".btn-spinner").hidden = true;
            return;
        }
        const data = await resp.json();
        // 显示进度
        let progressHtml = `<div class="result-title">⏳ ${escapeHtml(data.step || "处理中...")}</div>`;
        if (data.status === "done") {
            clearInterval(claimProgressTimer);
            claimProgressTimer = null;
            claimNowBtn.disabled = false;
            claimNowBtn.querySelector(".btn-text").hidden = false;
            claimNowBtn.querySelector(".btn-spinner").hidden = true;
            if (data.result) {
                const r = data.result;
                let gamesHtml = "";
                if (r.games && r.games.length > 0) {
                    gamesHtml = "<ul>" + r.games.map(g => {
                        let icon = "❌";
                        if (g.status === "claimed") icon = "✅";
                        else if (g.status === "already_claimed") icon = "🔁";
                        else if (g.status === "needs_manual") icon = "👉";
                        let msg = escapeHtml(g.message || g.status);
                        // needs_manual 状态下，message 中包含 URL，解析出来
                        if (g.status === "needs_manual" && g.message) {
                            const urlMatch = g.message.match(/https?:\/\/[^\s>"']+/);
                            const url = urlMatch ? urlMatch[0] : '';
                            msg = `<a href="${escapeHtml(url)}" target="_blank" style="color:#0078f2">点击领取 ${escapeHtml(g.title)}</a>`;
                        }
                        return `<li>${icon} ${escapeHtml(g.title)} — ${msg}</li>`;
                    }).join("") + "</ul>";
                }
                const cls = r.success ? "success" : "failed";
                progressHtml = `
                    <div class="result-title">${r.success ? "✅ 领取完成" : "❌ 领取失败"}</div>
                    ${r.error ? `<div class="result-error">${escapeHtml(r.error)}</div>` : ""}
                    ${gamesHtml}
                `;
                manualClaimResult.className = `result ${cls}`;
            } else if (data.step) {
                manualClaimResult.className = `result failed`;
                progressHtml = `<div class="result-title">${escapeHtml(data.step)}</div>`;
            }
            // 刷新历史
            loadHistory();
        } else {
            manualClaimResult.className = `result info`;
        }
        manualClaimResult.innerHTML = progressHtml;
        manualClaimResult.hidden = false;
    } catch (err) {
        console.warn("进度轮询失败:", err);
    }
}

function showManualClaimResult(data) {
    manualClaimResult.hidden = false;
    manualClaimResult.className = `result ${data.error ? "failed" : "success"}`;
    manualClaimResult.innerHTML = `<div class="result-title">${escapeHtml(data.error || "完成")}</div>`;
    claimNowBtn.disabled = false;
    claimNowBtn.querySelector(".btn-text").hidden = false;
    claimNowBtn.querySelector(".btn-spinner").hidden = true;
}

// ============ 自动领取开关 ============
autoSwitch.addEventListener("change", async () => {
    const enabled = autoSwitch.checked;
    try {
        const resp = await fetch("/api/auto-claim/toggle", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled }),
        });
        const data = await resp.json();
        if (resp.ok) {
            updateAutoStatus(data.auto_claim_enabled);
        } else {
            autoSwitch.checked = !enabled;
            alert(data.detail || "操作失败");
        }
    } catch (err) {
        autoSwitch.checked = !enabled;
        alert(`网络错误: ${err.message}`);
    }
});

function updateAutoStatus(enabled) {
    autoSwitch.checked = enabled;
    autoStatusText.textContent = enabled ? "已启用" : "已关闭";
    autoStatusText.className = `auto-status ${enabled ? "on" : "off"}`;
}

// ============ 刷新状态（统一入口） ============
async function refreshDeviceAuthStatus() {
    try {
        const [authResp, autoResp] = await Promise.all([
            fetch("/api/device-auth/status"),
            fetch("/api/credentials/status"),
        ]);
        const authData = await authResp.json();
        const autoData = await autoResp.json();

        if (authData.device_auth_configured) {
            deviceAuthStatus.classList.add("configured");
            deviceAuthStatus.classList.remove("empty");
            deviceAuthStatusText.innerHTML = "✓ 已通过 Epic 设备码授权（永不过期）";
            deleteDeviceAuthBtn.hidden = false;
            startDeviceAuthBtn.hidden = true;
            // 显示立即领取、自动领取和账号游戏库
            manualClaimSection.hidden = false;
            autoClaimSection.hidden = false;
            accountGamesSection.hidden = false;
            loadAccountGames();
        } else {
            deviceAuthStatus.classList.remove("configured");
            deviceAuthStatus.classList.add("empty");
            deviceAuthStatusText.innerHTML = "⚠ 未授权（每周需要手动重新登录）";
            deleteDeviceAuthBtn.hidden = true;
            startDeviceAuthBtn.hidden = false;
            manualClaimSection.hidden = true;
            autoClaimSection.hidden = true;
            accountGamesSection.hidden = true;
        }
        updateAutoStatus(autoData.auto_claim_enabled);
    } catch (err) {
        console.error("状态刷新失败:", err);
    }
}

function showDeviceAuthResult(data) {
    deviceAuthResult.hidden = false;
    deviceAuthResult.className = `result ${data.success ? "success" : "failed"}`;
    if (data.success) {
        deviceAuthResult.innerHTML = `<div class="result-title">✓ ${escapeHtml(data.message || "成功")}</div>`;
    } else {
        deviceAuthResult.innerHTML = `<div class="result-title">❌ ${escapeHtml(data.error || "失败")}</div>`;
    }
}

// ============ 历史记录 ============
async function loadHistory() {
    try {
        const resp = await fetch("/api/history?limit=10");
        const data = await resp.json();
        const list = document.getElementById("history-list");
        if (!data.items || data.items.length === 0) {
            list.innerHTML = `<p class="hint">暂无记录</p>`;
            return;
        }
        list.innerHTML = data.items.map(item => {
            const cls = item.success ? "success" : "failed";
            const gamesText = (item.games || []).map(g => {
                const icon = g.status === "claimed" ? "✅" : g.status === "already_claimed" ? "🔁" : "❌";
                return `<div>${icon} ${escapeHtml(g.title)} — ${escapeHtml(g.message || g.status)}</div>`;
            }).join("");
            return `
                <div class="history-item ${cls}">
                    <div class="history-time">${escapeHtml(item.started_at || "")}</div>
                    <div class="history-username">${escapeHtml(item.username || "")}</div>
                    ${item.error ? `<div class="history-error">${escapeHtml(item.error)}</div>` : ""}
                    ${gamesText}
                </div>
            `;
        }).join("");
    } catch (err) {
        console.error("加载历史失败:", err);
    }
}

document.getElementById("refresh-history").addEventListener("click", loadHistory);

// ============ 本周免费游戏卡片 ============
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

async function loadAccountGames() {
    if (!accountGamesGrid) return;
    accountGamesHint.textContent = "加载中…";
    try {
        const resp = await fetch("/api/free-games");
        const data = await resp.json();
        if (!data.success) {
            accountGamesGrid.innerHTML = `<div class="empty-state">加载失败：${escapeHtml(data.error || "")}</div>`;
            accountGamesHint.textContent = "加载失败";
            console.error("free-games API 返回失败:", data);
            return;
        }

        const games = data.games || [];
        const ownedGames = games.filter(g => g.already_owned);
        const claimableGames = games.filter(g => !g.already_owned);

        if (games.length === 0) {
            accountGamesGrid.innerHTML = `<div class="empty-state">📭 本周暂无免费游戏</div>`;
            accountGamesHint.textContent = "本周暂无免费游戏";
            return;
        }

        accountGamesHint.textContent = `本周 ${claimableGames.length} 款可领取 · ${ownedGames.length} 款已拥有`;

        accountGamesGrid.innerHTML = games.map(g => {
            const owned = g.already_owned;
            const daysLeft = daysUntilEnd(g.end_date);
            const datesHtml = g.start_date || g.end_date
                ? `<div class="game-dates">
                       🆓 <span class="free">${escapeHtml(formatDates(g.start_date, g.end_date))}</span>
                       ${daysLeft !== null && daysLeft > 0 && daysLeft <= 3
                           ? ` <span class="end-soon">仅剩 ${daysLeft} 天</span>` : ""}
                   </div>`
                : "";
            const priceHtml = g.original_price
                ? `<div class="game-price"><span class="original">${escapeHtml(g.original_price)}</span> <span class="free">免费</span></div>`
                : `<div class="game-price"><span class="free">🆓 免费领取</span></div>`;

            const cover = g.image_url
                ? `<img class="game-cover" src="${escapeHtml(g.image_url)}" alt="${escapeHtml(g.title)}" loading="lazy" onerror="this.outerHTML='<div class=&quot;game-cover-placeholder&quot;>🎮</div>'">`
                : `<div class="game-cover-placeholder">🎮</div>`;

            const badge = owned
                ? `<span class="game-status-badge owned">已拥有</span>`
                : `<span class="game-status-badge free">可领取</span>`;

            const actionBtn = owned
                ? `<button class="btn-claim-card owned" disabled>✅ 已拥有</button>`
                : `<a class="btn-claim-card" href="${escapeHtml(g.checkout_url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">领取</a>`;

            return `
                <div class="game-card ${owned ? "owned" : ""}" data-offer-id="${escapeHtml(g.offer_id)}">
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
    } catch (err) {
        console.error("加载账号游戏库失败:", err);
        accountGamesHint.textContent = "加载失败";
        accountGamesGrid.innerHTML = `<div class="empty-state">加载失败：${escapeHtml(String(err))}</div>`;
    }
}

// ============ 调试按钮 ============
const debugOutput = document.getElementById("device-auth-debug-output");

function setDebugOutput(obj) {
    debugOutput.textContent = JSON.stringify(obj, null, 2);
}

document.getElementById("test-free-games-btn").addEventListener("click", async () => {
    debugOutput.textContent = "⏳ 测试中...";
    try {
        const resp = await fetch("/api/device-auth/test/free-games", { method: "POST" });
        const data = await resp.json();
        setDebugOutput(data);
    } catch (err) {
        setDebugOutput({ success: false, error: err.message });
    }
});

document.getElementById("test-free-games-raw-btn").addEventListener("click", async () => {
    debugOutput.textContent = "⏳ 获取原始数据...";
    try {
        const resp = await fetch("/api/device-auth/test/free-games-raw", { method: "POST" });
        const data = await resp.json();
        setDebugOutput(data);
    } catch (err) {
        setDebugOutput({ success: false, error: err.message });
    }
});

document.getElementById("test-device-code-btn").addEventListener("click", async () => {
    debugOutput.textContent = "⏳ 申请中...";
    try {
        const resp = await fetch("/api/device-auth/test/request", { method: "POST" });
        const data = await resp.json();
        setDebugOutput(data);
    } catch (err) {
        setDebugOutput({ success: false, error: err.message });
    }
});

document.getElementById("test-claim-btn").addEventListener("click", async () => {
    if (!confirm("将使用已保存的 device auth token 测试领取流程（需先完成授权）。继续？")) return;
    debugOutput.textContent = "⏳ 领取中（可能需要几秒）...";
    try {
        const resp = await fetch("/api/device-auth/test/claim", { method: "POST" });
        const data = await resp.json();
        setDebugOutput(data);
    } catch (err) {
        setDebugOutput({ success: false, error: err.message });
    }
});

// 页面加载时初始化
refreshDeviceAuthStatus();
loadHistory();
