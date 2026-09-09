// ============ 账号密码模式（备选方案，高级用户） ============
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

setupToggle("save-password", "toggle-save-pwd");

const saveForm = document.getElementById("save-form");
const saveBtn = document.getElementById("save-btn");
const saveBtnText = saveBtn?.querySelector(".btn-text");
const saveBtnSpinner = saveBtn?.querySelector(".btn-spinner");
const saveResult = document.getElementById("save-result");
const deleteBtn = document.getElementById("delete-btn");
const credStatus = document.getElementById("cred-status");
const credStatusText = document.getElementById("cred-status-text");
const quickClaimBtn = document.getElementById("quick-claim-btn");
const quickClaimResult = document.getElementById("quick-claim-result");

if (saveForm) {
    saveForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const username = document.getElementById("save-username").value.trim();
        const password = document.getElementById("save-password").value;

        if (!username || !password) {
            showSaveResult({ success: false, error: "请输入账号和密码" });
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
                body: JSON.stringify({
                    username,
                    password,
                    enable_auto_claim: true,
                }),
            });
            const data = await resp.json();
            if (resp.ok) {
                showSaveResult({
                    success: true,
                    message: "凭证已加密保存（同时启用自动领取）",
                });
                document.getElementById("save-password").value = "";
                await refreshCredentialsStatus();
            } else {
                showSaveResult({ success: false, error: data.detail || "保存失败" });
            }
        } catch (err) {
            showSaveResult({ success: false, error: `网络错误: ${err.message}` });
        } finally {
            saveBtn.disabled = false;
            saveBtnText.hidden = false;
            saveBtnSpinner.hidden = true;
        }
    });
}

if (deleteBtn) {
    deleteBtn.addEventListener("click", async () => {
        if (!confirm("确定删除已保存的凭证吗？\n删除后自动领取将停止。")) return;
        try {
            const resp = await fetch("/api/credentials", { method: "DELETE" });
            const data = await resp.json();
            if (resp.ok) {
                showSaveResult({ success: true, message: "凭证已删除" });
                await refreshCredentialsStatus();
            } else {
                showSaveResult({ success: false, error: data.detail || "删除失败" });
            }
        } catch (err) {
            showSaveResult({ success: false, error: `网络错误: ${err.message}` });
        }
    });
}

// 立即领取（用账号密码 - 浏览器模式）
if (quickClaimBtn) {
    quickClaimBtn.addEventListener("click", async () => {
        const username = document.getElementById("save-username").value.trim();
        const password = document.getElementById("save-password").value;
        if (!username || !password) {
            showQuickClaimResult({ error: "请先填写账号和密码" });
            return;
        }
        const claimId = "quick-" + Date.now();
        quickClaimBtn.disabled = true;
        quickClaimResult.hidden = true;
        try {
            const resp = await fetch("/api/claim", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password, verification_code: "" }),
            });
            const data = await resp.json();
            if (resp.ok) {
                showQuickClaimResult({ success: true, message: `领取任务已启动 (ID: ${claimId})` });
                // 轮询进度
                pollQuickClaimProgress(claimId);
            } else {
                showQuickClaimResult({ error: data.detail || "领取失败" });
            }
        } catch (err) {
            showQuickClaimResult({ error: `网络错误: ${err.message}` });
        } finally {
            quickClaimBtn.disabled = false;
        }
    });
}

async function pollQuickClaimProgress(claimId) {
    // 简化：用 setInterval 查
    const maxTries = 120;
    for (let i = 0; i < maxTries; i++) {
        await new Promise(r => setTimeout(r, 2000));
        try {
            const resp = await fetch(`/api/claim/progress/${claimId}`);
            if (resp.status === 404) continue;
            const data = await resp.json();
            if (data.status === "done") {
                if (data.result) {
                    const r = data.result;
                    const cls = r.success ? "success" : "failed";
                    const gamesHtml = (r.games || []).map(g => {
                        const icon = g.status === "claimed" ? "✅" : g.status === "already_claimed" ? "🔁" : "❌";
                        return `<li>${icon} ${escapeHtml(g.title)} — ${escapeHtml(g.message || g.status)}</li>`;
                    }).join("");
                    quickClaimResult.className = `result ${cls}`;
                    quickClaimResult.innerHTML = `
                        <div class="result-title">${r.success ? "✅ 领取完成" : "❌ 领取失败"}</div>
                        ${r.error ? `<div class="result-error">${escapeHtml(r.error)}</div>` : ""}
                        ${gamesHtml ? `<ul>${gamesHtml}</ul>` : ""}
                    `;
                    quickClaimResult.hidden = false;
                    // 清空密码输入
                    document.getElementById("save-password").value = "";
                }
                return;
            }
        } catch (err) {
            console.warn("进度查询失败:", err);
        }
    }
}

function showSaveResult(data) {
    if (!saveResult) return;
    saveResult.hidden = false;
    saveResult.className = `result ${data.success ? "success" : "failed"}`;
    saveResult.innerHTML = `<div class="result-title">${data.success ? "✓ " : "❌ "}${escapeHtml(data.message || data.error || "")}</div>`;
}

function showQuickClaimResult(data) {
    if (!quickClaimResult) return;
    quickClaimResult.hidden = false;
    quickClaimResult.className = `result ${data.error ? "failed" : "success"}`;
    quickClaimResult.innerHTML = `<div class="result-title">${escapeHtml(data.message || data.error || "完成")}</div>`;
}

async function refreshCredentialsStatus() {
    try {
        const resp = await fetch("/api/credentials/status");
        const data = await resp.json();
        if (credStatus && credStatusText) {
            if (data.configured) {
                credStatus.classList.add("configured");
                credStatus.classList.remove("empty");
                credStatusText.innerHTML = `✓ 已配置账号密码凭证 (${data.file_size || "?"} bytes)`;
                if (deleteBtn) deleteBtn.hidden = false;
                document.getElementById("save-username").value = "";
                document.getElementById("save-password").value = "";
            } else {
                credStatus.classList.remove("configured");
                credStatus.classList.add("empty");
                credStatusText.innerHTML = "⚠ 未配置账号密码凭证";
                if (deleteBtn) deleteBtn.hidden = true;
            }
        }
    } catch (err) {
        console.error("凭证状态刷新失败:", err);
    }
}

// 页面加载时初始化
refreshCredentialsStatus();
