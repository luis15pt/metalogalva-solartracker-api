/**
 * Solar Tracker Control - Web UI
 */

const API_BASE = window.location.origin;
let ws = null;
let wsReconnectTimer = null;
let isConnected = false;
let currentMode = 'manual';
let lastUpdateTime = null;

// DOM Elements
const $ = id => document.getElementById(id);
const el = {
    serialStatus: $('serial-status'),
    linkStatus: $('link-status'),
    wsStatus: $('ws-status'),
    wsText: $('ws-text'),
    lastUpdateBadge: $('last-update-badge'),
    portSelect: $('port-select'),
    refreshPortsBtn: $('refresh-ports-btn'),
    connectBtn: $('connect-btn'),
    disconnectBtn: $('disconnect-btn'),
    modeManualBtn: $('mode-manual-btn'),
    modeAutoBtn: $('mode-auto-btn'),
    stopBtn: $('stop-btn'),
    syncClockBtn: $('sync-clock-btn'),
    sunAzimuth: $('sun-azimuth'),
    sunAltitude: $('sun-altitude'),
    posHorizontal: $('pos-horizontal'),
    posVertical: $('pos-vertical'),
    alarmBanner: $('alarm-banner'),
    staleBanner: $('stale-banner'),
    staleText: $('stale-text'),
    alarmList: $('alarm-list'),
    alarmHistory: $('alarm-history'),
    clearAlarmsBtn: $('clear-alarms-btn'),
    resetLimitsBtn: $('reset-limits-btn'),
    maxWindInput: $('max-wind-input'),
    setWindBtn: $('set-wind-btn'),
    zeroBtn: $('zero-btn'),
};

const SWITCH_NAMES = {
    east_limit: 'East limit',
    west_limit: 'West limit',
    horizontal_limit: 'Flat limit',
    vertical_limit: 'Upright limit',
};

// =============================================================================
// API & Helpers
// =============================================================================

async function apiCall(endpoint, method = 'GET', body = null) {
    const options = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) options.body = JSON.stringify(body);
    const response = await fetch(`${API_BASE}${endpoint}`, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'API error');
    return data;
}

async function withLoading(btn, asyncFn) {
    const orig = btn.innerHTML;
    btn.classList.add('loading');
    btn.innerHTML = '<span class="btn-spinner"></span>' + orig;
    btn.disabled = true;
    try { await asyncFn(); } finally {
        btn.classList.remove('loading');
        btn.innerHTML = orig;
        btn.disabled = false;
    }
}

function log(msg) { console.log(`[tracker] ${msg}`); }

// Run an action from a button; show failures instead of swallowing them
function action(btn, fn) {
    return withLoading(btn, async () => {
        try { const r = await fn(); if (r && r.message) log(r.message); }
        catch (e) { alert(e.message); }
    });
}

// =============================================================================
// WebSocket
// =============================================================================

function connectWebSocket() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${proto}//${location.host}/ws`);

    ws.onopen = () => {
        log('WebSocket connected');
        el.wsStatus.classList.remove('reconnecting');
        el.wsStatus.classList.add('connected');
        el.wsText.textContent = 'WS';
        clearTimeout(wsReconnectTimer);
    };

    ws.onclose = () => {
        el.wsStatus.classList.remove('connected');
        el.wsStatus.classList.add('reconnecting');
        el.wsText.textContent = 'WS...';
        wsReconnectTimer = setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = () => {};

    ws.onmessage = (event) => {
        try {
            updateUI(JSON.parse(event.data));
        } catch (e) { console.error(e); }
    };
}

// =============================================================================
// SVG Gauges
// =============================================================================

function initCompassTicks() {
    const g = document.getElementById('compass-ticks');
    if (!g) return;
    for (let deg = 0; deg < 360; deg += 10) {
        const major = deg % 30 === 0;
        const rad = (deg - 90) * Math.PI / 180;
        const r1 = major ? 82 : 87, r2 = 92;
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', 100 + r1 * Math.cos(rad));
        line.setAttribute('y1', 100 + r1 * Math.sin(rad));
        line.setAttribute('x2', 100 + r2 * Math.cos(rad));
        line.setAttribute('y2', 100 + r2 * Math.sin(rad));
        line.setAttribute('stroke', major ? '#a0a0a0' : 'rgba(160,160,160,0.3)');
        line.setAttribute('stroke-width', major ? '1.5' : '0.75');
        g.appendChild(line);
    }
}

function initAltitudeTicks() {
    const g = document.getElementById('altitude-ticks');
    if (!g) return;
    const cx = 100, cy = 105, r = 80;
    for (let alt = 0; alt <= 90; alt += 15) {
        const angle = 180 - alt;
        const rad = angle * Math.PI / 180;
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', cx + (r-5)*Math.cos(rad));
        line.setAttribute('y1', cy - (r-5)*Math.sin(rad));
        line.setAttribute('x2', cx + (r+3)*Math.cos(rad));
        line.setAttribute('y2', cy - (r+3)*Math.sin(rad));
        line.setAttribute('stroke', '#a0a0a0');
        line.setAttribute('stroke-width', '1');
        g.appendChild(line);
        if (alt > 0 && alt < 90) {
            const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            text.setAttribute('x', cx + (r+12)*Math.cos(rad));
            text.setAttribute('y', cy - (r+12)*Math.sin(rad));
            text.setAttribute('fill', '#a0a0a0');
            text.setAttribute('font-size', '8');
            text.setAttribute('text-anchor', 'middle');
            text.setAttribute('dominant-baseline', 'central');
            text.textContent = alt + '\u00B0';
            g.appendChild(text);
        }
    }
}

function initAltitudeTicksBelow() {
    const g = document.getElementById('altitude-ticks-below');
    if (!g) return;
    const cx = 100, cy = 105, r = 85;
    for (let alt = -15; alt >= -45; alt -= 15) {
        const angle = 180 - alt;
        const rad = angle * Math.PI / 180;
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', cx + (r-5)*Math.cos(rad));
        line.setAttribute('y1', cy - (r-5)*Math.sin(rad));
        line.setAttribute('x2', cx + (r+3)*Math.cos(rad));
        line.setAttribute('y2', cy - (r+3)*Math.sin(rad));
        line.setAttribute('stroke', 'rgba(160,160,160,0.4)');
        line.setAttribute('stroke-width', '1');
        g.appendChild(line);
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', cx + (r+14)*Math.cos(rad));
        text.setAttribute('y', cy - (r+14)*Math.sin(rad));
        text.setAttribute('fill', 'rgba(160,160,160,0.5)');
        text.setAttribute('font-size', '7');
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('dominant-baseline', 'central');
        text.textContent = alt + '\u00B0';
        g.appendChild(text);
    }
}

function updateCompass(sunAzi, panelAzi) {
    const sunN = document.getElementById('sun-needle');
    const panelN = document.getElementById('panel-needle');
    // Half compass: pivot at top, 180°=straight down(S), 90°=right(E), 270°=left(W)
    if (sunN && sunAzi !== null) sunN.style.transform = `rotate(${sunAzi}deg)`;
    if (panelN && panelAzi !== null) panelN.style.transform = `rotate(${panelAzi}deg)`;
}

function updateAltitudeGauge(sunAlt, panelVert) {
    const cx = 100, cy = 105, r = 80;

    function toPoint(alt, min) {
        if (alt === null || alt === undefined) return null;
        const c = Math.max(min, Math.min(90, alt));
        const angle = 180 - c;
        const rad = angle * Math.PI / 180;
        return { x: cx + r * Math.cos(rad), y: cy - r * Math.sin(rad) };
    }

    const sunNeedle = document.getElementById('sun-alt-needle');
    const sunDot = document.getElementById('sun-alt-dot');
    const sunGroup = document.getElementById('sun-alt-needle-group');
    const panelNeedle = document.getElementById('panel-alt-needle');

    if (sunNeedle && sunAlt !== null) {
        const pt = toPoint(sunAlt, -45);
        if (pt) {
            sunNeedle.setAttribute('x2', pt.x);
            sunNeedle.setAttribute('y2', pt.y);
            if (sunDot) { sunDot.setAttribute('cx', pt.x); sunDot.setAttribute('cy', pt.y); }
            if (sunGroup) sunGroup.classList.toggle('below-horizon', sunAlt < 0);
        }
    }

    if (panelNeedle && panelVert !== null) {
        const pt = toPoint(panelVert, 0);
        if (pt) { panelNeedle.setAttribute('x2', pt.x); panelNeedle.setAttribute('y2', pt.y); }
    }
}

function updateScene(sunAzi, sunAlt, panelH, panelV) {
    const sun = document.getElementById('scene-sun');
    const glow = document.getElementById('scene-sun-glow');
    const rays = document.getElementById('scene-sun-rays');
    const panel = document.getElementById('scene-panel');
    const shadow = document.getElementById('panel-shadow');
    const highlight = document.getElementById('panel-highlight');
    const stars = document.getElementById('scene-stars');
    const skyTop = document.getElementById('sky-top');
    const skyMid = document.getElementById('sky-mid');
    const skyBottom = document.getElementById('sky-bottom');
    if (!sun || !panel) return;

    // Horizon at y=150. Sky 0-150, ground 150-200.
    // Sun arcs left to right: East(90°)=left(40), South(180°)=center(240), West(270°)=right(440)
    // Map azimuth 60-300° to x 20-460 (visible range)
    let sunX = 300;
    if (sunAzi !== null) {
        // E(90°)=right(460), S(180°)=center(300), W(270°)=left(140)
        // Shifted right to keep sun away from panel on the far left
        sunX = 460 - ((Math.max(90, Math.min(270, sunAzi)) - 90) / 180) * 320;
    }
    // Altitude to Y: 0°=horizon(150), 90°=top(10), -15°=below(185)
    const altClamped = sunAlt !== null ? Math.max(-15, Math.min(90, sunAlt)) : 0;
    const sunY = 150 - (altClamped / 90) * 140;

    const isDay = sunAlt !== null && sunAlt > 0;
    const sunVisible = sunAlt !== null && sunAlt > -8;

    // Sun position + visibility
    const sunOpacity = sunVisible ? Math.min(1, (sunAlt + 8) / 12) : 0;
    sun.setAttribute('cx', sunX);
    sun.setAttribute('cy', sunY);
    sun.setAttribute('opacity', sunOpacity);
    if (glow) {
        glow.setAttribute('cx', sunX);
        glow.setAttribute('cy', sunY);
        glow.setAttribute('opacity', sunVisible ? sunOpacity * 0.7 : 0);
    }
    if (rays) {
        rays.setAttribute('cx', sunX);
        rays.setAttribute('cy', sunY);
        rays.setAttribute('opacity', isDay ? Math.min(0.6, sunAlt / 30) : 0);
    }

    // Stars + moon: visible at night
    if (stars) {
        stars.setAttribute('opacity', sunAlt !== null && sunAlt < -5 ? Math.min(1, (-sunAlt - 5) / 10) : 0);
    }
    const moon = document.getElementById('scene-moon');
    if (moon) {
        moon.setAttribute('opacity', sunAlt !== null && sunAlt < -3 ? Math.min(0.9, (-sunAlt - 3) / 8) : 0);
    }

    // Sky gradient
    if (sunAlt !== null && skyTop && skyMid && skyBottom) {
        if (sunAlt > 15) {
            skyTop.setAttribute('stop-color', '#0e2a4a');
            skyMid.setAttribute('stop-color', '#1e5a8c');
            skyBottom.setAttribute('stop-color', '#5aa0d0');
        } else if (sunAlt > 5) {
            skyTop.setAttribute('stop-color', '#142a4c');
            skyMid.setAttribute('stop-color', '#2a4a6c');
            skyBottom.setAttribute('stop-color', '#c08050');
        } else if (sunAlt > -2) {
            skyTop.setAttribute('stop-color', '#0e1a30');
            skyMid.setAttribute('stop-color', '#2a2a40');
            skyBottom.setAttribute('stop-color', '#b05030');
        } else if (sunAlt > -10) {
            skyTop.setAttribute('stop-color', '#080e1a');
            skyMid.setAttribute('stop-color', '#151a28');
            skyBottom.setAttribute('stop-color', '#4a2828');
        } else {
            skyTop.setAttribute('stop-color', '#040810');
            skyMid.setAttribute('stop-color', '#0a0e18');
            skyBottom.setAttribute('stop-color', '#0e1420');
        }
    }

    // Panel tilt — pivot at (100, 118)
    // panelV is the tilt angle shown on the altitude gauge (0°=horizon, 90°=zenith)
    // Scene panel starts horizontal. Rotate by panelV so visual matches gauge.
    // Positive = CW = right end up, surface faces right towards sun
    // panelV = panel normal angle (raw from tracker). Scene needs surface angle.
    // Surface angle from horizontal = 90 - normal angle
    // raw 90 (flat/stowed) → scene 0° (flat). raw 35 (tracking) → scene 55° (tilted)
    if (panelV !== null) {
        panel.setAttribute('transform', `rotate(${90 - panelV}, 60, 95)`);
    }

    // Panel highlight (reflection when sun is hitting it)
    if (highlight && isDay) {
        highlight.setAttribute('opacity', Math.min(0.25, sunAlt / 60));
    } else if (highlight) {
        highlight.setAttribute('opacity', '0');
    }

    // Shadow on ground — cast from sun direction
    if (shadow) {
        if (isDay && panelV !== null && sunAlt > 2) {
            // Shadow stretches away from the sun
            const shadowLen = Math.max(8, (70 - sunAlt) * 0.6);
            // Sun to the left of panel = shadow goes right, and vice versa
            const panelCX = 60;
            const shadowDir = sunX > panelCX ? 1 : -1;
            const shadowSpread = shadowDir * shadowLen;
            const gY = 160;
            const sY = gY + Math.max(4, 20 - sunAlt * 0.2);
            shadow.setAttribute('points',
                `${25},${gY} ${95},${gY} ` +
                `${95 + shadowSpread},${sY} ${25 + shadowSpread},${sY}`
            );
            shadow.setAttribute('opacity', Math.min(0.35, sunAlt / 25));
        } else {
            shadow.setAttribute('opacity', '0');
        }
    }
}

function updateCompassLimits(hMin, hMax) {
    const g = document.getElementById('compass-limits');
    if (!g) return;
    g.innerHTML = '';
    if (hMin === null && hMax === null) return;
    const cx = 100, cy = 100, r1 = 75, r2 = 93;

    function drawLine(angle) {
        const rad = (angle - 90) * Math.PI / 180;
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', cx + r1*Math.cos(rad));
        line.setAttribute('y1', cy + r1*Math.sin(rad));
        line.setAttribute('x2', cx + r2*Math.cos(rad));
        line.setAttribute('y2', cy + r2*Math.sin(rad));
        line.setAttribute('class', 'limit-marker-line');
        g.appendChild(line);
    }

    if (hMin !== null) drawLine(hMin);
    if (hMax !== null) drawLine(hMax);

    if (hMin !== null && hMax !== null) {
        const rArc = 78;
        const sr = (hMin - 90) * Math.PI / 180;
        const er = (hMax - 90) * Math.PI / 180;
        let sweep = hMax - hMin;
        if (sweep < 0) sweep += 360;
        const arc = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        const sx = cx + rArc*Math.cos(sr), sy = cy + rArc*Math.sin(sr);
        const ex = cx + rArc*Math.cos(er), ey = cy + rArc*Math.sin(er);
        arc.setAttribute('d', `M ${sx} ${sy} A ${rArc} ${rArc} 0 ${sweep > 180 ? 1 : 0} 1 ${ex} ${ey}`);
        arc.setAttribute('class', 'limit-marker-arc');
        g.appendChild(arc);
    }
}

function updateAltitudeLimits(vMin, vMax) {
    const g = document.getElementById('altitude-limits');
    if (!g) return;
    g.innerHTML = '';
    if (vMin === null && vMax === null) return;
    const cx = 100, cy = 105, r = 85;

    function drawTick(alt) {
        const c = Math.max(0, Math.min(90, alt));
        const angle = 180 - c;
        const rad = angle * Math.PI / 180;
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', cx + (r-8)*Math.cos(rad));
        line.setAttribute('y1', cy - (r-8)*Math.sin(rad));
        line.setAttribute('x2', cx + (r+2)*Math.cos(rad));
        line.setAttribute('y2', cy - (r+2)*Math.sin(rad));
        line.setAttribute('class', 'limit-marker-line');
        g.appendChild(line);
    }

    if (vMin !== null) drawTick(vMin);
    if (vMax !== null) drawTick(vMax);

    if (vMin !== null && vMax !== null) {
        const rArc = 80;
        const sa = 180 - Math.max(0, Math.min(90, vMin));
        const ea = 180 - Math.max(0, Math.min(90, vMax));
        const sr = sa * Math.PI / 180, er = ea * Math.PI / 180;
        const arc = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        arc.setAttribute('d', `M ${100 + rArc*Math.cos(sr)} ${105 - rArc*Math.sin(sr)} A ${rArc} ${rArc} 0 ${Math.abs(sa-ea) > 180 ? 1 : 0} 0 ${100 + rArc*Math.cos(er)} ${105 - rArc*Math.sin(er)}`);
        arc.setAttribute('class', 'limit-marker-arc');
        g.appendChild(arc);
    }
}

// =============================================================================
// UI Updates
// =============================================================================

const pad2 = n => String(n).padStart(2, '0');
// Tracker timestamps are UTC without a zone suffix
const asUTC = t => new Date(/Z|[+-]\d\d:\d\d$/.test(t) ? t : t + 'Z');
const fmtUTC = d => `${d.getUTCFullYear()}-${pad2(d.getUTCMonth()+1)}-${pad2(d.getUTCDate())} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`;

function setChip(node, text, cls) {
    node.textContent = text;
    node.className = 'chip' + (cls ? ' ' + cls : '');
}

function updateUI(status) {
    // Connection and link
    isConnected = status.connection?.connected || false;
    const linkOk = !!status.link_ok;
    el.serialStatus.classList.toggle('connected', isConnected);
    el.linkStatus.classList.toggle('connected', linkOk);
    el.connectBtn.disabled = isConnected;
    el.disconnectBtn.disabled = !isConnected;
    lastUpdateTime = status.last_frame ? asUTC(status.last_frame).getTime() : null;

    el.staleBanner.style.display = linkOk ? 'none' : '';
    el.staleText.textContent = !isConnected
        ? 'Serial port not connected. Values below are the last received.'
        : (status.last_frame
            ? 'No data from the tracker. Values below are the last received.'
            : 'Waiting for the first status frame from the tracker.');
    document.body.classList.toggle('stale', !linkOk);

    // Mode: manual controls only work in manual mode
    currentMode = status.mode || 'manual';
    const manual = currentMode === 'manual';
    el.modeManualBtn.classList.toggle('active', manual);
    el.modeAutoBtn.classList.toggle('active', !manual);
    document.querySelector('.controls-col').classList.toggle('locked', !manual);
    document.querySelectorAll('#dpad button, #presets button').forEach(b => { b.disabled = !manual; });
    updateGoto(status, manual);
    setChip($('chip-mode'), manual ? 'Manual' : 'Auto tracking', manual ? 'warn' : 'ok');

    // Tracker clock (UTC)
    if (status.utc_time) {
        const dt = asUTC(status.utc_time);
        if (!isNaN(dt.getTime())) {
            $('tracker-date').textContent = `${pad2(dt.getUTCDate())}/${pad2(dt.getUTCMonth()+1)}/${dt.getUTCFullYear()}`;
            $('tracker-time').textContent = `${pad2(dt.getUTCHours())}:${pad2(dt.getUTCMinutes())}:${pad2(dt.getUTCSeconds())} UTC`;
            const drift = Math.round((dt.getTime() - (lastUpdateTime || Date.now())) / 1000);
            $('d-clock').textContent = fmtUTC(dt) + (Math.abs(drift) > 60 ? ` (off by ${drift}s)` : '');
        }
    }

    // Positions
    const sunAzi = status.sun_position?.azimuth ?? null;
    const sunAlt = status.sun_position?.altitude ?? null;
    const panelH = status.position?.horizontal ?? null;
    const panelV = status.position?.vertical ?? null;

    el.sunAzimuth.textContent = sunAzi !== null ? sunAzi.toFixed(1) : '--';
    el.sunAltitude.textContent = sunAlt !== null ? sunAlt.toFixed(1) : '--';
    el.posHorizontal.textContent = panelH !== null ? panelH.toFixed(1) : '--';
    el.posVertical.textContent = panelV !== null ? panelV.toFixed(1) : '--';

    updateCompass(sunAzi, panelH);
    updateAltitudeGauge(sunAlt, panelV);
    updateScene(sunAzi, sunAlt, panelH, panelV);
    updateObservedLimits(status.observed_limits);

    // Tracking offset (only meaningful with the sun up)
    const chipOffset = $('chip-offset');
    if (sunAzi !== null && panelH !== null && sunAlt !== null && sunAlt > 3) {
        const off = Math.abs(((panelH - sunAzi + 540) % 360) - 180);
        setChip(chipOffset, `Offset ${off.toFixed(0)}\u00B0`, off > 15 ? 'bad' : (off > 5 ? 'warn' : 'ok'));
        chipOffset.style.display = '';
    } else {
        chipOffset.style.display = 'none';
    }

    // Wind
    const wind = status.wind_speed;
    const ws = status.wind_settings;
    const windCls = ws && wind !== null && wind !== undefined
        ? (wind > ws.trip ? 'bad' : (wind > ws.release ? 'warn' : '')) : '';
    setChip($('chip-wind'), `Wind ${wind ?? '--'} km/h`, windCls);
    $('d-wind').textContent = wind ?? '--';
    $('d-wind-settings').textContent = ws
        ? `above ${ws.trip} km/h, clears after ${ws.hold_minutes} min below ${ws.release}`
        : 'not read yet';
    if (ws && !el.maxWindInput.value && document.activeElement !== el.maxWindInput) {
        el.maxWindInput.placeholder = `Wind limit (now ${ws.trip} km/h)`;
    }

    // Limit switches are normal states, shown as chips rather than alarms
    const sw = $('chip-switches');
    sw.innerHTML = '';
    (status.limit_switches || []).forEach(code => {
        const c = document.createElement('span');
        c.className = 'chip';
        c.textContent = SWITCH_NAMES[code] || code;
        sw.appendChild(c);
    });

    // Details
    $('d-enc-rot').textContent = status.rotation_encoder ?? '--';
    $('d-enc-tilt').textContent = status.tilt_encoder ?? '--';
    if (status.firmware_version) $('firmware-version').textContent = status.firmware_version;
    $('d-alarm-word').textContent = '0x' + (status.alarm_word || 0).toString(16).toUpperCase().padStart(4, '0');
    $('d-frames').textContent = `${status.frames_ok ?? 0} / ${status.frames_bad ?? 0}`;

    updateAlarms((status.active_alarms || []).filter(a => a.severity !== 'info'));
    updateAlarmHistory(status.alarm_history || []);
}

function updateObservedLimits(limits) {
    if (!limits) return;
    updateCompassLimits(limits.horizontal_min ?? null, limits.horizontal_max ?? null);
    updateAltitudeLimits(limits.vertical_min ?? null, limits.vertical_max ?? null);
}

function updateAlarms(alarms) {
    el.alarmBanner.style.display = alarms.length ? '' : 'none';
    if (!alarms.length) return;
    el.alarmBanner.classList.toggle('warn-alarm', alarms.every(a => a.severity === 'warning'));
    el.alarmList.innerHTML = '';
    alarms.forEach(a => {
        const li = document.createElement('li');
        li.textContent = a.message;
        if (a.timestamp) {
            const s = document.createElement('small');
            s.textContent = 'since ' + fmtUTC(asUTC(a.timestamp)) + ' UTC';
            li.appendChild(s);
        }
        el.alarmList.appendChild(li);
    });
}

function updateAlarmHistory(history) {
    el.alarmHistory.innerHTML = '';
    if (history.length === 0) {
        const li = document.createElement('li');
        li.className = 'no-history';
        li.textContent = 'No alarms logged';
        el.alarmHistory.appendChild(li);
        return;
    }
    history.forEach(entry => {
        const li = document.createElement('li');
        const dot = document.createElement('span');
        dot.className = 'sev ' + entry.severity;
        const span = document.createElement('span');
        span.className = 'history-time';
        span.textContent = fmtUTC(asUTC(entry.timestamp));
        li.appendChild(dot);
        li.appendChild(span);
        li.appendChild(document.createTextNode(' ' + entry.message));
        el.alarmHistory.appendChild(li);
    });
}

// Last update timer
setInterval(() => {
    if (!el.lastUpdateBadge) return;
    if (!lastUpdateTime) { el.lastUpdateBadge.textContent = 'no data'; return; }
    const secs = Math.max(0, Math.round((Date.now() - lastUpdateTime) / 1000));
    el.lastUpdateBadge.textContent = secs < 60 ? `${secs}s` : (secs < 3600 ? `${Math.floor(secs/60)}m` : `${Math.floor(secs/3600)}h`);
    el.lastUpdateBadge.style.borderColor = secs > 10 ? 'var(--warning)' : 'var(--info)';
}, 1000);

// =============================================================================
// Weather (Open-Meteo, free, no API key)
// =============================================================================

const WEATHER_LAT = 40.54;
const WEATHER_LON = -8.70;
let weatherCache = null;

const WMO_CODES = {
    0: 'Clear', 1: 'Mostly Clear', 2: 'Partly Cloudy', 3: 'Overcast',
    45: 'Fog', 48: 'Rime Fog', 51: 'Light Drizzle', 53: 'Drizzle', 55: 'Heavy Drizzle',
    61: 'Light Rain', 63: 'Rain', 65: 'Heavy Rain', 71: 'Light Snow', 73: 'Snow', 75: 'Heavy Snow',
    80: 'Rain Showers', 81: 'Mod. Showers', 82: 'Heavy Showers', 95: 'Thunderstorm',
};

async function fetchWeather() {
    try {
        const url = `https://api.open-meteo.com/v1/forecast?latitude=${WEATHER_LAT}&longitude=${WEATHER_LON}&current=temperature_2m,weather_code,wind_speed_10m&daily=sunrise,sunset&timezone=auto&forecast_days=1`;
        const resp = await fetch(url);
        const data = await resp.json();
        weatherCache = {
            temp: data.current?.temperature_2m,
            code: data.current?.weather_code,
            wind: data.current?.wind_speed_10m,
            sunrise: data.daily?.sunrise?.[0],
            sunset: data.daily?.sunset?.[0],
        };
        updateWeatherDisplay();
    } catch (e) {
        console.warn('Weather fetch failed:', e);
    }
}

function updateWeatherDisplay() {
    if (!weatherCache) return;

    const sunriseEl = document.getElementById('scene-sunrise');
    const weatherEl = document.getElementById('scene-weather');
    const cloudsEl = document.getElementById('weather-clouds');
    const rainEl = document.getElementById('weather-rain');

    // Sunrise/sunset text
    if (sunriseEl && weatherCache.sunrise && weatherCache.sunset) {
        const sr = new Date(weatherCache.sunrise);
        const ss = new Date(weatherCache.sunset);
        const fmt = d => `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
        sunriseEl.textContent = `\u2600\uFE0E ${fmt(sr)}  \u263D\uFE0E ${fmt(ss)}`;
    }

    // Weather text
    if (weatherEl) {
        const desc = WMO_CODES[weatherCache.code] || '';
        const temp = weatherCache.temp !== undefined ? `${Math.round(weatherCache.temp)}\u00B0C` : '';
        const wind = weatherCache.wind !== undefined ? `Wind ${Math.round(weatherCache.wind)} km/h` : '';
        weatherEl.textContent = `${desc}  ${temp}  ${wind}`;
    }

    // Weather effects: clouds + rain based on WMO code
    const code = weatherCache.code;
    const hasClouds = code >= 2; // Partly cloudy and above
    const hasRain = (code >= 51 && code <= 67) || (code >= 80 && code <= 82) || code === 95;
    const heavyRain = code === 55 || code === 65 || code === 82;

    if (cloudsEl) {
        cloudsEl.setAttribute('opacity', hasClouds ? (code >= 3 ? '0.7' : '0.4') : '0');
    }
    if (rainEl) {
        rainEl.setAttribute('opacity', hasRain ? (heavyRain ? '0.9' : '0.6') : '0');
    }
}

// Fetch weather on load and every 15 minutes
fetchWeather();
setInterval(fetchWeather, 15 * 60 * 1000);

// =============================================================================
// Actions
// =============================================================================

// =============================================================================
// Inverter Data
// =============================================================================

async function fetchInverterStatus() {
    try {
        const data = await apiCall('/inverter/status');
        const powerEl = document.getElementById('inv-power');
        const todayEl = document.getElementById('inv-today');
        const totalEl = document.getElementById('inv-total');
        const tempEl = document.getElementById('inv-temp');
        const badgeEl = document.getElementById('inverter-status-badge');
        const scenePower = document.getElementById('inv-scene-power');
        const sceneLed = document.getElementById('inv-scene-led');

        if (powerEl) powerEl.textContent = data.current_power || 0;
        if (todayEl) todayEl.textContent = (data.today_yield / 1000).toFixed(2);
        if (totalEl) totalEl.textContent = (data.total_yield / 1000000).toFixed(1);
        if (tempEl) tempEl.textContent = data.temperature !== null ? data.temperature.toFixed(0) : '--';
        if (badgeEl) {
            badgeEl.textContent = data.status || '--';
            badgeEl.style.borderColor = data.status === 'OK' ? 'var(--success)' : 'var(--warning)';
        }

        // Scene inverter LCD
        if (scenePower) {
            const p = data.current_power || 0;
            scenePower.textContent = p > 1000 ? (p/1000).toFixed(1) + 'kW' : p + 'W';
        }
        if (sceneLed) {
            sceneLed.setAttribute('fill', data.current_power > 0 ? '#4aff4a' : '#666');
        }
    } catch (e) {
        // DB might not be mounted yet
    }
}

// Fetch inverter data every 30 seconds
fetchInverterStatus();
setInterval(fetchInverterStatus, 30000);

// =============================================================================
// Actions
// =============================================================================

async function refreshPorts() {
    const data = await apiCall('/serial/ports');
    el.portSelect.innerHTML = '<option value="">Select port...</option>';
    data.ports.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.device;
        opt.textContent = `${p.device} - ${p.description}`;
        el.portSelect.appendChild(opt);
    });
}

async function connect() {
    const port = el.portSelect.value;
    if (!port) throw new Error('Select a port');
    return apiCall(`/serial/connect?port=${encodeURIComponent(port)}&baudrate=9600`, 'POST');
}

// Go-to-angle: sliders start at the current position and are left alone once touched
const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
let gotoTouched = { alt: false, azi: false };

function showGotoValues() {
    $('goto-alt-out').textContent = `${$('goto-alt').value}°`;
    const a = parseInt($('goto-azi').value, 10);
    $('goto-azi-out').textContent = `${a}° ${COMPASS[Math.round(a / 45) % 8]}`;
}

function updateGoto(status, manual) {
    const pos = status.position || {};
    if (!gotoTouched.alt && pos.vertical != null) $('goto-alt').value = Math.round(pos.vertical);
    if (!gotoTouched.azi && pos.horizontal != null) $('goto-azi').value = Math.round(pos.horizontal);
    showGotoValues();
    const g = status.goto || {};
    $('goto-alt').disabled = $('goto-azi').disabled = !manual || g.active;
    $('goto-btn').disabled = !manual || g.active;
    const st = $('goto-status');
    st.textContent = g.active ? `${g.message}… press ■ to stop` : (g.phase && g.phase !== 'idle' ? g.message : '');
    st.className = 'goto-status ' + (g.active ? '' : g.phase || '');
    if (!g.active && (g.phase === 'done' || g.phase === 'cancelled')) gotoTouched = { alt: false, azi: false };
}

async function goThere() {
    const body = {};
    if (gotoTouched.alt) body.altitude = parseFloat($('goto-alt').value);
    if (gotoTouched.azi) body.azimuth = parseFloat($('goto-azi').value);
    if (!Object.keys(body).length) throw new Error('Move a slider to choose where the panel should go');
    return apiCall('/tracker/goto', 'POST', body);
}

async function nudge(dir, ms) {
    await apiCall(`/tracker/move/${dir}/start`, 'POST');
    await new Promise(r => setTimeout(r, ms));
    await apiCall(`/tracker/move/${dir}/stop`, 'POST');
}

async function setWind() {
    const v = parseInt(el.maxWindInput.value, 10);
    if (!(v >= 10 && v <= 99)) throw new Error('Enter a wind limit between 10 and 99 km/h');
    if (!confirm(`Set the wind limit to ${v} km/h? This is stored in the tracker.`)) return;
    const r = await apiCall('/tracker/wind', 'POST', { max_wind: v });
    el.maxWindInput.value = '';
    return r;
}

async function zeroPanel() {
    if (!confirm('Start the homing routine? The tracker will move by itself.')) return;
    return apiCall('/tracker/zero?confirm=true', 'POST');
}

// =============================================================================
// Event Listeners
// =============================================================================

function setup() {
    document.querySelectorAll('.clickable[data-toggle]').forEach(header => {
        header.addEventListener('click', () => $(header.dataset.toggle).classList.toggle('collapsed'));
    });

    el.refreshPortsBtn.addEventListener('click', () => action(el.refreshPortsBtn, refreshPorts));
    el.connectBtn.addEventListener('click', () => action(el.connectBtn, connect));
    el.disconnectBtn.addEventListener('click', () => action(el.disconnectBtn, () => apiCall('/serial/disconnect', 'POST')));

    // Mode changes are written to the tracker's flash, so confirm them
    el.modeManualBtn.addEventListener('click', () => {
        if (currentMode === 'manual' || !confirm('Switch to manual? Sun tracking stops until you switch back.')) return;
        action(el.modeManualBtn, () => apiCall('/tracker/mode/manual', 'POST'));
    });
    el.modeAutoBtn.addEventListener('click', () => {
        if (currentMode === 'automatic') return;
        action(el.modeAutoBtn, () => apiCall('/tracker/mode/automatic', 'POST'));
    });

    document.querySelectorAll('.dpad-btn[data-direction]').forEach(btn => {
        btn.addEventListener('click', () => nudge(btn.dataset.direction, 500).catch(e => alert(e.message)));
    });
    el.stopBtn.addEventListener('click', () => action(el.stopBtn, () => apiCall('/tracker/stop', 'POST')));
    $('goto-alt').addEventListener('input', () => { gotoTouched.alt = true; showGotoValues(); });
    $('goto-azi').addEventListener('input', () => { gotoTouched.azi = true; showGotoValues(); });
    $('goto-btn').addEventListener('click', () => action($('goto-btn'), goThere));
    document.querySelectorAll('#presets button').forEach(btn => {
        btn.addEventListener('click', () => action(btn, () => apiCall(`/tracker/position/${btn.dataset.preset}`, 'POST')));
    });

    el.syncClockBtn.addEventListener('click', () => action(el.syncClockBtn, () => apiCall('/tracker/datetime/sync', 'POST')));
    el.setWindBtn.addEventListener('click', () => action(el.setWindBtn, setWind));
    el.zeroBtn.addEventListener('click', () => action(el.zeroBtn, zeroPanel));
    el.clearAlarmsBtn.addEventListener('click', () => {
        if (!confirm('Clear alarms? This also erases the tracker\'s alarm log.')) return;
        action(el.clearAlarmsBtn, () => apiCall('/tracker/alarms/clear', 'POST'));
    });
    el.resetLimitsBtn.addEventListener('click', () => action(el.resetLimitsBtn, () => apiCall('/tracker/limits/reset', 'POST')));
}

// =============================================================================
// Init
// =============================================================================

async function init() {
    log('UI initialized');
    initCompassTicks();
    initAltitudeTicks();
    initAltitudeTicksBelow();
    setup();
    connectWebSocket();
    await refreshPorts();

    try {
        const status = await apiCall('/tracker/status');
        updateUI(status);
        if (status.connection?.connected && status.connection?.port) {
            el.portSelect.value = status.connection.port;
        }
    } catch (e) {
        log(`Initial status failed: ${e.message}`);
    }
}

document.addEventListener('DOMContentLoaded', init);
