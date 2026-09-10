// ============ Device Auth 设备码授权主入口 ============
// 拆分说明：
// - device_auth.js（本文件）：设备码授权流程 + 测试按钮 + 页面初始化
// - free_games.js：本周免费游戏 + 下周预告 + 每周赠送记录渲染
// 全局函数/变量通过全局作用域共享（无 ES Modules）

let deviceAuthPollTimer = null;
let currentDeviceCode = null;
let currentWeeklyGames = null;     // 本周免费游戏缓存
let currentUpcomingGames = null;   // 下周预告缓存

// HTML 转义工具函数（全局可用）
function escapeHtml(str) {
    if (typeof str !== 'string') return str;
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// 带超时的 fetch helper（全局可用）
async function fetchWithTimeout(url, timeoutMs = 15000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const resp = await fetch(url, { signal: controller.signal });
        return resp;
    } catch (err) {
        if (err.name === 'AbortError') {
            throw new Error(`请求超时（${timeoutMs / 1000}秒）`);
        }
        throw err;
    } finally {
        clearTimeout(timer);
    }
}

// ============ 元素引用 ============
const startDeviceAuthBtn = document.getElementById("start-device-auth-btn");
const deleteDeviceAuthBtn = document.getElementById("delete-device-auth-btn");
const cancelDeviceAuthBtn = document.getElementById("cancel-device-auth-btn");
const deviceAuthFlow = document.getElementById("device-auth-flow");
const deviceAuthStatus = document.getElementById("device-auth-status");
const deviceCodeValue = document.getElementById("device-code-value");
const verificationUriLink = document.getElementById("verification-uri-link");
const deviceAuthPollMsg = document.getElementById("device-auth-poll-msg");
const deviceAuthResult = document.getElementById("device-auth-result");
const authStatusTag = document.getElementById("auth-status-tag");
const navStatusDot = document.getElementById("nav-status-dot");
const navStatusText = document.getElementById("nav-status-text");
const startDeviceAuthBtnText = startDeviceAuthBtn.querySelector(".btn-text");
const startDeviceAuthBtnSpinner = startDeviceAuthBtn.querySelector(".btn-spinner");

const autoClaimSection = document.getElementById("auto-claim-section");

// 本周免费游戏区域
const weeklyFreeSection = document.getElementById("weekly-free-section");
const weeklyFreeGrid = document.getElementById("weekly-free-grid");
const weeklyFreeHint = document.getElementById("weekly-free-hint");

// 每周赠送记录区域
const weeklyHistorySection = document.getElementById("weekly-history-section");
const weeklyHistoryGrid = document.getElementById("weekly-history-grid");

// 调试
const debugOutput = document.getElementById("device-auth-debug-output");

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
    if (!confirm("确定撤销 Epic 设备授权吗？\n撤销后需要重新授权才能继续追踪免费游戏。")) return;
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

function showDeviceAuthResult(data) {
    deviceAuthResult.hidden = false;
    if (data.success) {
        deviceAuthResult.className = "epic-status configured";
        deviceAuthResult.innerHTML = `
            <span class="epic-status-dot"></span>
            <span><span class="text-success">✓</span> ${escapeHtml(data.message || "成功")}</span>
        `;
    } else {
        deviceAuthResult.className = "device-auth-status-box error";
        deviceAuthResult.innerHTML = `
            <span>⚠️</span>
            <span>${escapeHtml(data.error || "失败")}</span>
        `;
    }
}

// ============ 刷新状态（统一入口） ============
async function refreshDeviceAuthStatus() {
    try {
        const [authResp, autoResp, healthResp] = await Promise.all([
            fetch("/api/device-auth/status"),
            fetch("/api/credentials/status"),
            fetch("/api/health"),
        ]);
        const authData = await authResp.json();
        const autoData = await autoResp.json();
        const healthData = await healthResp.json();

        // 更新定时任务信息
        const nextRunEl = document.getElementById("auto-claim-next-run");
        const notifyEl = document.getElementById("auto-claim-notify");
        if (nextRunEl && healthData.schedule && healthData.schedule.next_run) {
            nextRunEl.textContent = `下次运行：${healthData.schedule.next_run}`;
        }
        if (notifyEl) {
            if (healthData.notify_enabled) {
                notifyEl.innerHTML = `推送状态：<span class="text-success">✓ 已启用（${escapeHtml(healthData.notify_type || '?')}）</span>`;
            } else {
                notifyEl.innerHTML = `推送状态：<span class="text-muted">未配置 webhook（如需推送通知请设置 NOTIFY_WEBHOOK_* 环境变量）</span>`;
            }
        }

        if (authData.device_auth_configured) {
            // 更新顶部导航栏
            if (navStatusDot) navStatusDot.classList.add("configured");
            if (navStatusText) navStatusText.textContent = "已授权";

            // 更新授权状态卡
            deviceAuthStatus.classList.add("configured");
            deviceAuthStatus.classList.remove("empty");
            deviceAuthStatus.innerHTML = `
                <span class="epic-status-dot"></span>
                <span><span class="epic-status-label">已通过 Epic 设备码授权</span> · token 永不过期</span>
            `;
            if (authStatusTag) {
                authStatusTag.textContent = "已授权";
                authStatusTag.classList.add("green");
            }
            deleteDeviceAuthBtn.hidden = false;
            startDeviceAuthBtn.hidden = true;
            autoClaimSection.hidden = false;
            // 显示本周免费游戏 + 每周赠送记录
            weeklyFreeSection.hidden = false;
            weeklyHistorySection.hidden = false;
            loadWeeklyFreeGames();
            loadWeeklyHistory();
        } else {
            // 未授权状态
            if (navStatusDot) navStatusDot.classList.remove("configured");
            if (navStatusText) navStatusText.textContent = "未授权";

            deviceAuthStatus.classList.remove("configured");
            deviceAuthStatus.classList.add("empty");
            deviceAuthStatus.innerHTML = `
                <span class="epic-status-dot"></span>
                <span><span class="epic-status-label">未授权</span> · 请先完成设备码授权</span>
            `;
            if (authStatusTag) {
                authStatusTag.textContent = "未授权";
                authStatusTag.classList.remove("green");
            }
            deleteDeviceAuthBtn.hidden = true;
            startDeviceAuthBtn.hidden = false;
            autoClaimSection.hidden = true;
            weeklyFreeSection.hidden = true;
            weeklyHistorySection.hidden = true;
        }
    } catch (err) {
        console.error("状态刷新失败:", err);
    }
}

// ============ 调试按钮 ============
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

document.getElementById("refresh-weekly-btn").addEventListener("click", async () => {
    debugOutput.textContent = "⏳ 刷新本周免费游戏...";
    await loadWeeklyFreeGames();
    setDebugOutput({ success: true, message: "已刷新" });
});

document.getElementById("test-scheduler-btn").addEventListener("click", async () => {
    if (!confirm("手动触发定时任务（拉取本周免费 + 检测变化 + 写入历史）。继续？")) return;
    debugOutput.textContent = "⏳ 定时任务执行中...";
    try {
        const resp = await fetch("/api/scheduler/test-run", { method: "POST" });
        const data = await resp.json();
        setDebugOutput(data);
    } catch (err) {
        setDebugOutput({ success: false, error: err.message });
    }
});

document.getElementById("test-notify-btn").addEventListener("click", async () => {
    debugOutput.textContent = "⏳ 发送测试推送...";
    try {
        const resp = await fetch("/api/scheduler/test-notify", { method: "POST" });
        const data = await resp.json();
        setDebugOutput(data);
    } catch (err) {
        setDebugOutput({ success: false, error: err.message });
    }
});

// ============ 页面加载时初始化 ============
refreshDeviceAuthStatus();