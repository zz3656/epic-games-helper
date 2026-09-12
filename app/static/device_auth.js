// ============ 工具函数 + 页面初始化 ============
// 依赖：DOM 就绪后调用 (async function 在 DOMContentLoaded 触发)

let currentWeeklyGames = null;
let currentUpcomingGames = null;

// ============ 用户认证状态 ============
let currentUser = null;  // { username, nickname }
let authToken = null;    // JWT token

// 从 localStorage 恢复 token
function loadAuthToken() {
    try {
        authToken = localStorage.getItem('epic_auth_token');
    } catch(e) {}
}

function saveAuthToken(token) {
    try {
        authToken = token;
        localStorage.setItem('epic_auth_token', token);
    } catch(e) {}
}

function clearAuthToken() {
    try {
        localStorage.removeItem('epic_auth_token');
    } catch(e) {}
    authToken = null;
    currentUser = null;
}

// 带 token 的 fetch（自动附加 Authorization header）
async function fetchWithAuth(url, options = {}) {
    const headers = {
        ...(options.headers || {}),
    };
    if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
    }
    // 不重复设置 Content-Type，让浏览器自动设置（处理 JSON 序列化）
    if (options.body && !headers['Content-Type'] && typeof options.body === 'object') {
        headers['Content-Type'] = 'application/json';
    }
    return fetch(url, { ...options, headers });
}

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
const weeklyPromoSection = document.getElementById("weekly-promo-section");
const weeklyPromoGrid = document.getElementById("weekly-promo-grid");
const weeklyPromoHint = document.getElementById("weekly-promo-hint");
const weeklyHistorySection = document.getElementById("weekly-history-section");
const weeklyHistoryGrid = document.getElementById("weekly-history-grid");

// ============ 调试区 ============
function setDebugOutput(obj) {
    document.getElementById("device-auth-debug-output").textContent = JSON.stringify(obj, null, 2);
}

// ============ 页面加载时初始化 ============
document.addEventListener("DOMContentLoaded", async () => {
    // 设置导航状态
    navStatusDot.classList.add("configured");
    navStatusText.textContent = "已连接";

    // 先初始化认证（加载 token + 用户 UI）
    await initAuth();

    // 直接加载免费游戏、促销和历史
    weeklyFreeSection.hidden = false;
    weeklyPromoSection.hidden = false;
    weeklyHistorySection.hidden = false;
    await loadWeeklyFreeGames();
    // 促销加载改为非阻塞，避免 Epic API 慢导致历史加载被卡住
    loadPromotions().catch(() => {});
    await loadWeeklyHistory();
    // 封面和价格映射会由 loadWeeklyHistory 内的 loadCoverMap + loadPriceMap 并行加载
    // 封面映射会由 loadWeeklyHistory 内的 loadCoverMap 并行加载
});
