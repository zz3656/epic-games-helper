// ============ Device Auth 设备码授权 ============
let deviceAuthPollTimer = null;
let currentDeviceCode = null;

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

// 启动设备码授权
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

        // 开始轮询（每 3 秒）
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

// 轮询 device auth 状态
async function pollDeviceAuth(deviceCode) {
    try {
        const resp = await fetch(`/api/device-auth/poll/${encodeURIComponent(deviceCode)}`);
        const data = await resp.json();
        const status = data.status;

        if (status === "success") {
            // 用户完成授权
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
        } else {
            // pending - 更新等待消息
            if (data.user_code && verificationUriLink.href === "#") {
                verificationUriLink.href = data.verification_uri_complete;
            }
        }
    } catch (err) {
        console.warn("轮询失败:", err);
    }
}

// 取消授权
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

// 撤销已保存的 device auth
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

// 刷新 device auth 状态
async function refreshDeviceAuthStatus() {
    try {
        const resp = await fetch("/api/device-auth/status");
        const data = await resp.json();
        if (data.device_auth_configured) {
            deviceAuthStatus.classList.add("configured");
            deviceAuthStatus.classList.remove("empty");
            deviceAuthStatusText.innerHTML = "✓ 已通过 Epic 设备码授权（永不过期）";
            deleteDeviceAuthBtn.hidden = false;
            startDeviceAuthBtn.hidden = true;
        } else {
            deviceAuthStatus.classList.remove("configured");
            deviceAuthStatus.classList.add("empty");
            deviceAuthStatusText.innerHTML = "⚠ 未授权（每周需要手动重新登录）";
            deleteDeviceAuthBtn.hidden = true;
            startDeviceAuthBtn.hidden = false;
        }
    } catch (err) {
        console.error("Device auth 状态刷新失败:", err);
    }
}

// 显示结果
function showDeviceAuthResult(data) {
    deviceAuthResult.hidden = false;
    deviceAuthResult.className = `result ${data.success ? "success" : "failed"}`;
    if (data.success) {
        deviceAuthResult.innerHTML = `
            <div class="result-title">✓ ${escapeHtml(data.message || "成功")}</div>
        `;
    } else {
        deviceAuthResult.innerHTML = `
            <div class="result-title">❌ ${escapeHtml(data.error || "失败")}</div>
        `;
    }
}

// 页面加载时初始化
refreshDeviceAuthStatus();

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
