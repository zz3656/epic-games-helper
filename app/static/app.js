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
        // 根据登录失败类型显示不同的图标和建议
        const loginStatusMap = {
            invalid_credentials: {
                icon: "🔑",
                title: "账号或密码错误",
                tips: [
                    "请检查账号（邮箱）和密码是否输入正确",
                    "注意区分大小写",
                    "如刚改过密码，请用新密码重试",
                ],
            },
            account_locked: {
                icon: "🚫",
                title: "账号被锁定",
                tips: [
                    "Epic 检测到异常活动已锁定账号",
                    "请前往 https://www.epicgames.com 手动解锁",
                    "或联系 Epic 客服：https://www.epicgames.com/help",
                ],
            },
            rate_limit: {
                icon: "⏱️",
                title: "登录频率超限",
                tips: [
                    "尝试次数过多，请等待 5-15 分钟后再试",
                    "本次领取任务已取消",
                ],
            },
            captcha_required: {
                icon: "🧩",
                title: "需要图形验证码 (hCaptcha)",
                tips: [
                    "Epic 检测到异常环境，弹出 hCaptcha 验证",
                    "点击下方的截图链接查看验证页面",
                    data.vnc_enabled ? "✓ VNC 已启用：新窗口打开 noVNC，手动完成验证" : "⚠ 未启用 VNC：需修改 docker-compose.yml 添加 ENABLE_VNC=true 重启",
                    "⚠ noVNC 黑屏是正常的：只有当领取任务运行时会看到 Chrome，请先点击「开始领取」",
                    "完成后领取任务会自动继续（等待最多 120 秒）",
                ],
                vncLink: data.vnc_enabled ? (window.location.protocol + "//" + window.location.host + "/vnc") : null,
            },
            network_error: {
                icon: "📡",
                title: "网络连接失败",
                tips: [
                    "无法访问 Epic 登录页",
                    "请检查容器网络连接 / DNS 配置",
                    "可能需要配置代理",
                ],
            },
            page_changed: {
                icon: "🔧",
                title: "Epic 登录页结构变化",
                tips: [
                    "Epic 更新了登录页，本项目暂时无法识别",
                    "请前往 GitHub 提交 issue 等待适配",
                ],
            },
            unknown: {
                icon: "❓",
                title: "登录失败，原因未知",
                tips: [
                    "请查看截图了解详情",
                    "可尝试在本地浏览器登录一次以信任本设备",
                ],
            },
        };
        const info = loginStatusMap[data.login_status] || loginStatusMap.unknown;
        const tipsHtml = info.tips.map(t => `• ${escapeHtml(t)}`).join("<br>");
        const vncSection = info.vncLink ? `
            <div class="vnc-cta" style="margin-top:14px; padding:12px; background:rgba(123,47,247,0.15); border-left:3px solid #7b2ff7; border-radius:8px;">
                <div style="font-weight:600; margin-bottom:6px;">🎯 打开嵌入式 noVNC（同一端口 8000）</div>
                <a href="${escapeHtml(info.vncLink)}" target="_blank" style="display:inline-block; padding:8px 14px; background:linear-gradient(90deg,#7b2ff7,#00d4ff); color:#fff; border-radius:8px; text-decoration:none; font-weight:600; font-size:14px;">
                    🖥️ 点击这里打开 noVNC
                </a>
                <div style="margin-top:8px; font-size:12px; opacity:0.8;">URL: ${escapeHtml(info.vncLink)} <strong style="color:#7b2ff7;">（同源 8000 端口）</strong></div>
                <div style="margin-top:6px; font-size:12px; opacity:0.7;">在打开的页面中完成 hCaptcha 后，领取任务会自动继续</div>
            </div>
        ` : (data.login_status === "captcha_required" ? `
            <div class="vnc-cta" style="margin-top:14px; padding:12px; background:rgba(251,191,36,0.15); border-left:3px solid #fbbf24; border-radius:8px;">
                <div style="font-weight:600; margin-bottom:10px;">⚠️ 未启用 VNC，无法手动解决 hCaptcha</div>
                <div style="font-size:13px; line-height:1.8;">
                    <strong>请按以下步骤在服务器上操作（SSH 到服务器后执行）：</strong><br>
                    <div style="margin-top:8px;">
                        <strong>第 1 步：</strong>拉取新镜像（含 VNC 支持）：<br>
                        <code style="display:block; margin:4px 0; padding:6px 8px; background:rgba(0,0,0,0.3); border-radius:4px; font-family:monospace;">docker compose pull</code>
                    </div>
                    <div style="margin-top:8px;">
                        <strong>第 2 步：</strong>编辑 <code>docker-compose.yml</code>，修改 <code>epic-claimer</code> 服务：<br>
                        <code style="display:block; margin:4px 0; padding:6px 8px; background:rgba(0,0,0,0.3); border-radius:4px; font-family:monospace; white-space:pre;">
environment:
  - ENABLE_VNC=true
ports:
  - "8000:8000"
  - "6080:6080"   # 新增 noVNC Web 端口</code>
                    </div>
                    <div style="margin-top:8px;">
                        <strong>第 3 步：</strong>重启容器：<br>
                        <code style="display:block; margin:4px 0; padding:6px 8px; background:rgba(0,0,0,0.3); border-radius:4px; font-family:monospace;">docker compose up -d</code>
                    </div>
                    <div style="margin-top:8px;">
                        <strong>第 4 步：</strong>回到本页面，再次点击「🚀 开始领取」<br>
                    </div>
                    <div style="margin-top:8px;">
                        <strong>第 5 步：</strong>领取失败后，本页面会显示 noVNC 链接，点击在新窗口打开，手动完成 hCaptcha
                    </div>
                </div>
            </div>
        ` : '');
        box.innerHTML = `
            <div class="result-title"><strong>${info.icon} ${escapeHtml(info.title)}</strong></div>
            <div class="result-error">${escapeHtml(data.error || "")}</div>
            <div class="result-hint" style="margin-top:10px;">
                💡 建议：<br>${tipsHtml}
            </div>
            ${vncSection}
            ${data.screenshot_path ? (() => { const fn = escapeHtml(data.screenshot_path.split('/').pop()); return `<div class="result-hint">📸 截图: <a href="/api/screenshots/${fn}" target="_blank" style="color:#00d4ff;">${escapeHtml(data.screenshot_path)}</a> <a href="#" data-toggle-preview="${fn}" style="color:#7b2ff7; margin-left:8px;">[查看/隐藏]</a></div><div class="screenshot-preview" data-preview-for="${fn}" style="margin-top:8px; display:none;"><img src="/api/screenshots/${fn}" style="max-width:100%; border-radius:8px; border:1px solid rgba(255,255,255,0.1);"/></div>`; })() : ''}
        `;
        bindScreenshotToggle(box);
        return;
    }

    // 其他错误（无游戏列表）
    if (data.error && (!data.success && (!data.games || data.games.length === 0))) {
        box.className = "result error";
        box.innerHTML = `
            <div class="result-title"><strong>❌ 领取失败</strong></div>
            <div class="result-error">${escapeHtml(data.error)}</div>
            ${data.screenshot_path ? (() => { const fn = escapeHtml(data.screenshot_path.split('/').pop()); return `<div class="result-hint">📸 截图: <a href="/api/screenshots/${fn}" target="_blank" style="color:#00d4ff;">${escapeHtml(data.screenshot_path)}</a> <a href="#" data-toggle-preview="${fn}" style="color:#7b2ff7; margin-left:8px;">[查看/隐藏]</a></div><div class="screenshot-preview" data-preview-for="${fn}" style="margin-top:8px; display:none;"><img src="/api/screenshots/${fn}" style="max-width:100%; border-radius:8px; border:1px solid rgba(255,255,255,0.1);"/></div>`; })() : ''}
        `;
        bindScreenshotToggle(box);
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
        html += `<div class="result-hint">📸 截图: <a href="/api/screenshots/${filename}" target="_blank" style="color:#00d4ff;">${escapeHtml(data.screenshot_path)}</a> <a href="#" data-toggle-preview="${filename}" style="color:#7b2ff7; margin-left:8px;">[查看/隐藏]</a></div>`;
        html += `<div class="screenshot-preview" data-preview-for="${filename}" style="margin-top:8px; display:none;"><img src="/api/screenshots/${filename}" style="max-width:100%; border-radius:8px; border:1px solid rgba(255,255,255,0.1);"/></div>`;
    }

    box.innerHTML = html;
    bindScreenshotToggle(box);
}

function bindScreenshotToggle(box) {
    box.querySelectorAll('a[data-toggle-preview]').forEach(a => {
        a.addEventListener('click', (e) => {
            e.preventDefault();
            const filename = a.dataset.togglePreview;
            const preview = box.querySelector(`div[data-preview-for="${filename}"]`);
            if (preview) {
                preview.style.display = preview.style.display === 'none' ? 'block' : 'none';
                a.textContent = preview.style.display === 'none' ? '[查看/隐藏]' : '[隐藏]';
            }
        });
    });
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