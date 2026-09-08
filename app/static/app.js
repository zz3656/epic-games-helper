// ============ 通用工具 ============
function escapeHtml(s) {
    if (!s) return "";
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function setupToggle(inputId, btnId) {
    const input = document.getElementById(inputId);
    const btn = document.getElementById(btnId);
    if (!input || !btn) return;
    btn.addEventListener("click", () => {
        input.type = input.type === "password" ? "text" : "password";
    });
}

setupToggle("password", "toggle-pwd");
setupToggle("save-password", "toggle-save-pwd");

// ============ 模式 2：保存凭证 + 自动领取 ============
const saveForm = document.getElementById("save-form");
const saveBtn = document.getElementById("save-btn");
const saveBtnText = saveBtn.querySelector(".btn-text");
const saveBtnSpinner = saveBtn.querySelector(".btn-spinner");
const saveResult = document.getElementById("save-result");
const deleteBtn = document.getElementById("delete-btn");
const credStatus = document.getElementById("cred-status");
const credStatusText = document.getElementById("cred-status-text");
const autoSwitch = document.getElementById("auto-switch");
const autoStatusText = document.getElementById("auto-status-text");

saveForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("save-username").value.trim();
    const password = document.getElementById("save-password").value;
    const enableAuto = document.getElementById("enable-auto").checked;

    if (!username || !password) {
        showSaveResult(saveResult, { success: false, error: "请输入账号和密码" });
        return;
    }

    saveBtn.disabled = true;
    saveBtnText.hidden = true;
    saveBtnSpinner.hidden = false;
    saveResult.hidden = true;

    try {
        const resp = await fetch("/api/credentials", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password, enable_auto_claim: enableAuto }),
        });
        const data = await resp.json();
        if (resp.ok) {
            showSaveResult(saveResult, {
                success: true,
                message: "凭证已加密保存",
                auto_claim_enabled: data.auto_claim_enabled,
            });
            document.getElementById("save-password").value = "";
            await refreshStatus();
        } else {
            showSaveResult(saveResult, { success: false, error: data.detail || "保存失败" });
        }
    } catch (err) {
        showSaveResult(saveResult, { success: false, error: `网络错误: ${err.message}` });
    } finally {
        saveBtn.disabled = false;
        saveBtnText.hidden = false;
        saveBtnSpinner.hidden = true;
    }
});

deleteBtn.addEventListener("click", async () => {
    if (!confirm("确定删除已保存的凭证吗？\n删除后自动领取将停止。")) return;

    try {
        const resp = await fetch("/api/credentials", { method: "DELETE" });
        const data = await resp.json();
        if (resp.ok) {
            showSaveResult(saveResult, { success: true, message: "凭证已删除" });
            await refreshStatus();
        } else {
            showSaveResult(saveResult, { success: false, error: data.detail || "删除失败" });
        }
    } catch (err) {
        showSaveResult(saveResult, { success: false, error: `网络错误: ${err.message}` });
    }
});

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

// ============ 状态刷新 ============
async function refreshStatus() {
    try {
        const resp = await fetch("/api/credentials/status");
        const data = await resp.json();
        if (data.configured) {
            credStatus.classList.add("configured");
            credStatus.classList.remove("empty");
            credStatusText.innerHTML = `✓ 已配置凭证 (${data.file_size || "?"} bytes)`;
            deleteBtn.hidden = false;
            document.getElementById("save-username").value = "";
            document.getElementById("save-password").value = "";
        } else {
            credStatus.classList.remove("configured");
            credStatus.classList.add("empty");
            credStatusText.innerHTML = "⚠ 未配置凭证";
            deleteBtn.hidden = true;
        }
        updateAutoStatus(data.auto_claim_enabled);
    } catch (err) {
        console.error("状态刷新失败:", err);
    }
}

// ============ 历史记录 ============
document.getElementById("refresh-history").addEventListener("click", loadHistory);

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
            const summary = item.games && item.games.length > 0
                ? `${item.games.length} 款游戏: ${item.games.filter(g => g.status === "claimed").length} 已领取`
                : (item.error || "无游戏");
            return `<div class="history-item ${cls}">
                        <div><strong>${escapeHtml(item.username)}</strong> · ${escapeHtml(summary)}</div>
                        <div class="history-meta">${item.started_at} → ${item.finished_at || "-"}</div>
                     </div>`;
        }).join("");
    } catch (err) {
        console.error("加载历史失败:", err);
    }
}

// ============ 结果显示 ============
function showClaimResult(box, data) {
    box.hidden = false;

    // 登录失败
    if (data.login_failed) {
        box.className = "result error";
        box.innerHTML = `
            <div class="result-title"><strong>🔒 登录失败</strong></div>
            <div class="result-error">${escapeHtml(data.error || "")}</div>
            <div class="result-hint" style="margin-top:10px;">
                💡 请检查：<br>
                • Epic 账号密码是否正确<br>
                • 是否开启了双因素认证<br>
                • Epic 是否要求验证码（需手动登录一次）
            </div>
            ${data.screenshot_path ? `<div class="result-hint">📸 截图: ${escapeHtml(data.screenshot_path)}</div>` : ''}
        `;
        return;
    }

    // 其他错误（无游戏列表）
    if (data.error && (!data.success && (!data.games || data.games.length === 0))) {
        box.className = "result error";
        box.innerHTML = `
            <div class="result-title"><strong>❌ 领取失败</strong></div>
            <div class="result-error">${escapeHtml(data.error)}</div>
            ${data.screenshot_path ? `<div class="result-hint">📸 截图: ${escapeHtml(data.screenshot_path)}</div>` : ''}
        `;
        return;
    }

    // 成功（或有部分失败）
    box.className = `result ${data.success ? "success" : "error"}`;
    let html = `<div class="result-title"><strong>${data.success ? "✅ 任务完成" : "⚠️ 任务完成（有失败）"}</strong></div>`;

    if (data.started_at || data.finished_at) {
        html += `<div class="result-time">
                    开始: ${data.started_at || "-"} | 结束: ${data.finished_at || "-"}
                 </div>`;
    }

    if (data.games && data.games.length > 0) {
        html += `<div class="games-list">`;
        for (const g of data.games) {
            const statusMap = {
                claimed: { cls: "claimed", text: "✅ 已领取" },
                already_claimed: { cls: "already", text: "🔸 已拥有" },
                failed: { cls: "failed", text: "❌ 失败" },
                not_free: { cls: "not_free", text: "⚪ 非免费" },
                not_started: { cls: "not_started", text: "⏳ 未开始免费" },
                pending: { cls: "pending", text: "⏳ 等待中" },
            };
            const s = statusMap[g.status] || { cls: "pending", text: g.status };
            html += `<div class="game-item">
                        <span class="title">${escapeHtml(g.title)}</span>
                        <div class="game-detail">
                            <span class="badge ${s.cls}">${s.text}</span>
                            ${g.message ? `<span class="game-msg">${escapeHtml(g.message)}</span>` : ''}
                        </div>
                     </div>`;
        }
        html += `</div>`;
    } else {
        html += `<div class="result-hint" style="margin-top:8px;">📭 本周暂无免费游戏</div>`;
    }

    if (data.screenshot_path) {
        const filename = escapeHtml(data.screenshot_path.split('/').pop());
        html += `<div class="result-hint">📸 截图: <a href="/api/screenshots/${filename}" target="_blank" style="color:#00d4ff;">${escapeHtml(data.screenshot_path)}</a></div>`;
    }

    box.innerHTML = html;
}

function showSaveResult(box, data) {
    box.hidden = false;
    if (data.success) {
        box.className = "result success";
        box.innerHTML = `<div class="result-title"><strong>✅ ${escapeHtml(data.message)}</strong></div>
            ${data.auto_claim_enabled !== undefined ? `<div class="result-time">自动领取: ${data.auto_claim_enabled ? "已启用" : "未启用"}</div>` : ''}`;
    } else {
        box.className = "result error";
        box.innerHTML = `<div class="result-title"><strong>❌ ${escapeHtml(data.error)}</strong></div>`;
    }
}

// 初始化
refreshStatus();
loadHistory();