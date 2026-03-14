// AI.me MUD Terminal Client
const API = window.location.origin;
let token = localStorage.getItem('aime_token');
let ws = null;
let commandHistory = [];
let historyIndex = -1;
let streamBuffer = '';
let waitingForResponse = false;

// Extract readable error message from API response
function extractError(data, fallback) {
    if (!data) return fallback;
    if (typeof data.detail === 'string') return data.detail;
    if (Array.isArray(data.detail)) {
        // FastAPI 422 validation errors
        return data.detail.map(e => {
            const field = e.loc && e.loc.length > 1 ? e.loc[e.loc.length - 1] : '';
            const fieldMap = { username: '用户名', password: '密码', display_name: '显示名', name: '念体名号', core_belief: '本心', intent: '修炼意图', first_feed: '初始投喂' };
            const name = fieldMap[field] || field;
            if (e.type === 'string_too_short') return `${name}至少需要${e.ctx?.min_length || ''}个字符`;
            if (e.type === 'string_too_long') return `${name}最多${e.ctx?.max_length || ''}个字符`;
            if (e.type === 'missing') return `请填写${name}`;
            return e.msg || '输入有误';
        }).join('；');
    }
    return fallback;
}

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
            errEl.textContent = extractError(data, '登录失败');
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
            errEl.textContent = extractError(data, '注册失败');
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
        } else if (res.status === 401) {
            // Token invalid/expired — force re-login
            logout();
        } else {
            showEntityCreation();
        }
    } catch {
        showEntityCreation();
    }
}

function logout() {
    token = null;
    localStorage.removeItem('aime_token');
    document.getElementById('auth-screen').classList.remove('hidden');
    document.getElementById('entity-screen').classList.add('hidden');
    document.getElementById('terminal-screen').classList.add('hidden');
    showLogin();
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

    // Start tribulation animation
    startTribulation();

    // Run animation and API call in parallel
    const animPromise = runTribulationSequence();
    const apiPromise = fetch(`${API}/api/entity`, {
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

    try {
        const [, res] = await Promise.all([animPromise, apiPromise]);
        const data = await res.json();
        if (!res.ok) {
            endTribulation(false);
            if (res.status === 401) {
                setTimeout(() => logout(), 2000);
                return;
            }
            setTimeout(() => { errEl.textContent = extractError(data, '创建失败'); }, 2000);
            return;
        }
        endTribulation(true);
        setTimeout(() => showTerminal(), 1500);
    } catch (e) {
        endTribulation(false);
        setTimeout(() => { errEl.textContent = '网络错误'; }, 2000);
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
            // Streaming complete — remove stream element and append final
            hideWaitingBar();
            const streamEl = document.getElementById('stream-line');
            if (streamEl) streamEl.remove();
            if (streamBuffer) {
                appendOutput('entity', streamBuffer);
                streamBuffer = '';
            }
        } else if (content) {
            // First real content — replace waiting bar with streaming display
            hideWaitingBar();
            streamBuffer += content;
            updateStreamDisplay(streamBuffer);
        }
        // Ignore empty streaming init messages — keep waiting bar visible
        return;
    }

    // Non-streaming message — hide waiting bar
    hideWaitingBar();

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

function showWaitingBar() {
    hideWaitingBar(); // remove any existing
    waitingForResponse = true;
    const output = document.getElementById('terminal-output');

    const container = document.createElement('div');
    container.id = 'waiting-indicator';

    const label = document.createElement('div');
    label.className = 'waiting-label';
    label.textContent = '念 体 思 考 中 ···';

    const barTrack = document.createElement('div');
    barTrack.className = 'waiting-bar-container';
    const barBounce = document.createElement('div');
    barBounce.className = 'waiting-bar-bounce';
    barTrack.appendChild(barBounce);

    container.appendChild(label);
    container.appendChild(barTrack);
    output.appendChild(container);
    output.scrollTop = output.scrollHeight;
}

function hideWaitingBar() {
    waitingForResponse = false;
    const el = document.getElementById('waiting-indicator');
    if (el) el.remove();
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
                    showWaitingBar();
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

// ===== Tribulation Animation (化念成劫·渡劫飞升) =====

const TRIB_STAGES = [
    { text: '凝 念 聚 识', sub: 'Gathering consciousness...', duration: 2000, progress: 15 },
    { text: '化 念 成 形', sub: 'Shaping the soul form...', duration: 2000, progress: 30 },
    { text: '念 劫 已 至', sub: 'Tribulation approaching...', duration: 1500, progress: 45, flash: true, stage: 'tribulation' },
    { text: '⚡ 天 劫 降 临 ⚡', sub: 'Lightning tribulation strikes!', duration: 2000, progress: 60, flash: true },
    { text: '念 体 凝 炼', sub: 'Forging the entity...', duration: 2000, progress: 75 },
    { text: '渡 劫 飞 升', sub: 'Ascending through tribulation...', duration: 1500, progress: 90, stage: 'ascension' },
];

let tribParticles = [];
let tribAnimFrame = null;
let tribCanvas, tribCtx;

function startTribulation() {
    const overlay = document.getElementById('tribulation-overlay');
    // Hide all screens so overlay is fully visible
    document.getElementById('auth-screen').classList.add('hidden');
    document.getElementById('entity-screen').classList.add('hidden');
    document.getElementById('terminal-screen').classList.add('hidden');
    overlay.classList.remove('hidden');

    tribCanvas = document.getElementById('tribulation-canvas');
    tribCtx = tribCanvas.getContext('2d');
    tribCanvas.width = window.innerWidth;
    tribCanvas.height = window.innerHeight;

    // Initialize particles
    tribParticles = [];
    for (let i = 0; i < 80; i++) {
        tribParticles.push(createParticle());
    }
    animateParticles();
}

function createParticle() {
    const cx = window.innerWidth / 2;
    const cy = window.innerHeight / 2;
    const angle = Math.random() * Math.PI * 2;
    const dist = 50 + Math.random() * 250;
    return {
        x: cx + Math.cos(angle) * dist,
        y: cy + Math.sin(angle) * dist,
        vx: (Math.random() - 0.5) * 0.5,
        vy: (Math.random() - 0.5) * 0.5,
        size: 1 + Math.random() * 2,
        alpha: 0.2 + Math.random() * 0.6,
        color: ['#00ff41', '#00e5ff', '#ffd700'][Math.floor(Math.random() * 3)],
        angle: angle,
        dist: dist,
        speed: 0.005 + Math.random() * 0.01,
        converging: false,
    };
}

function animateParticles() {
    tribCtx.clearRect(0, 0, tribCanvas.width, tribCanvas.height);
    const cx = tribCanvas.width / 2;
    const cy = tribCanvas.height / 2;

    tribParticles.forEach(p => {
        if (p.converging) {
            // Spiral inward
            p.dist *= 0.98;
            p.angle += p.speed * 3;
            p.x = cx + Math.cos(p.angle) * p.dist;
            p.y = cy + Math.sin(p.angle) * p.dist;
            p.alpha = Math.min(1, p.alpha + 0.01);
        } else {
            // Orbit slowly
            p.angle += p.speed;
            p.x = cx + Math.cos(p.angle) * p.dist;
            p.y = cy + Math.sin(p.angle) * p.dist;
        }

        tribCtx.beginPath();
        tribCtx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        tribCtx.fillStyle = p.color;
        tribCtx.globalAlpha = p.alpha;
        tribCtx.fill();

        // Draw faint line to center
        tribCtx.beginPath();
        tribCtx.moveTo(p.x, p.y);
        tribCtx.lineTo(cx, cy);
        tribCtx.strokeStyle = p.color;
        tribCtx.globalAlpha = p.alpha * 0.08;
        tribCtx.stroke();
    });

    tribCtx.globalAlpha = 1;
    tribAnimFrame = requestAnimationFrame(animateParticles);
}

function triggerFlash() {
    const flash = document.getElementById('trib-flash');
    flash.classList.remove('active');
    void flash.offsetWidth; // force reflow
    flash.classList.add('active');
}

function setTribStage(stageClass) {
    const formation = document.getElementById('trib-formation');
    formation.className = 'trib-formation';
    if (stageClass) formation.classList.add('stage-' + stageClass);
}

async function runTribulationSequence() {
    const stageEl = document.getElementById('trib-stage');
    const subEl = document.getElementById('trib-substage');
    const progressEl = document.getElementById('trib-progress');

    for (const s of TRIB_STAGES) {
        stageEl.textContent = s.text;
        subEl.textContent = s.sub;
        progressEl.style.width = s.progress + '%';
        if (s.flash) triggerFlash();
        if (s.stage) setTribStage(s.stage);
        if (s.stage === 'tribulation') {
            tribParticles.forEach(p => p.converging = true);
        }
        await sleep(s.duration);
    }
}

function endTribulation(success) {
    const stageEl = document.getElementById('trib-stage');
    const subEl = document.getElementById('trib-substage');
    const progressEl = document.getElementById('trib-progress');
    const formation = document.getElementById('trib-formation');

    if (success) {
        progressEl.style.width = '100%';
        stageEl.textContent = '✦ 念 体 诞 生 ✦';
        subEl.textContent = 'Entity successfully created!';
        setTribStage('ascension');
        formation.classList.add('burst');
        triggerFlash();
    } else {
        stageEl.textContent = '渡 劫 失 败';
        subEl.textContent = 'Creation failed. Please try again.';
        stageEl.style.color = 'var(--red)';
    }

    setTimeout(() => {
        if (tribAnimFrame) cancelAnimationFrame(tribAnimFrame);
        document.getElementById('tribulation-overlay').classList.add('hidden');
        // Reset state
        formation.className = 'trib-formation';
        stageEl.style.color = '';
        progressEl.style.width = '0%';
        tribParticles = [];
        // On failure, show entity creation screen again
        if (!success) {
            document.getElementById('entity-screen').classList.remove('hidden');
        }
    }, success ? 1500 : 2000);
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
