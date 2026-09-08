// ============ 模式 1：立即领取（一次性） ============
// 此文件由浏览器全局加载，使用 app.js 中定义的 escapeHtml

const form = document.getElementById("claim-form");
const submitBtn = document.getElementById("submit-btn");
const btnText = submitBtn.querySelector(".btn-text");
const btnSpinner = submitBtn.querySelector(".btn-spinner");
const resultBox = document.getElementById("result");

let currentClaimId = null;
let pollTimer = null;

form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;
    if (!username || !password) {
        showClaimResult(resultBox, { success: false, error: "请输入账号和密码" });
        return;
    }

    submitBtn.disabled = true;
    btnText.hidden = true;
    btnSpinner.hidden = false;

    currentClaimId = null;
    resultBox.hidden = false;
    resultBox.className = "result progress";
    resultBox.innerHTML = `
        <div class="progress-steps">
            <div class="step-item active">
                <span class="step-icon">⏳</span>
                <span class="step-text">正在提交请求…</span>
            </div>
        </div>
    `;

    try {
        const resp = await fetch("/api/claim", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password }),
        });
        const data = await resp.json();

        if (!resp.ok) {
            showClaimResult(resultBox, { success: false, error: data.detail || "请求失败" });
            submitBtn.disabled = false;
            btnText.hidden = false;
            btnSpinner.hidden = true;
            return;
        }
        currentClaimId = data.claim_id;
        pollProgress(currentClaimId);
    } catch (err) {
        showClaimResult(resultBox, { success: false, error: `网络错误: ${err.message}` });
        submitBtn.disabled = false;
        btnText.hidden = false;
        btnSpinner.hidden = true;
    }
});

function pollProgress(claimId) {
    if (pollTimer) clearTimeout(pollTimer);

    function doPoll() {
        fetch(`/api/claim/progress/${claimId}`)
            .then(resp => {
                if (!resp.ok) {
                    if (resp.status === 404) return fetch(`/api/history/latest`);
                    throw new Error(`HTTP ${resp.status}`);
                }
                return resp.json();
            })
            .then(data => {
                // 需要邮箱验证
                if (data.status === "needs_verification") {
                    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
                    showVerificationPrompt(resultBox, claimId);
                    submitBtn.disabled = false;
                    btnText.hidden = false;
                    btnSpinner.hidden = true;
                    document.getElementById("password").value = "";
                    return;
                }
                if (data.result) {
                    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
                    showClaimResult(resultBox, data.result);
                    submitBtn.disabled = false;
                    btnText.hidden = false;
                    btnSpinner.hidden = true;
                    document.getElementById("password").value = "";
                    loadHistory();
                    return;
                }
                if (data.status === "done") {
                    pollTimer = setTimeout(doPoll, 1000);
                    return;
                }
                updateProgressBox(resultBox, data);
                pollTimer = setTimeout(doPoll, 1500);
            })
            .catch(err => {
                if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
                console.warn("轮询进度出错:", err);
            });
    }

    pollTimer = setTimeout(doPoll, 1000);
}

function updateProgressBox(container, data) {
    container.className = "result progress";
    container.innerHTML = `
        <div class="progress-steps">
            <div class="step-item active">
                <span class="step-icon">⏳</span>
                <span class="step-text">${escapeHtml(data.step || "处理中…")}</span>
            </div>
        </div>
    `;
    container.hidden = false;
}

// ============ 邮箱验证码提示 ============
function showVerificationPrompt(box, claimId) {
    box.hidden = false;
    box.className = "result error";
    box.innerHTML = `
        <div class="result-title"><strong>🔐 需要邮箱验证码</strong></div>
        <div class="result-error">Epic 检测到异常登录，要求邮箱验证。请检查邮箱获取验证码。</div>
        <div class="verification-form" style="margin-top:14px;">
            <label style="display:block; margin-bottom:6px; font-size:13px; color:#cbd5e1;">
                输入邮箱验证码（4-8 位数字）：
            </label>
            <div style="display:flex; gap:8px;">
                <input type="text" id="verification-code-input" maxlength="8"
                       placeholder="123456"
                       style="flex:1; padding:8px 10px; font-size:14px; letter-spacing:4px;
                              background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.12);
                              border-radius:8px; color:#f1f5f9; outline:none;">
                <button id="verification-submit-btn" class="btn-primary" style="width:auto; padding:8px 16px;">
                    提交
                </button>
            </div>
            <div class="result-hint" style="margin-top:10px;">
                💡 提交后请在 60 秒内点击「开始领取」按钮重新触发任务
            </div>
            <div class="result-hint" style="margin-top:6px; opacity:0.7;">
                提示：也可在本地手动登录一次以信任本设备
            </div>
        </div>
    `;

    const input = document.getElementById("verification-code-input");
    const btn = document.getElementById("verification-submit-btn");
    if (!input || !btn) return;

    async function submit() {
        const code = input.value.trim();
        if (!/^\d{4,8}$/.test(code)) {
            alert("请输入正确的验证码（4-8 位数字）");
            return;
        }
        btn.disabled = true;
        btn.textContent = "提交中…";
        try {
            const resp = await fetch("/api/claim/verification", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ claim_id: claimId, code }),
            });
            const data = await resp.json();
            if (resp.ok) {
                box.innerHTML = `
                    <div class="result-title"><strong>✅ 验证码已保存</strong></div>
                    <div class="result-error" style="color:#86efac;">${escapeHtml(data.message)}</div>
                `;
                box.className = "result success";
            } else {
                alert("提交失败: " + (data.detail || "未知错误"));
                btn.disabled = false;
                btn.textContent = "提交";
            }
        } catch (err) {
            alert("网络错误: " + err.message);
            btn.disabled = false;
            btn.textContent = "提交";
        }
    }

    btn.addEventListener("click", submit);
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") submit();
    });
    input.focus();
}