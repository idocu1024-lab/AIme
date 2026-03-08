// AI.me MUD Terminal Client
const API = window.location.origin;
let token = localStorage.getItem('aime_token');
let ws = null;
let commandHistory = [];
let historyIndex = -1;
let streamBuffer = '';

// ===== Auth =====

function showRegister() {
    document.getElementById('login-form').classList.add('hidden');
    document.getElementById('register-form').classList.remove('hidden');
}

function showLogin() {
    document.getElementById('register-form').classList.add('hidden');
    document.getElementById('login-form').classList.remove('hidden');
}

async function doLogin() {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const errEl = document.getElementById('login-error');
    errEl.textContent = '';

    if (!username || !password) {
        errEl.textContent = '请输入用户名和密码';
        return;
    }

    try {
        const res = await fetch(`${API}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        const data = await res.json();
        if (!res.ok) {
            errEl.textContent = data.detail || '登录失败';
            return;
        }
        token = data.access_token;
        localStorage.setItem('aime_token', token);
        await checkEntityAndProceed();
    } catch (e) {
        errEl.textContent = '网络错误';
    }
}

async function doRegister() {
    const username = document.getElementById('reg-username').value.trim();
    const display = document.getElementById('reg-display').value.trim();
    const password = document.getElementById('reg-password').value;
    const errEl = document.getElementById('reg-error');
    errEl.textContent = '';

    if (!username || !password || !display) {
        errEl.textContent = '请填写所有字段';
        return;
    }

    try {
        const res = await fetch(`${API}/api/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, display_name: display }),
        });
        const data = await res.json();
        if (!res.ok) {
            errEl.textContent = data.detail || '注册失败';
            return;
        }
        token = data.access_token;
        localStorage.setItem('aime_token', token);
        await checkEntityAndProceed();
    } catch (e) {
        errEl.textContent = '网络错误';
    }
}

async function checkEntityAndProceed() {
    try {
        const res = await fetch(`${API}/api/entity/me`, {
            headers: { 'Authorization': `Bearer ${token}` },
        });
        if (res.ok) {
            showTerminal();
        } else {
            showEntityCreation();
        }
    } catch {
        showEntityCreation();
    }
}

function showEntityCreation() {
    document.getElementById('auth-screen').classList.add('hidden');
    document.getElementById('entity-screen').classList.remove('hidden');
    document.getElementById('terminal-screen').classList.add('hidden');
}

async function createEntity() {
    const name = document.getElementById('entity-name').value.trim();
    const belief = document.getElementById('entity-belief').value.trim();
    const intent = document.getElementById('entity-intent').value.trim();
    const feed = document.getElementById('entity-feed').value.trim();
    const errEl = document.getElementById('entity-error');
    errEl.textContent = '';

    if (!name || !belief || !intent || !feed) {
        errEl.textContent = '请填写所有字段';
        return;
    }

    try {
        const res = await fetch(`${API}/api/entity`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
            },
            body: JSON.stringify({
                name,
                core_belief: belief,
                intent,
                first_feed: feed,
            }),
        });
        const data = await res.json();
        if (!res.ok) {
            errEl.textContent = data.detail || '创建失败';
            return;
        }
        showTerminal();
    } catch (e) {
        errEl.textContent = '网络错误';
    }
}

// ===== Terminal =====

function showTerminal() {
    document.getElementById('auth-screen').classList.add('hidden');
    document.getElementById('entity-screen').classList.add('hidden');
    document.getElementById('terminal-screen').classList.remove('hidden');
    connectWS();
    document.getElementById('terminal-input').focus();
}

function connectWS() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws?token=${token}`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        appendOutput('system', '连接已建立。');
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleMessage(msg);
        } catch {
            appendOutput('narrative', event.data);
        }
    };

    ws.onclose = () => {
        appendOutput('error', '连接已断开。刷新页面重新连接。');
    };

    ws.onerror = () => {
        appendOutput('error', '连接错误。');
    };
}

function handleMessage(msg) {
    const type = msg.type;
    const content = msg.content;

    if (type === 'entity_speech' && msg.streaming) {
        if (msg.done) {
            // Streaming complete
            if (streamBuffer) {
                appendOutput('entity', streamBuffer);
                streamBuffer = '';
            }
        } else {
            streamBuffer += content;
            updateStreamDisplay(streamBuffer);
        }
        return;
    }

    const styleMap = {
        'system': 'system',
        'narrative': 'narrative',
        'entity_speech': 'entity',
        'error': 'error',
        'highlight': 'highlight',
        'divider': 'divider',
    };
    const style = styleMap[type] || 'narrative';
    appendOutput(style, content);
}

function appendOutput(style, text) {
    const output = document.getElementById('terminal-output');
    const line = document.createElement('div');
    line.className = `msg-${style}`;
    line.textContent = text;
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
}

function updateStreamDisplay(text) {
    const output = document.getElementById('terminal-output');
    let streamEl = document.getElementById('stream-line');
    if (!streamEl) {
        streamEl = document.createElement('div');
        streamEl.id = 'stream-line';
        streamEl.className = 'msg-entity';
        output.appendChild(streamEl);
    }
    streamEl.textContent = text;
    output.scrollTop = output.scrollHeight;
}

// Input handling
document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('terminal-input');

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const text = input.value.trim();
            if (text) {
                // Show command echo
                appendOutput('narrative', `⟩ ${text}`);
                // Send to server
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ cmd: text }));
                }
                // Update history
                commandHistory.unshift(text);
                if (commandHistory.length > 50) commandHistory.pop();
                historyIndex = -1;
            }
            input.value = '';
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (historyIndex < commandHistory.length - 1) {
                historyIndex++;
                input.value = commandHistory[historyIndex];
            }
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (historyIndex > 0) {
                historyIndex--;
                input.value = commandHistory[historyIndex];
            } else {
                historyIndex = -1;
                input.value = '';
            }
        }
    });

    // Auto-login if token exists
    if (token) {
        checkEntityAndProceed();
    }
});

// Click anywhere to focus input
document.addEventListener('click', (e) => {
    if (document.getElementById('terminal-screen').classList.contains('hidden')) return;
    if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        document.getElementById('terminal-input').focus();
    }
});
