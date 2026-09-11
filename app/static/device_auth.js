// ============ 工具函数 + 页面初始化 ============
// 依赖：DOM 就绪后调用 (async function 在 DOMContentLoaded 触发)

let currentWeeklyGames = null;
let currentUpcomingGames = null;

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
const navStatusDot = document.getElementById("nav-status-dot");
const navStatusText = document.getElementById("nav-status-text");
const weeklyFreeSection = document.getElementById("weekly-free-section");
const weeklyFreeGrid = document.getElementById("weekly-free-grid");
const weeklyFreeHint = document.getElementById("weekly-free-hint");
const weeklyHistorySection = document.getElementById("weekly-history-section");
const weeklyHistoryGrid = document.getElementById("weekly-history-grid");
const debugOutput = document.getElementById("device-auth-debug-output");

// ============ 调试区 ============
function setDebugOutput(obj) {
    debugOutput.textContent = JSON.stringify(obj, null, 2);
}

document.getElementById("test-free-games-btn").addEventListener("click", async () => {
    debugOutput.textContent = "⏳ 测试中...";
    try {
        const resp = await fetchWithTimeout("/api/free-games");
        const data = await resp.json();
        setDebugOutput(data);
    } catch (err) {
        setDebugOutput({ success: false, error: err.message });
    }
});

document.getElementById("refresh-weekly-btn").addEventListener("click", async () => {
    debugOutput.textContent = "⏳ 刷新中...";
    await loadWeeklyFreeGames();
    setDebugOutput({ success: true, message: "已刷新" });
});

document.getElementById("test-history-btn").addEventListener("click", async () => {
    debugOutput.textContent = "⏳ 刷新中...";
    await loadWeeklyHistory();
    setDebugOutput({ success: true, message: "已刷新" });
});

document.getElementById("test-raw-btn").addEventListener("click", async () => {
    debugOutput.textContent = "⏳ 获取原始数据...";
    try {
        const resp = await fetchWithTimeout("https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions", {
            params: { locale: "zh-CN", country: "CN" },
        });
        const data = await resp.json();
        setDebugOutput(data);
    } catch (err) {
        setDebugOutput({ success: false, error: err.message });
    }
});

// ============ 页面加载时初始化 ============
document.addEventListener("DOMContentLoaded", async () => {
    // 设置导航状态
    navStatusDot.classList.add("configured");
    navStatusText.textContent = "已连接";

    // 直接加载免费游戏和历史
    weeklyFreeSection.hidden = false;
    weeklyHistorySection.hidden = false;
    await loadWeeklyFreeGames();
    await loadWeeklyHistory();
});
