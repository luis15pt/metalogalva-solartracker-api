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
const el = {
    serialStatus: document.getElementById('serial-status'),
    serialText: document.getElementById('serial-text'),
    wsStatus: document.getElementById('ws-status'),
    wsText: document.getElementById('ws-text'),
    lastUpdateBadge: document.getElementById('last-update-badge'),
    portSelect: document.getElementById('port-select'),
    baudrateSelect: document.getElementById('baudrate-select'),
    refreshPortsBtn: document.getElementById('refresh-ports-btn'),
    connectBtn: document.getElementById('connect-btn'),
    disconnectBtn: document.getElementById('disconnect-btn'),
    modeManualBtn: document.getElementById('mode-manual-btn'),
    modeAutoBtn: document.getElementById('mode-auto-btn'),
    stopBtn: document.getElementById('stop-btn'),
    homeBtn: document.getElementById('home-btn'),
    stowBtn: document.getElementById('stow-btn'),
    syncClockBtn: document.getElementById('sync-clock-btn'),
    sunAzimuth: document.getElementById('sun-azimuth'),
    sunAltitude: document.getElementById('sun-altitude'),
    posHorizontal: document.getElementById('pos-horizontal'),
    posVertical: document.getElementById('pos-vertical'),
    alarmBanner: document.getElementById('alarm-banner'),
    alarmList: document.getElementById('alarm-list'),
    alarmHistory: document.getElementById('alarm-history'),
    clearAlarmsBtn: document.getElementById('clear-alarms-btn'),
    limitHMin: document.getElementById('limit-h-min'),
    limitHMax: document.getElementById('limit-h-max'),
    limitVMin: document.getElementById('limit-v-min'),
    limitVMax: document.getElementById('limit-v-max'),
    limitsSince: document.getElementById('limits-since'),
    resetLimitsBtn: document.getElementById('reset-limits-btn'),
    maxWindInput: document.getElementById('max-wind-input'),
    setWindBtn: document.getElementById('set-wind-btn'),
    debugPanel: document.getElementById('debug-panel'),
    rawHex: document.getElementById('raw-hex'),
    sendRawBtn: document.getElementById('send-raw-btn'),
    debugLog: document.getElementById('debug-log'),
};

// Informational alarms (expected, not critical)
const INFO_ALARMS = ['tilt_limit_flat', 'unknown_alarm_1'];

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

function log(msg) {
    if (!el.debugLog) return;
    el.debugLog.textContent += `[${new Date().toLocaleTimeString()}] ${msg}\n`;
    el.debugLog.scrollTop = el.debugLog.scrollHeight;
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
            lastUpdateTime = Date.now();
        } catch (e) {}
    };
}

// =============================================================================
// SVG Gauges
// =============================================================================

function initCompassTicks() {
    const g = document.getElementById('compass-ticks');
    if (!g) return;
    // Half compass: E(90°) through S(180°) to W(270°), pivot at top (100,10)
    const cx = 100, cy = 10, r1inner = 82, r2outer = 92;
    for (let deg = 90; deg <= 270; deg += 10) {
        const major = deg % 30 === 0;
        const rad = (deg - 90) * Math.PI / 180;
        const r1 = major ? r1inner : r1inner + 5;
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', cx + r1 * Math.cos(rad));
        line.setAttribute('y1', cy + r1 * Math.sin(rad));
        line.setAttribute('x2', cx + r2outer * Math.cos(rad));
        line.setAttribute('y2', cy + r2outer * Math.sin(rad));
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
    glow.setAttribute('cx', sunX);
    glow.setAttribute('cy', sunY);
    glow.setAttribute('opacity', sunVisible ? sunOpacity * 0.7 : 0);
    rays.setAttribute('cx', sunX);
    rays.setAttribute('cy', sunY);
    rays.setAttribute('opacity', isDay ? Math.min(0.6, sunAlt / 30) : 0);

    // Stars: visible at night
    if (stars) {
        stars.setAttribute('opacity', sunAlt !== null && sunAlt < -5 ? Math.min(1, (-sunAlt - 5) / 10) : 0);
    }

    // Sky gradient
    if (sunAlt !== null) {
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
    if (panelV !== null) {
        panel.setAttribute('transform', `rotate(${panelV}, 60, 95)`);
    }

    // Panel highlight (reflection when sun is hitting it)
    if (highlight && isDay) {
        highlight.setAttribute('opacity', Math.min(0.25, sunAlt / 60));
    } else if (highlight) {
        highlight.setAttribute('opacity', '0');
    }

    // Shadow on ground — cast from sun direction
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

function updateCompassLimits(hMin, hMax) {
    const g = document.getElementById('compass-limits');
    if (!g) return;
    g.innerHTML = '';
    if (hMin === null && hMax === null) return;
    const cx = 100, cy = 10, r1 = 75, r2 = 93;

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

const ALARM_NAMES = {
    'vertical_limit': 'Vertical Limit',
    'tilt_limit_flat': 'Tilt Limit - Panel Flat (stow)',
    'unknown_alarm_1': 'Unknown Alarm (bit 1)',
    'west_limit': 'West Limit',
    'wind_speed': 'Wind Speed Exceeded',
    'actuator_current': 'Actuator Current',
    'rotation_current': 'Rotation Current',
    'unknown_alarm_6': 'Unknown Alarm (bit 6)',
    'encoder_error': 'Encoder Error - BLOCKS ALL MOVEMENT',
};

function updateUI(status) {
    // Connection
    isConnected = status.connection?.connected || false;
    el.serialStatus.classList.toggle('connected', isConnected);
    el.serialText.textContent = isConnected ? 'Serial' : 'Serial';
    el.connectBtn.disabled = isConnected;
    el.disconnectBtn.disabled = !isConnected;

    // Auto-collapse connection panel when connected
    const connPanel = document.getElementById('connection-panel');
    if (isConnected && connPanel) connPanel.classList.add('collapsed');

    // Mode
    currentMode = status.mode || 'manual';
    el.modeManualBtn.classList.toggle('active', currentMode === 'manual');
    el.modeAutoBtn.classList.toggle('active', currentMode === 'automatic');

    // Date/Time
    if (status.utc_time) {
        const dt = new Date(status.utc_time);
        if (!isNaN(dt.getTime())) {
            const pad = n => String(n).padStart(2, '0');
            document.getElementById('tracker-date').textContent = `${pad(dt.getDate())}/${pad(dt.getMonth()+1)}/${dt.getFullYear()}`;
            document.getElementById('tracker-time').textContent = `${pad(dt.getHours())}:${pad(dt.getMinutes())}:${pad(dt.getSeconds())}`;
        }
    }

    // Firmware
    if (status.firmware_version) {
        document.getElementById('firmware-version').textContent = status.firmware_version;
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

    // Wind (hidden but keep for API compat)
    const windThresh = status.max_wind_threshold ?? null;
    if (windThresh !== null) el.maxWindInput.value = windThresh;

    // Observed Limits
    updateObservedLimits(status.observed_limits);

    // Alarms
    updateAlarms(status.alarms || []);
    updateAlarmHistory(status.alarm_history || []);
}

function updateObservedLimits(limits) {
    if (!limits) return;
    const fmt = v => v !== null && v !== undefined ? v.toFixed(1) : '--';
    el.limitHMin.textContent = fmt(limits.horizontal_min);
    el.limitHMax.textContent = fmt(limits.horizontal_max);
    el.limitVMin.textContent = fmt(limits.vertical_min);
    el.limitVMax.textContent = fmt(limits.vertical_max);

    if (el.limitsSince && limits.first_seen) {
        const dt = new Date(limits.first_seen);
        el.limitsSince.textContent = !isNaN(dt.getTime()) ?
            dt.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : '--';
    }

    updateCompassLimits(limits.horizontal_min ?? null, limits.horizontal_max ?? null);
    updateAltitudeLimits(limits.vertical_min ?? null, limits.vertical_max ?? null);
}

function updateAlarms(alarms) {
    const hasAlarms = alarms.length > 0;
    el.alarmBanner.style.display = hasAlarms ? '' : 'none';

    if (hasAlarms) {
        // Check if all alarms are informational
        const allInfo = alarms.every(a => INFO_ALARMS.includes(a));
        el.alarmBanner.classList.toggle('info-alarm', allInfo);
        el.alarmList.innerHTML = alarms.map(a => `<li>${ALARM_NAMES[a] || a}</li>`).join('');
    }
}

function updateAlarmHistory(history) {
    if (!el.alarmHistory) return;
    if (history.length === 0) {
        el.alarmHistory.innerHTML = '<li class="no-history">No alarm history</li>';
        return;
    }
    el.alarmHistory.innerHTML = history.map(entry => {
        const ts = new Date(entry.timestamp);
        const d = ts.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: '2-digit' });
        const t = ts.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
        return `<li><span class="history-time">${d} ${t}</span> ${entry.message}</li>`;
    }).join('');
}

// Last update timer
setInterval(() => {
    if (!lastUpdateTime || !el.lastUpdateBadge) return;
    const secs = Math.round((Date.now() - lastUpdateTime) / 1000);
    el.lastUpdateBadge.textContent = secs < 60 ? `${secs}s` : `${Math.floor(secs/60)}m`;
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

async function refreshPorts() {
    const data = await apiCall('/serial/ports');
    el.portSelect.innerHTML = '<option value="">Select port...</option>';
    data.ports.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.device;
        opt.textContent = `${p.device} - ${p.description}`;
        el.portSelect.appendChild(opt);
    });
    log(`Found ${data.ports.length} ports`);
}

async function connect() {
    const port = el.portSelect.value;
    if (!port) { alert('Select a port'); return; }
    const baud = parseInt(el.baudrateSelect.value);
    const data = await apiCall(`/serial/connect?port=${encodeURIComponent(port)}&baudrate=${baud}`, 'POST');
    log(data.message);
}

async function disconnect() {
    const data = await apiCall('/serial/disconnect', 'POST');
    log(data.message);
}

async function moveForDuration(dir, ms) {
    await apiCall(`/tracker/move/${dir}/start`, 'POST');
    await new Promise(r => setTimeout(r, ms));
    await apiCall(`/tracker/move/${dir}/stop`, 'POST');
}

async function goHome() {
    const data = await apiCall('/tracker/home', 'POST');
    log(data.message);
}

async function goStow() {
    const data = await apiCall('/tracker/stow', 'POST');
    log(data.message);
}

async function syncClock() {
    const data = await apiCall('/tracker/datetime/sync', 'POST');
    log(data.message);
}

async function sendRaw() {
    const hex = el.rawHex.value.replace(/\s/g, '');
    if (!hex || !/^[0-9a-fA-F]+$/.test(hex)) { alert('Invalid hex'); return; }
    const data = await apiCall(`/serial/send?data=${hex}`, 'POST');
    log(`Sent: ${hex} - ${data.message}`);
}

// =============================================================================
// Event Listeners
// =============================================================================

function setup() {
    // Collapsible panels
    document.querySelectorAll('.clickable[data-toggle]').forEach(header => {
        header.addEventListener('click', () => {
            document.getElementById(header.dataset.toggle).classList.toggle('collapsed');
        });
    });

    // Connection
    el.refreshPortsBtn.addEventListener('click', () => withLoading(el.refreshPortsBtn, refreshPorts));
    el.connectBtn.addEventListener('click', () => withLoading(el.connectBtn, connect));
    el.disconnectBtn.addEventListener('click', () => withLoading(el.disconnectBtn, disconnect));

    // Mode
    el.modeManualBtn.addEventListener('click', () => withLoading(el.modeManualBtn, () => apiCall('/tracker/mode/manual', 'POST')));
    el.modeAutoBtn.addEventListener('click', () => withLoading(el.modeAutoBtn, () => apiCall('/tracker/mode/automatic', 'POST')));

    // D-Pad
    document.querySelectorAll('.dpad-btn[data-direction]').forEach(btn => {
        btn.addEventListener('click', () => moveForDuration(btn.dataset.direction, 500));
    });
    el.stopBtn.addEventListener('click', () => withLoading(el.stopBtn, () => apiCall('/tracker/stop', 'POST')));

    // Presets
    el.homeBtn.addEventListener('click', () => withLoading(el.homeBtn, goHome));
    el.stowBtn.addEventListener('click', () => withLoading(el.stowBtn, goStow));

    // Sync clock
    el.syncClockBtn.addEventListener('click', () => withLoading(el.syncClockBtn, syncClock));

    // Alarms
    el.clearAlarmsBtn.addEventListener('click', () => withLoading(el.clearAlarmsBtn, () => apiCall('/tracker/alarms/clear', 'POST')));

    // Limits
    el.resetLimitsBtn.addEventListener('click', () => withLoading(el.resetLimitsBtn, () => apiCall('/tracker/limits/reset', 'POST')));

    // Debug
    el.sendRawBtn.addEventListener('click', () => withLoading(el.sendRawBtn, sendRaw));
    el.rawHex.addEventListener('keypress', e => { if (e.key === 'Enter') sendRaw(); });
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
