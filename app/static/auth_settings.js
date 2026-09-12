// ============ 用户认证模块 - 设置弹窗 ============
// 依赖：auth_core.js 提供的 createAuthModal / closeModal / escapeHtml / fetchWithAuth

function createSettingsModal() {
    const modal = document.createElement('div');
    modal.id = 'settings-modal';
    modal.style.display = 'none';
    modal.innerHTML = `
        <div class="modal-overlay" data-close-modal></div>
        <div class="modal-content settings-modal-content">
            <div class="modal-header">
                <h2>📲 推送设置</h2>
                <button class="modal-close" data-close-modal>&times;</button>
            </div>
            <div class="modal-body">
                <div class="setting-section">
                    <h3>推送渠道</h3>
                    <p class="text-muted" style="font-size:13px;margin:4px 0 12px;">配置后，每周免费游戏更新时会自动推送到你的设备</p>

                    <div class="form-group">
                        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
                            <input type="checkbox" id="push-enabled" style="width:18px;height:18px;cursor:pointer;">
                            <span>启用推送</span>
                        </label>
                    </div>

                    <div class="form-group">
                        <label for="push-type">推送渠道</label>
                        <select id="push-type">
                            <option value="">请选择渠道</option>
                            <option value="bark">📱 Bark（iOS 推送）</option>
                            <option value="serverchan">💬 Server 酱（微信）</option>
                            <option value="pushplus">📮 PushPlus（微信/钉钉/飞书/邮件）</option>
                            <option value="telegram">✈️ Telegram Bot</option>
                            <option value="generic">🔗 通用 Webhook</option>
                        </select>
                    </div>

                    <div class="push-config-group" id="config-bark" style="display:none;">
                        <div class="form-group">
                            <label for="push-token">Device Key</label>
                            <input type="text" id="push-token" placeholder="例如：ABC123def456ghi...">
                            <span class="form-help">在 Bark App 中获取</span>
                        </div>
                    </div>

                    <div class="push-config-group" id="config-serverchan" style="display:none;">
                        <div class="form-group">
                            <label for="push-token">SendKey</label>
                            <input type="text" id="push-token" placeholder="例如：SCT123456...">
                            <span class="form-help">在 https://sct.ftqq.com 注册获取</span>
                        </div>
                    </div>

                    <div class="push-config-group" id="config-pushplus" style="display:none;">
                        <div class="form-group">
                            <label for="push-token">Token</label>
                            <input type="text" id="push-token" placeholder="例如：abc123def456...">
                        </div>
                        <div class="form-group">
                            <label for="push-channel">推送方式</label>
                            <select id="push-channel">
                                <option value="wechat">微信</option>
                                <option value="webhook">Webhook</option>
                                <option value="email">邮件</option>
                                <option value="sms">短信</option>
                                <option value="bark">Bark</option>
                                <option value="voice">语音</option>
                            </select>
                        </div>
                    </div>

                    <div class="push-config-group" id="config-telegram" style="display:none;">
                        <div class="form-group">
                            <label for="push-token">Chat ID</label>
                            <input type="text" id="push-token" placeholder="例如：-1001234567890">
                        </div>
                        <div class="form-group">
                            <label for="push-url">Bot Token</label>
                            <input type="text" id="push-url" placeholder="例如：123456:ABC-DEF1234...">
                            <span class="form-help">通过 @BotFather 创建机器人获取</span>
                        </div>
                    </div>

                    <div class="push-config-group" id="config-generic" style="display:none;">
                        <div class="form-group">
                            <label for="push-url">Webhook URL</label>
                            <input type="url" id="push-url" placeholder="例如：https://your-server.com/webhook">
                        </div>
                    </div>

                    <div id="push-error" class="form-error" style="display:none;"></div>
                    <div style="display:flex;gap:8px;margin-top:16px;">
                        <button type="button" id="save-push-btn" class="btn-primary" style="flex:1;">保存配置</button>
                        <button type="button" id="test-push-btn" class="btn-secondary" style="flex:1;">测试推送</button>
                    </div>
                </div>

                <div class="setting-section" style="margin-top:24px;padding-top:24px;border-top:1px solid var(--epic-border);">
                    <h3>账号管理</h3>
                    <button type="button" id="logout-btn" class="btn-danger" style="margin-top:12px;">退出登录</button>
                </div>
            </div>
        </div>
    `;

    // 渠道切换
    modal.querySelector('#push-type').addEventListener('change', () => {
        modal.querySelectorAll('.push-config-group').forEach(el => el.style.display = 'none');
        const cg = modal.querySelector('#config-' + modal.querySelector('#push-type').value);
        if (cg) cg.style.display = 'block';
    });

    // 保存
    modal.querySelector('#save-push-btn').addEventListener('click', async () => {
        const errorEl = modal.querySelector('#push-error');
        errorEl.style.display = 'none';
        const pushType = modal.querySelector('#push-type').value;
        if (!pushType && modal.querySelector('#push-enabled').checked) {
            errorEl.textContent = '请先选择推送渠道';
            errorEl.style.display = 'block';
            return;
        }
        const config = {
            enabled: modal.querySelector('#push-enabled').checked,
            type: pushType,
            token: (modal.querySelector('#push-token')?.value || '').trim(),
            url: (modal.querySelector('#push-url')?.value || '').trim(),
            channel: (modal.querySelector('#push-channel')?.value || 'wechat'),
        };
        try {
            const resp = await fetchWithAuth('/api/auth/push-config', {
                method: 'PUT',
                body: JSON.stringify(config),
            });
            const data = await resp.json();
            if (resp.ok && data.success) {
                showToast('推送配置已保存', 'success');
            } else {
                errorEl.textContent = data.detail || '保存失败';
                errorEl.style.display = 'block';
            }
        } catch (err) {
            errorEl.textContent = '网络错误：' + err.message;
            errorEl.style.display = 'block';
        }
    });

    // 测试
    modal.querySelector('#test-push-btn').addEventListener('click', async () => {
        const errorEl = modal.querySelector('#push-error');
        errorEl.style.display = 'none';
        try {
            const resp = await fetchWithAuth('/api/auth/test-push', { method: 'POST' });
            const data = await resp.json();
            if (resp.ok && data.success) {
                showToast('测试推送已发送', 'success');
            } else {
                errorEl.textContent = data.detail || data.message || '推送失败';
                errorEl.style.display = 'block';
            }
        } catch (err) {
            errorEl.textContent = '网络错误：' + err.message;
            errorEl.style.display = 'block';
        }
    });

    // 登出
    modal.querySelector('#logout-btn').addEventListener('click', () => {
        clearAuthToken();
        currentUser = null;
        updateUserUI();
        showToast('已退出登录', 'success');
        location.reload();
    });

    modal.querySelectorAll('[data-close-modal]').forEach(el => {
        el.addEventListener('click', closeModal);
    });

    // 加载用户推送配置
    modal._loadPushConfig = async function() {
        try {
            const resp = await fetchWithAuth('/api/auth/push-config');
            if (resp.ok) {
                const data = await resp.json();
                modal.querySelector('#push-enabled').checked = data.enabled;
                modal.querySelector('#push-type').value = data.type;
                modal.querySelector('#push-type').dispatchEvent(new Event('change'));
                if (data.type && data.has_token) {
                    const ti = modal.querySelector('#push-token');
                    if (ti) { ti.placeholder = '已有配置（填写将被覆盖）'; ti.required = false; }
                    if (data.type === 'telegram') {
                        const ui = modal.querySelector('#push-url');
                        if (ui) { ui.placeholder = '已有配置（填写将被覆盖）'; ui.required = false; }
                    }
                }
            }
        } catch(e) {}
    };

    return modal;
}

// ============ 用户 UI 更新 ============
function openSettingsModal() {
    initAuthElements();
    settingsModal._loadPushConfig();
    settingsModal.style.display = 'flex';
}

function updateUserUI() {
    initAuthElements();

    if (currentUser) {
        navUserArea.innerHTML = `
            <button id="nav-settings-btn" class="btn-settings" title="推送设置">📲</button>
            <span class="nav-username">${escapeHtml(currentUser.nickname || currentUser.username)}</span>
            <button id="nav-logout-btn" class="btn-logout" title="退出登录">退出</button>
        `;
        navUserArea.querySelector('#nav-settings-btn').addEventListener('click', openSettingsModal);
        navUserArea.querySelector('#nav-logout-btn').addEventListener('click', () => {
            clearAuthToken();
            currentUser = null;
            updateUserUI();
            showToast('已退出登录', 'success');
            location.reload();
        });
    } else {
        navUserArea.innerHTML = `<button id="nav-login-btn" class="btn-login" title="登录/注册">登录</button>`;
        navUserArea.querySelector('#nav-login-btn').addEventListener('click', openAuthModal);
    }
}

// ============ 提示消息 ============
function showToast(message, type = 'info') {
    const old = document.querySelector('.epic-toast');
    if (old) old.remove();
    const toast = document.createElement('div');
    toast.className = 'epic-toast';
    toast.style.cssText = `
        position:fixed;top:80px;right:24px;padding:12px 20px;border-radius:8px;
        background:${type === 'success' ? 'var(--epic-green)' : type === 'error' ? 'var(--epic-red)' : 'var(--epic-blue)'};
        color:#fff;font-size:14px;z-index:10000;box-shadow:0 4px 12px rgba(0,0,0,0.3);
        max-width:320px;animation:slideInRight 0.3s ease;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ============ 初始化认证 ============
async function initAuth() {
    loadAuthToken();
    initAuthElements();
    if (!authToken) { updateUserUI(); return; }
    try {
        const resp = await fetchWithAuth('/api/auth/me');
        if (resp.ok) {
            const data = await resp.json();
            if (data.authenticated && data.user) {
                currentUser = data.user;
                updateUserUI();
                return;
            }
        }
    } catch(e) {}
    clearAuthToken();
    updateUserUI();
}
