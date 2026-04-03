// AI.me MUD Terminal Client
const API = window.location.origin;
let token = localStorage.getItem('aime_token');
let ws = null;
let commandHistory = [];
let historyIndex = -1;
let streamBuffer = '';
let waitingForResponse = false;
let reconnectAttempts = 0;
let reconnectTimer = null;
const MAX_RECONNECT_ATTEMPTS = 10;

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
        // First verify the token is still valid (player exists)
        const authRes = await fetch(`${API}/api/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` },
        });
        if (!authRes.ok) {
            // Token invalid or player deleted (Render restart wiped DB)
            logout();
            return;
        }

        const res = await fetch(`${API}/api/entity/me`, {
            headers: { 'Authorization': `Bearer ${token}` },
        });
        if (res.ok) {
            showTerminal();
        } else if (res.status === 401) {
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

let isReconnecting = false;

function connectWS() {
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }

    // Close existing connection cleanly
    if (ws) {
        try { ws.close(); } catch {}
        ws = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws?token=${token}`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        const wasReconnecting = isReconnecting;
        reconnectAttempts = 0;
        isReconnecting = false;
        appendOutput('system', wasReconnecting ? '重新连接成功。' : '连接已建立。');
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            // Handle server ping — reply with pong
            if (msg.type === 'ping') {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'pong' }));
                }
                return;
            }
            handleMessage(msg);
        } catch {
            appendOutput('narrative', event.data);
        }
    };

    ws.onclose = (event) => {
        // Code 4002 = account deleted (Render restart wiped DB)
        if (event.code === 4002) {
            appendOutput('error', '账号数据已丢失（服务器重启），请重新注册。');
            logout();
            return;
        }
        // Code 4001 = auth failed
        if (event.code === 4001) {
            appendOutput('error', '认证失败，请重新登录。');
            logout();
            return;
        }
        scheduleReconnect();
    };

    ws.onerror = () => {
        // onclose will fire after onerror, reconnect handled there
    };
}

function scheduleReconnect() {
    if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        appendOutput('error', '连接已断开，无法重连。请刷新页面。');
        return;
    }
    isReconnecting = true;
    // Exponential backoff: 1s, 2s, 4s, 8s... capped at 15s
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 15000);
    reconnectAttempts++;
    appendOutput('system', `连接断开，${(delay / 1000).toFixed(0)}秒后重连... (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);
    reconnectTimer = setTimeout(() => {
        if (token && !document.getElementById('terminal-screen').classList.contains('hidden')) {
            connectWS();
        }
    }, delay);
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

function highlightEntityText(text) {
    // Cultivation keywords to highlight
    const keywords = [
        '聚变度', '聚变', '魂念力', '修炼', '念体', '投喂', '论道', '切磋',
        '飞升', '渡劫', '天劫', '凝念', '本心', '灵魂', '境界', '突破',
        '觉醒', '顿悟', '悟道', '道心', '心法', '功法', '灵力', '元气',
        '天道', '大道', '因果', '轮回', '造化', '气运', '机缘', '劫难',
        '认知对齐', '认知深度', '知行一致', '自洽度',
    ];
    const kwPattern = keywords.map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');

    // Build combined regex: Chinese quotes「」, 【】brackets, **bold**, numbers/stats, keywords
    const regex = new RegExp(
        '(「[^」]+」)' +                     // Chinese quotes
        '|(【[^】]+】)' +                    // Square brackets
        '|(\\*\\*[^*]+\\*\\*)' +             // **bold** markdown
        '|(\\b\\d+(?:\\.\\d+)?%?)' +         // numbers like 0.523, 42, 85%
        '|(' + kwPattern + ')',              // cultivation keywords
        'g'
    );

    return text.replace(regex, (match, quote, bracket, bold, number, keyword) => {
        if (quote) return `<span class="hl-quote">${quote}</span>`;
        if (bracket) return `<span class="hl-bracket">${bracket}</span>`;
        if (bold) return `<span class="hl-emphasis">${bold.slice(2, -2)}</span>`;
        if (number) return `<span class="hl-number">${number}</span>`;
        if (keyword) return `<span class="hl-keyword">${keyword}</span>`;
        return match;
    });
}

function appendOutput(style, text) {
    const output = document.getElementById('terminal-output');
    const line = document.createElement('div');
    line.className = `msg-${style}`;
    if (style === 'entity') {
        line.innerHTML = highlightEntityText(escapeHtml(text));
    } else {
        line.textContent = text;
    }
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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
    streamEl.innerHTML = highlightEntityText(escapeHtml(text));
    output.scrollTop = output.scrollHeight;
}

let waitingAnimFrame = null;
let waitingStartTime = 0;

function showWaitingBar() {
    hideWaitingBar();
    waitingForResponse = true;
    waitingStartTime = performance.now();

    const output = document.getElementById('terminal-output');
    const container = document.createElement('div');
    container.id = 'waiting-indicator';

    const canvas = document.createElement('canvas');
    canvas.id = 'waiting-canvas';
    canvas.height = 24;
    container.appendChild(canvas);

    output.appendChild(container);
    output.scrollTop = output.scrollHeight;

    // Set canvas width after DOM insertion (match CSS constrained size)
    canvas.width = Math.min(canvas.offsetWidth || 340, 340);

    animateWaiting(canvas);
}

function animateWaiting(canvas) {
    const ctx = canvas.getContext('2d');
    const W = canvas.width;
    const H = canvas.height;

    function draw() {
        if (!waitingForResponse) return;
        const t = (performance.now() - waitingStartTime) / 1000; // seconds

        ctx.clearRect(0, 0, W, H);

        // === Row 1: Animated text (y=12) ===
        const symbols = ['☰','☱','☲','☳','☴','☵','☶','☷'];
        const symIdx = Math.floor(t * 3) % symbols.length;
        const sym = symbols[symIdx];

        // Glowing symbol
        ctx.font = '13px "Fira Code", monospace';
        ctx.fillStyle = `rgba(0, 229, 255, ${0.6 + 0.4 * Math.sin(t * 4)})`;
        ctx.shadowColor = '#00e5ff';
        ctx.shadowBlur = 8 + 4 * Math.sin(t * 3);
        ctx.fillText(sym, 4, 13);
        ctx.shadowBlur = 0;

        // "念体思考中" with wave color
        const label = '念 体 思 考 中';
        ctx.font = '12px "Fira Code", monospace';
        let x = 24;
        for (let i = 0; i < label.length; i++) {
            const wave = Math.sin(t * 3 + i * 0.5);
            const r = Math.floor(0 + wave * 20);
            const g = Math.floor(200 + wave * 55);
            const b = Math.floor(230 + wave * 25);
            ctx.fillStyle = `rgb(${r},${g},${b})`;
            ctx.fillText(label[i], x, 13);
            x += ctx.measureText(label[i]).width;
        }

        // Animated dots
        const dotCount = Math.floor(t * 2) % 4;
        ctx.fillStyle = '#00ff41';
        ctx.fillText('·'.repeat(dotCount), x + 4, 13);

        // === Row 2: Gentle breathing energy bar (y=18~21) ===
        const barY = 19;
        const barH = 2;

        // Subtle track
        ctx.fillStyle = 'rgba(51,51,51,0.25)';
        ctx.fillRect(4, barY, W - 8, barH);

        // Gentle breathing glow — no fast movement, just a soft pulse
        const breathe = 0.4 + 0.3 * Math.sin(t * 1.2); // slow breath
        const glowW = (W - 8) * (0.3 + 0.15 * Math.sin(t * 0.8)); // pulse width
        const glowX = 4 + ((W - 8) - glowW) * (0.5 + 0.4 * Math.sin(t * 0.5)); // gentle drift

        // Soft glow
        const grad = ctx.createLinearGradient(glowX, 0, glowX + glowW, 0);
        grad.addColorStop(0, 'transparent');
        grad.addColorStop(0.2, `rgba(0,229,255,${breathe * 0.4})`);
        grad.addColorStop(0.5, `rgba(0,255,65,${breathe * 0.5})`);
        grad.addColorStop(0.8, `rgba(0,229,255,${breathe * 0.4})`);
        grad.addColorStop(1, 'transparent');
        ctx.fillStyle = grad;
        ctx.fillRect(glowX, barY, glowW, barH);

        waitingAnimFrame = requestAnimationFrame(draw);
    }

    draw();
}

function hideWaitingBar() {
    waitingForResponse = false;
    if (waitingAnimFrame) {
        cancelAnimationFrame(waitingAnimFrame);
        waitingAnimFrame = null;
    }
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
