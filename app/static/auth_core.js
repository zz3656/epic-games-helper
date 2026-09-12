// ============ 用户认证模块 - 核心功能 ============
// 依赖：device_auth.js 提供的 fetchWithAuth / loadAuthToken / saveAuthToken / clearAuthToken / escapeHtml

// ============ 认证相关 DOM 元素 ============
let authModal = null;
let navUserArea = null;
let settingsModal = null;

function initAuthElements() {
    if (!document.getElementById('nav-user-area')) {
        const navStatus = document.querySelector('.epic-nav-status');
        if (navStatus) {
            const userArea = document.createElement('div');
            userArea.id = 'nav-user-area';
            userArea.style.cssText = 'margin-left:16px;display:flex;align-items:center;gap:8px;';
            navStatus.parentNode.insertBefore(userArea, navStatus);
        }
    }
    navUserArea = document.getElementById('nav-user-area');

    if (!document.getElementById('auth-modal')) {
        authModal = createAuthModal();
        document.body.appendChild(authModal);
    }

    if (!document.getElementById('settings-modal')) {
        settingsModal = createSettingsModal();
        document.body.appendChild(settingsModal);
    }
}

// ============ 认证弹窗（登录/注册） ============
function createAuthModal() {
    const modal = document.createElement('div');
    modal.id = 'auth-modal';
    modal.style.display = 'none';
    modal.innerHTML = `
        <div class="modal-overlay" data-close-modal></div>
        <div class="modal-content auth-modal-content">
            <div class="modal-header">
                <h2 id="auth-modal-title">登录</h2>
                <button class="modal-close" data-close-modal>&times;</button>
            </div>
            <div class="modal-body">
                <form id="login-form" style="display:block;">
                    <div class="form-group">
                        <label for="login-username">用户名</label>
                        <input type="text" id="login-username" placeholder="输入用户名" required autocomplete="username" minlength="3" maxlength="32">
                    </div>
                    <div class="form-group">
                        <label for="login-password">密码</label>
                        <input type="password" id="login-password" placeholder="输入密码" required autocomplete="current-password" minlength="6">
                    </div>
                    <div id="login-error" class="form-error" style="display:none;"></div>
                    <button type="submit" class="btn-primary" style="width:100%;margin-top:12px;">登录</button>
                </form>
                <form id="register-form" style="display:none;">
                    <div class="form-group">
                        <label for="reg-username">用户名</label>
                        <input type="text" id="reg-username" placeholder="3-32个字符" required autocomplete="username" minlength="3" maxlength="32">
                    </div>
                    <div class="form-group">
                        <label for="reg-nickname">昵称 <span class="text-muted" style="font-size:12px;">（可选）</span></label>
                        <input type="text" id="reg-nickname" placeholder="留空则使用用户名" autocomplete="name" maxlength="64">
                    </div>
                    <div class="form-group">
                        <label for="reg-password">密码</label>
                        <input type="password" id="reg-password" placeholder="至少6个字符" required autocomplete="new-password" minlength="6">
                    </div>
                    <div id="register-error" class="form-error" style="display:none;"></div>
                    <button type="submit" class="btn-primary" style="width:100%;margin-top:12px;">注册</button>
                </form>
                <div class="auth-switch" style="text-align:center;margin-top:16px;">
                    <span id="auth-switch-text">还没有账号？</span>
                    <a href="#" id="auth-switch-link" style="color:var(--epic-blue);cursor:pointer;">去注册</a>
                </div>
            </div>
        </div>
    `;

    // 登录提交
    modal.querySelector('#login-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const errorEl = modal.querySelector('#login-error');
        errorEl.style.display = 'none';
        const username = modal.querySelector('#login-username').value.trim();
        const password = modal.querySelector('#login-password').value;
        try {
            const resp = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });
            const data = await resp.json();
            if (data.success) {
                saveAuthToken(data.token);
                currentUser = data.user;
                closeModal();
                updateUserUI();
                showToast('登录成功，欢迎 ' + data.user.nickname, 'success');
                location.reload();
            } else {
                errorEl.textContent = data.detail || data.message || '登录失败';
                errorEl.style.display = 'block';
            }
        } catch (err) {
            errorEl.textContent = '网络错误：' + err.message;
            errorEl.style.display = 'block';
        }
    });

    // 注册提交
    modal.querySelector('#register-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const errorEl = modal.querySelector('#register-error');
        errorEl.style.display = 'none';
        const username = modal.querySelector('#reg-username').value.trim();
        const nickname = modal.querySelector('#reg-nickname').value.trim();
        const password = modal.querySelector('#reg-password').value;
        try {
            const resp = await fetch('/api/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password, nickname }),
            });
            const data = await resp.json();
            if (data.success) {
                errorEl.textContent = data.message + '，请切换到登录';
                errorEl.style.display = 'block';
                errorEl.className = 'form-success';
                errorEl.style.color = 'var(--epic-green)';
                setTimeout(() => {
                    modal.querySelector('#register-form').style.display = 'none';
                    modal.querySelector('#login-form').style.display = 'block';
                    modal.querySelector('#auth-switch-text').textContent = '已有账号？';
                    modal.querySelector('#auth-switch-link').textContent = '去登录';
                }, 1500);
            } else {
                errorEl.textContent = data.detail || data.message || '注册失败';
                errorEl.style.display = 'block';
            }
        } catch (err) {
            errorEl.textContent = '网络错误：' + err.message;
            errorEl.style.display = 'block';
        }
    });

    // 切换登录/注册
    modal.querySelector('#auth-switch-link').addEventListener('click', (e) => {
        e.preventDefault();
        const isRegister = modal.querySelector('#register-form').style.display !== 'none';
        if (isRegister) {
            modal.querySelector('#register-form').style.display = 'none';
            modal.querySelector('#login-form').style.display = 'block';
            modal.querySelector('#auth-switch-text').textContent = '还没有账号？';
            modal.querySelector('#auth-switch-link').textContent = '去注册';
            modal.querySelector('#auth-modal-title').textContent = '登录';
        } else {
            modal.querySelector('#login-form').style.display = 'none';
            modal.querySelector('#register-form').style.display = 'block';
            modal.querySelector('#auth-switch-text').textContent = '已有账号？';
            modal.querySelector('#auth-switch-link').textContent = '去登录';
            modal.querySelector('#auth-modal-title').textContent = '注册';
        }
        modal.querySelectorAll('.form-error').forEach(el => { el.style.display = 'none'; el.className = 'form-error'; });
    });

    modal.querySelectorAll('[data-close-modal]').forEach(el => {
        el.addEventListener('click', closeModal);
    });

    return modal;
}

// ============ 弹窗操作 ============
function openAuthModal() {
    initAuthElements();
    authModal.querySelector('#login-username').value = '';
    authModal.querySelector('#login-password').value = '';
    authModal.querySelector('#reg-username').value = '';
    authModal.querySelector('#reg-nickname').value = '';
    authModal.querySelector('#reg-password').value = '';
    authModal.querySelectorAll('.form-error').forEach(el => { el.style.display = 'none'; el.className = 'form-error'; });
    authModal.querySelector('#login-form').style.display = 'block';
    authModal.querySelector('#register-form').style.display = 'none';
    authModal.querySelector('#auth-modal-title').textContent = '登录';
    authModal.style.display = 'flex';
}

function closeModal() {
    authModal.style.display = 'none';
    settingsModal.style.display = 'none';
}
