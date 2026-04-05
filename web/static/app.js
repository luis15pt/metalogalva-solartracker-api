/**
 * Solar Tracker Control - Web UI JavaScript
 */

// API base URL
const API_BASE = window.location.origin;

// WebSocket connection
let ws = null;
let wsReconnectTimer = null;

// State
let isConnected = false;
let currentMode = 'manual';

// DOM Elements
const elements = {
    // Status indicators
    serialStatus: document.getElementById('serial-status'),
    serialText: document.getElementById('serial-text'),
    wsStatus: document.getElementById('ws-status'),
    wsText: document.getElementById('ws-text'),

    // Connection
    portSelect: document.getElementById('port-select'),
    baudrateSelect: document.getElementById('baudrate-select'),
    refreshPortsBtn: document.getElementById('refresh-ports-btn'),
    connectBtn: document.getElementById('connect-btn'),
    disconnectBtn: document.getElementById('disconnect-btn'),

    // Mode
    modeManualBtn: document.getElementById('mode-manual-btn'),
    modeAutoBtn: document.getElementById('mode-auto-btn'),

    // Movement
    stopBtn: document.getElementById('stop-btn'),

    // Status
    trackerDate: document.getElementById('tracker-date'),
    trackerTime: document.getElementById('tracker-time'),
    firmwareVersion: document.getElementById('firmware-version'),

    // Sun Position
    sunAzimuth: document.getElementById('sun-azimuth'),
    sunAltitude: document.getElementById('sun-altitude'),

    // Panel Position
    posHorizontal: document.getElementById('pos-horizontal'),
    posVertical: document.getElementById('pos-vertical'),

    // Alarms
    alarmStatus: document.getElementById('alarm-status'),
    alarmList: document.getElementById('alarm-list'),
    alarmHistory: document.getElementById('alarm-history'),
    clearAlarmsBtn: document.getElementById('clear-alarms-btn'),

    // Observed Limits
    limitHMin: document.getElementById('limit-h-min'),
    limitHMax: document.getElementById('limit-h-max'),
    limitVMin: document.getElementById('limit-v-min'),
    limitVMax: document.getElementById('limit-v-max'),
    limitsSince: document.getElementById('limits-since'),
    resetLimitsBtn: document.getElementById('reset-limits-btn'),

    // Parameters
    maxWindInput: document.getElementById('max-wind-input'),
    setWindBtn: document.getElementById('set-wind-btn'),

    // Debug
    debugPanel: document.getElementById('debug-panel'),
    rawHex: document.getElementById('raw-hex'),
    sendRawBtn: document.getElementById('send-raw-btn'),
    debugLog: document.getElementById('debug-log'),
};

// =============================================================================
// API Functions
// =============================================================================

async function apiCall(endpoint, method = 'GET', body = null) {
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json',
        },
    };

    if (body) {
        options.body = JSON.stringify(body);
    }

    try {
        const response = await fetch(`${API_BASE}${endpoint}`, options);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'API error');
        }

        return data;
    } catch (error) {
        log(`API Error: ${error.message}`);
        throw error;
    }
}

// =============================================================================
// Button Loading Wrapper
// =============================================================================

async function withLoading(btn, asyncFn) {
    const originalHTML = btn.innerHTML;
    btn.classList.add('loading');
    btn.innerHTML = '<span class="btn-spinner"></span>' + originalHTML;
    btn.disabled = true;
    try {
        await asyncFn();
    } finally {
        btn.classList.remove('loading');
        btn.innerHTML = originalHTML;
        btn.disabled = false;
    }
}

// =============================================================================
// WebSocket Functions
// =============================================================================

function connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        log('WebSocket connected');
        elements.wsStatus.classList.remove('reconnecting');
        updateWsStatus(true);
        clearTimeout(wsReconnectTimer);
    };

    ws.onclose = () => {
        log('WebSocket disconnected');
        updateWsStatus(false);
        elements.wsStatus.classList.add('reconnecting');
        elements.wsText.textContent = 'Reconnecting...';
        wsReconnectTimer = setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (error) => {
        log(`WebSocket error: ${error}`);
    };

    ws.onmessage = (event) => {
        try {
            const status = JSON.parse(event.data);
            updateUI(status);
        } catch (error) {
            log(`WebSocket message parse error: ${error}`);
        }
    };
}

// =============================================================================
// SVG Gauge Functions
// =============================================================================

function initCompassTicks() {
    const ticksGroup = document.getElementById('compass-ticks');
    if (!ticksGroup) return;
    for (let deg = 0; deg < 360; deg += 10) {
        const isMajor = deg % 30 === 0;
        const rad = (deg - 90) * Math.PI / 180;
        const r1 = isMajor ? 82 : 87;
        const r2 = 92;
        const x1 = 100 + r1 * Math.cos(rad);
        const y1 = 100 + r1 * Math.sin(rad);
        const x2 = 100 + r2 * Math.cos(rad);
        const y2 = 100 + r2 * Math.sin(rad);
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', x1);
        line.setAttribute('y1', y1);
        line.setAttribute('x2', x2);
        line.setAttribute('y2', y2);
        line.setAttribute('stroke', isMajor ? '#a0a0a0' : 'rgba(160,160,160,0.3)');
        line.setAttribute('stroke-width', isMajor ? '1.5' : '0.75');
        ticksGroup.appendChild(line);
    }
}

function initAltitudeTicks() {
    const ticksGroup = document.getElementById('altitude-ticks');
    if (!ticksGroup) return;
    const cx = 100, cy = 105, r = 85;
    for (let alt = 0; alt <= 90; alt += 15) {
        const angle = 180 - (alt * 180 / 90);
        const rad = angle * Math.PI / 180;
        const x1 = cx + (r - 5) * Math.cos(rad);
        const y1 = cy - (r - 5) * Math.sin(rad);
        const x2 = cx + (r + 3) * Math.cos(rad);
        const y2 = cy - (r + 3) * Math.sin(rad);
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', x1);
        line.setAttribute('y1', y1);
        line.setAttribute('x2', x2);
        line.setAttribute('y2', y2);
        line.setAttribute('stroke', '#a0a0a0');
        line.setAttribute('stroke-width', '1');
        ticksGroup.appendChild(line);

        // Label for intermediate ticks
        if (alt > 0 && alt < 90) {
            const lx = cx + (r + 12) * Math.cos(rad);
            const ly = cy - (r + 12) * Math.sin(rad);
            const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            text.setAttribute('x', lx);
            text.setAttribute('y', ly);
            text.setAttribute('fill', '#a0a0a0');
            text.setAttribute('font-size', '8');
            text.setAttribute('text-anchor', 'middle');
            text.setAttribute('dominant-baseline', 'central');
            text.textContent = alt + '\u00B0';
            ticksGroup.appendChild(text);
        }
    }
}

function initAltitudeTicksBelow() {
    const ticksGroup = document.getElementById('altitude-ticks-below');
    if (!ticksGroup) return;
    const cx = 100, cy = 105, r = 85;
    for (let alt = -15; alt >= -45; alt -= 15) {
        const angle = 180 - (alt * 180 / 90);
        const rad = angle * Math.PI / 180;
        const x1 = cx + (r - 5) * Math.cos(rad);
        const y1 = cy - (r - 5) * Math.sin(rad);
        const x2 = cx + (r + 3) * Math.cos(rad);
        const y2 = cy - (r + 3) * Math.sin(rad);
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', x1);
        line.setAttribute('y1', y1);
        line.setAttribute('x2', x2);
        line.setAttribute('y2', y2);
        line.setAttribute('stroke', 'rgba(160,160,160,0.4)');
        line.setAttribute('stroke-width', '1');
        ticksGroup.appendChild(line);

        const lx = cx + (r + 14) * Math.cos(rad);
        const ly = cy - (r + 14) * Math.sin(rad);
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', lx);
        text.setAttribute('y', ly);
        text.setAttribute('fill', 'rgba(160,160,160,0.5)');
        text.setAttribute('font-size', '7');
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('dominant-baseline', 'central');
        text.textContent = alt + '\u00B0';
        ticksGroup.appendChild(text);
    }
}

function initWindTicks() {
    const ticksGroup = document.getElementById('wind-ticks');
    if (!ticksGroup) return;
    const cx = 80, cy = 85, r = 65;
    // Ticks at 0, 10, 20, 30, 40, 50
    for (let val = 0; val <= 50; val += 10) {
        const fraction = val / 50;
        const angle = (180 + fraction * 180) * Math.PI / 180;
        const x1 = cx + (r - 4) * Math.cos(angle);
        const y1 = cy + (r - 4) * Math.sin(angle);
        const x2 = cx + (r + 3) * Math.cos(angle);
        const y2 = cy + (r + 3) * Math.sin(angle);
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', x1);
        line.setAttribute('y1', y1);
        line.setAttribute('x2', x2);
        line.setAttribute('y2', y2);
        line.setAttribute('stroke', '#a0a0a0');
        line.setAttribute('stroke-width', '1');
        ticksGroup.appendChild(line);

        // Label
        const lx = cx + (r + 12) * Math.cos(angle);
        const ly = cy + (r + 12) * Math.sin(angle);
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', lx);
        text.setAttribute('y', ly);
        text.setAttribute('fill', '#a0a0a0');
        text.setAttribute('font-size', '8');
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('dominant-baseline', 'central');
        text.textContent = val;
        ticksGroup.appendChild(text);
    }
}

function updateCompass(sunAzimuth, panelAzimuth) {
    const sunNeedle = document.getElementById('sun-needle');
    const panelNeedle = document.getElementById('panel-needle');
    if (sunNeedle && sunAzimuth !== null) {
        sunNeedle.style.transform = `rotate(${sunAzimuth}deg)`;
    }
    if (panelNeedle && panelAzimuth !== null) {
        panelNeedle.style.transform = `rotate(${panelAzimuth}deg)`;
    }
}

function updateAltitudeGauge(sunAltitude, panelVertical) {
    const cx = 100, cy = 105, r = 80;

    function sunAltToPoint(alt) {
        if (alt === null || alt === undefined) return null;
        const clamped = Math.max(-45, Math.min(90, alt));
        const angle = 180 - (clamped * 180 / 90);
        const rad = angle * Math.PI / 180;
        return { x: cx + r * Math.cos(rad), y: cy - r * Math.sin(rad) };
    }

    function panelAltToPoint(alt) {
        if (alt === null || alt === undefined) return null;
        const clamped = Math.max(0, Math.min(90, alt));
        const angle = 180 - (clamped * 180 / 90);
        const rad = angle * Math.PI / 180;
        return { x: cx + r * Math.cos(rad), y: cy - r * Math.sin(rad) };
    }

    const sunNeedle = document.getElementById('sun-alt-needle');
    const sunDot = document.getElementById('sun-alt-dot');
    const sunNeedleGroup = document.getElementById('sun-alt-needle-group');
    const panelNeedle = document.getElementById('panel-alt-needle');

    if (sunNeedle && sunAltitude !== null) {
        const pt = sunAltToPoint(sunAltitude);
        if (pt) {
            sunNeedle.setAttribute('x2', pt.x);
            sunNeedle.setAttribute('y2', pt.y);
            if (sunDot) {
                sunDot.setAttribute('cx', pt.x);
                sunDot.setAttribute('cy', pt.y);
            }
            if (sunNeedleGroup) {
                sunNeedleGroup.classList.toggle('below-horizon', sunAltitude < 0);
            }
        }
    }

    if (panelNeedle && panelVertical !== null) {
        const pt = panelAltToPoint(panelVertical);
        if (pt) {
            panelNeedle.setAttribute('x2', pt.x);
            panelNeedle.setAttribute('y2', pt.y);
        }
    }
}

function updateWindGauge(speed, threshold) {
    const maxScale = Math.max(threshold || 50, 50);
    const cx = 80, cy = 85, r = 65;

    function speedToArcPath(value) {
        if (value === null || value === undefined || value <= 0) return '';
        const clamped = Math.max(0, Math.min(value, maxScale));
        const fraction = clamped / maxScale;
        const endAngle = 180 + fraction * 180;
        const endRad = endAngle * Math.PI / 180;
        const sx = cx - r; // Start at 180 degrees (left)
        const sy = cy;
        const ex = cx + r * Math.cos(endRad);
        const ey = cy + r * Math.sin(endRad);
        const largeArc = fraction > 0.5 ? 1 : 0;
        return `M ${sx} ${sy} A ${r} ${r} 0 ${largeArc} 1 ${ex} ${ey}`;
    }

    function speedColor(value, thresh) {
        if (!thresh) return '#00c853';
        const pct = value / thresh;
        if (pct < 0.5) return '#00c853';
        if (pct < 0.8) return '#ffc107';
        return '#ff5252';
    }

    const arcEl = document.getElementById('wind-arc-value');
    const textEl = document.getElementById('wind-speed-gauge');
    const markerEl = document.getElementById('wind-threshold-marker');

    if (arcEl && speed !== null && speed !== undefined) {
        arcEl.setAttribute('d', speedToArcPath(speed));
        arcEl.setAttribute('stroke', speedColor(speed, threshold));
    }

    if (textEl) {
        textEl.textContent = speed !== null && speed !== undefined ? speed : '--';
    }

    // Position threshold marker
    if (markerEl && threshold) {
        const fraction = Math.min(threshold / maxScale, 1);
        const angle = (180 + fraction * 180) * Math.PI / 180;
        const x1 = cx + (r + 5) * Math.cos(angle);
        const y1 = cy + (r + 5) * Math.sin(angle);
        const x2 = cx + (r - 10) * Math.cos(angle);
        const y2 = cy + (r - 10) * Math.sin(angle);
        markerEl.setAttribute('x1', x1);
        markerEl.setAttribute('y1', y1);
        markerEl.setAttribute('x2', x2);
        markerEl.setAttribute('y2', y2);
    }
}

// =============================================================================
// Observed Limits Markers
// =============================================================================

function updateCompassLimits(hMin, hMax) {
    const group = document.getElementById('compass-limits');
    if (!group) return;
    group.innerHTML = '';

    if (hMin === null && hMax === null) return;

    const cx = 100, cy = 100, r1 = 75, r2 = 93;

    function drawLimitLine(angle) {
        const rad = (angle - 90) * Math.PI / 180;
        const x1 = cx + r1 * Math.cos(rad);
        const y1 = cy + r1 * Math.sin(rad);
        const x2 = cx + r2 * Math.cos(rad);
        const y2 = cy + r2 * Math.sin(rad);
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', x1);
        line.setAttribute('y1', y1);
        line.setAttribute('x2', x2);
        line.setAttribute('y2', y2);
        line.setAttribute('class', 'limit-marker-line');
        group.appendChild(line);
    }

    if (hMin !== null) drawLimitLine(hMin);
    if (hMax !== null) drawLimitLine(hMax);

    // Draw arc between limits
    if (hMin !== null && hMax !== null) {
        const rArc = 78;
        const startRad = (hMin - 90) * Math.PI / 180;
        const endRad = (hMax - 90) * Math.PI / 180;
        const sx = cx + rArc * Math.cos(startRad);
        const sy = cy + rArc * Math.sin(startRad);
        const ex = cx + rArc * Math.cos(endRad);
        const ey = cy + rArc * Math.sin(endRad);
        let sweep = hMax - hMin;
        if (sweep < 0) sweep += 360;
        const largeArc = sweep > 180 ? 1 : 0;
        const arc = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        arc.setAttribute('d', `M ${sx} ${sy} A ${rArc} ${rArc} 0 ${largeArc} 1 ${ex} ${ey}`);
        arc.setAttribute('class', 'limit-marker-arc');
        group.appendChild(arc);
    }
}

function updateAltitudeLimits(vMin, vMax) {
    const group = document.getElementById('altitude-limits');
    if (!group) return;
    group.innerHTML = '';

    if (vMin === null && vMax === null) return;

    const cx = 100, cy = 105, r = 85;

    function drawLimitTick(alt) {
        const clamped = Math.max(0, Math.min(90, alt));
        const angle = 180 - (clamped * 180 / 90);
        const rad = angle * Math.PI / 180;
        const x1 = cx + (r - 8) * Math.cos(rad);
        const y1 = cy - (r - 8) * Math.sin(rad);
        const x2 = cx + (r + 2) * Math.cos(rad);
        const y2 = cy - (r + 2) * Math.sin(rad);
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', x1);
        line.setAttribute('y1', y1);
        line.setAttribute('x2', x2);
        line.setAttribute('y2', y2);
        line.setAttribute('class', 'limit-marker-line');
        group.appendChild(line);
    }

    if (vMin !== null) drawLimitTick(vMin);
    if (vMax !== null) drawLimitTick(vMax);

    // Draw arc between limits
    if (vMin !== null && vMax !== null) {
        const rArc = 80;
        const startAngle = 180 - (Math.max(0, Math.min(90, vMin)) * 180 / 90);
        const endAngle = 180 - (Math.max(0, Math.min(90, vMax)) * 180 / 90);
        const startRad = startAngle * Math.PI / 180;
        const endRad = endAngle * Math.PI / 180;
        const sx = cx + rArc * Math.cos(startRad);
        const sy = cy - rArc * Math.sin(startRad);
        const ex = cx + rArc * Math.cos(endRad);
        const ey = cy - rArc * Math.sin(endRad);
        const sweep = Math.abs(startAngle - endAngle);
        const largeArc = sweep > 180 ? 1 : 0;
        const arc = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        // Go from vMin (lower angle, right side) to vMax (higher angle, left side) counter-clockwise
        arc.setAttribute('d', `M ${sx} ${sy} A ${rArc} ${rArc} 0 ${largeArc} 0 ${ex} ${ey}`);
        arc.setAttribute('class', 'limit-marker-arc');
        group.appendChild(arc);
    }
}

function updateObservedLimitsUI(observedLimits) {
    if (!observedLimits) return;

    const fmt = (v) => v !== null && v !== undefined ? v.toFixed(1) : '--';

    if (elements.limitHMin) elements.limitHMin.textContent = fmt(observedLimits.horizontal_min);
    if (elements.limitHMax) elements.limitHMax.textContent = fmt(observedLimits.horizontal_max);
    if (elements.limitVMin) elements.limitVMin.textContent = fmt(observedLimits.vertical_min);
    if (elements.limitVMax) elements.limitVMax.textContent = fmt(observedLimits.vertical_max);

    if (elements.limitsSince) {
        if (observedLimits.first_seen) {
            const dt = new Date(observedLimits.first_seen);
            if (!isNaN(dt.getTime())) {
                elements.limitsSince.textContent = dt.toLocaleDateString('en-GB', {
                    day: '2-digit', month: '2-digit', year: '2-digit',
                    hour: '2-digit', minute: '2-digit'
                });
            } else {
                elements.limitsSince.textContent = '--';
            }
        } else {
            elements.limitsSince.textContent = '--';
        }
    }

    updateCompassLimits(
        observedLimits.horizontal_min ?? null,
        observedLimits.horizontal_max ?? null
    );
    updateAltitudeLimits(
        observedLimits.vertical_min ?? null,
        observedLimits.vertical_max ?? null
    );
}

// =============================================================================
// UI Update Functions
// =============================================================================

function updateUI(status) {
    // Update connection status
    isConnected = status.connection?.connected || false;
    updateSerialStatus(isConnected);

    // Update mode
    currentMode = status.mode || 'manual';
    updateModeButtons();

    // Update date/time from tracker
    if (status.utc_time) {
        const dt = new Date(status.utc_time);
        if (!isNaN(dt.getTime())) {
            const day = String(dt.getDate()).padStart(2, '0');
            const month = String(dt.getMonth() + 1).padStart(2, '0');
            const year = dt.getFullYear();
            const hours = String(dt.getHours()).padStart(2, '0');
            const minutes = String(dt.getMinutes()).padStart(2, '0');
            const seconds = String(dt.getSeconds()).padStart(2, '0');
            const dateEl = document.getElementById('tracker-date');
            const timeEl = document.getElementById('tracker-time');
            if (dateEl) dateEl.textContent = `${day}/${month}/${year}`;
            if (timeEl) timeEl.textContent = `${hours}:${minutes}:${seconds}`;
        }
    }

    // Update firmware version
    if (status.firmware_version) {
        const fwEl = document.getElementById('firmware-version');
        if (fwEl) fwEl.textContent = status.firmware_version;
    }

    // Update sun position (text + compass)
    const sunAzi = status.sun_position?.azimuth ?? null;
    const sunAlt = status.sun_position?.altitude ?? null;
    if (elements.sunAzimuth) {
        elements.sunAzimuth.textContent = sunAzi !== null ? sunAzi.toFixed(2) : '--';
    }
    if (elements.sunAltitude) {
        elements.sunAltitude.textContent = sunAlt !== null ? sunAlt.toFixed(2) : '--';
    }

    // Update panel position (text + compass)
    const panelHoriz = status.position?.horizontal ?? null;
    const panelVert = status.position?.vertical ?? null;
    if (elements.posHorizontal) {
        elements.posHorizontal.textContent = panelHoriz !== null ? panelHoriz.toFixed(2) : '--';
    }
    if (elements.posVertical) {
        elements.posVertical.textContent = panelVert !== null ? panelVert.toFixed(2) : '--';
    }

    // Update gauges
    updateCompass(sunAzi, panelHoriz);
    updateAltitudeGauge(sunAlt, panelVert);

    // Update wind
    const windVal = status.wind_speed ?? null;
    const windThresh = status.max_wind_threshold ?? null;
    if (windThresh !== null) {
        elements.maxWindInput.value = windThresh;
    }
    updateWindGauge(windVal, windThresh);

    // Update observed limits
    updateObservedLimitsUI(status.observed_limits);

    // Update alarms
    updateAlarms(status.alarms || []);
    updateAlarmHistory(status.alarm_history || []);
}

function updateSerialStatus(connected) {
    elements.serialStatus.classList.toggle('connected', connected);
    elements.serialStatus.classList.remove('reconnecting');
    elements.serialText.textContent = connected ? 'Connected' : 'Disconnected';
    elements.connectBtn.disabled = connected;
    elements.disconnectBtn.disabled = !connected;
}

function updateWsStatus(connected) {
    elements.wsStatus.classList.toggle('connected', connected);
    elements.wsText.textContent = connected ? 'Connected' : 'Disconnected';
}

function updateModeButtons() {
    elements.modeManualBtn.classList.toggle('active', currentMode === 'manual');
    elements.modeAutoBtn.classList.toggle('active', currentMode === 'automatic');
}

function updateAlarms(alarms) {
    const hasAlarms = alarms.length > 0;
    elements.alarmStatus.classList.toggle('has-alarms', hasAlarms);

    elements.alarmList.innerHTML = alarms.map(alarm =>
        `<li>${formatAlarm(alarm)}</li>`
    ).join('');
}

function updateAlarmHistory(history) {
    if (!elements.alarmHistory) return;

    if (history.length === 0) {
        elements.alarmHistory.innerHTML = '<li class="no-history">No alarm history</li>';
        return;
    }

    elements.alarmHistory.innerHTML = history.map(entry => {
        const ts = new Date(entry.timestamp);
        const dateStr = ts.toLocaleDateString('en-GB', {
            day: '2-digit', month: '2-digit', year: '2-digit'
        });
        const timeStr = ts.toLocaleTimeString('en-GB', {
            hour: '2-digit', minute: '2-digit'
        });
        return `<li><span class="history-time">${dateStr} - ${timeStr}</span> => ${entry.message}</li>`;
    }).join('');
}

function formatAlarm(alarm) {
    const alarmNames = {
        'vertical_limit': 'Vertical Limit',
        'tilt_limit_flat': 'Tilt Limit - Panel Flat (stow)',
        'west_limit': 'West Limit',
        'wind_speed': 'Wind Speed Exceeded',
        'actuator_current': 'Actuator Current',
        'rotation_current': 'Rotation Current',
        'unknown_alarm_6': 'Unknown Alarm (bit 6)',
        'encoder_error': 'Encoder Error - Motor actuator limit not detected (BLOCKS ALL MOVEMENT)',
    };
    return alarmNames[alarm] || alarm;
}

function log(message) {
    const timestamp = new Date().toLocaleTimeString();
    const logLine = `[${timestamp}] ${message}\n`;
    elements.debugLog.textContent += logLine;
    elements.debugLog.scrollTop = elements.debugLog.scrollHeight;
}

// =============================================================================
// Serial Port Functions
// =============================================================================

async function refreshPorts() {
    try {
        const data = await apiCall('/serial/ports');
        elements.portSelect.innerHTML = '<option value="">Select port...</option>';

        data.ports.forEach(port => {
            const option = document.createElement('option');
            option.value = port.device;
            option.textContent = `${port.device} - ${port.description}`;
            elements.portSelect.appendChild(option);
        });

        log(`Found ${data.ports.length} serial ports`);
    } catch (error) {
        log(`Failed to refresh ports: ${error.message}`);
    }
}

async function connect() {
    const port = elements.portSelect.value;
    const baudrate = parseInt(elements.baudrateSelect.value);

    if (!port) {
        alert('Please select a port');
        return;
    }

    try {
        const data = await apiCall(`/serial/connect?port=${encodeURIComponent(port)}&baudrate=${baudrate}`, 'POST');
        log(data.message);
    } catch (error) {
        log(`Connection failed: ${error.message}`);
    }
}

async function disconnect() {
    try {
        const data = await apiCall('/serial/disconnect', 'POST');
        log(data.message);
    } catch (error) {
        log(`Disconnect failed: ${error.message}`);
    }
}

// =============================================================================
// Control Functions
// =============================================================================

async function setMode(mode) {
    try {
        const data = await apiCall(`/tracker/mode/${mode}`, 'POST');
        log(data.message);
    } catch (error) {
        log(`Set mode failed: ${error.message}`);
    }
}

async function startMove(direction) {
    try {
        await apiCall(`/tracker/move/${direction}/start`, 'POST');
        log(`Moving ${direction}`);
    } catch (error) {
        log(`Move failed: ${error.message}`);
    }
}

async function stopMove(direction) {
    try {
        await apiCall(`/tracker/move/${direction}/stop`, 'POST');
        log(`Stopped ${direction}`);
    } catch (error) {
        log(`Stop failed: ${error.message}`);
    }
}

async function stopAll() {
    try {
        const data = await apiCall('/tracker/stop', 'POST');
        log(data.message);
    } catch (error) {
        log(`Stop failed: ${error.message}`);
    }
}

async function moveForDuration(direction, durationMs) {
    try {
        await apiCall(`/tracker/move/${direction}/start`, 'POST');
        log(`Moving ${direction}...`);

        await new Promise(resolve => setTimeout(resolve, durationMs));

        await apiCall(`/tracker/move/${direction}/stop`, 'POST');
        log(`Stopped ${direction}`);
    } catch (error) {
        log(`Move failed: ${error.message}`);
        try {
            await apiCall(`/tracker/move/${direction}/stop`, 'POST');
        } catch (e) {}
    }
}

async function clearAlarms() {
    try {
        const data = await apiCall('/tracker/alarms/clear', 'POST');
        log(data.message);
    } catch (error) {
        log(`Clear alarms failed: ${error.message}`);
    }
}

async function setMaxWind() {
    const value = parseInt(elements.maxWindInput.value);

    if (isNaN(value) || value < 0 || value > 99) {
        alert('Wind threshold must be between 0 and 99');
        return;
    }

    try {
        const data = await apiCall('/tracker/wind', 'POST', { max_wind: value });
        log(data.message);
    } catch (error) {
        log(`Set wind failed: ${error.message}`);
    }
}

async function resetLimits() {
    try {
        const data = await apiCall('/tracker/limits/reset', 'POST');
        log(data.message);
    } catch (error) {
        log(`Reset limits failed: ${error.message}`);
    }
}

async function sendRaw() {
    const hex = elements.rawHex.value.replace(/\s/g, '');

    if (!hex || !/^[0-9a-fA-F]+$/.test(hex)) {
        alert('Please enter valid hex data');
        return;
    }

    try {
        const data = await apiCall(`/serial/send?data=${hex}`, 'POST');
        log(`Sent: ${hex} - ${data.message}`);
    } catch (error) {
        log(`Send failed: ${error.message}`);
    }
}

// =============================================================================
// Ripple Effect
// =============================================================================

function addRipple(e) {
    const btn = e.currentTarget;
    const ripple = document.createElement('span');
    ripple.classList.add('ripple');
    const rect = btn.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    ripple.style.width = ripple.style.height = size + 'px';
    ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
    ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
    btn.appendChild(ripple);
    ripple.addEventListener('animationend', () => ripple.remove());
}

// =============================================================================
// Event Listeners
// =============================================================================

function setupEventListeners() {
    // Connection (with loading spinners)
    elements.refreshPortsBtn.addEventListener('click', () => withLoading(elements.refreshPortsBtn, refreshPorts));
    elements.connectBtn.addEventListener('click', () => withLoading(elements.connectBtn, connect));
    elements.disconnectBtn.addEventListener('click', () => withLoading(elements.disconnectBtn, disconnect));

    // Mode (with loading spinners)
    elements.modeManualBtn.addEventListener('click', () => withLoading(elements.modeManualBtn, () => setMode('manual')));
    elements.modeAutoBtn.addEventListener('click', () => withLoading(elements.modeAutoBtn, () => setMode('automatic')));

    // Movement - D-Pad buttons with click to move for fixed duration
    document.querySelectorAll('.dpad-btn[data-direction]').forEach(btn => {
        const direction = btn.dataset.direction;

        btn.addEventListener('click', async () => {
            await moveForDuration(direction, 500);
        });
    });

    // Stop button
    elements.stopBtn.addEventListener('click', () => withLoading(elements.stopBtn, stopAll));

    // Alarms (with loading spinner)
    elements.clearAlarmsBtn.addEventListener('click', () => withLoading(elements.clearAlarmsBtn, clearAlarms));

    // Observed Limits
    elements.resetLimitsBtn.addEventListener('click', () => withLoading(elements.resetLimitsBtn, resetLimits));

    // Parameters (with loading spinner)
    elements.setWindBtn.addEventListener('click', () => withLoading(elements.setWindBtn, setMaxWind));

    // Debug
    elements.debugPanel.querySelector('h2').addEventListener('click', () => {
        elements.debugPanel.classList.toggle('collapsed');
    });
    elements.sendRawBtn.addEventListener('click', () => withLoading(elements.sendRawBtn, sendRaw));
    elements.rawHex.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendRaw();
    });

    // Ripple effect on all buttons
    document.querySelectorAll('button').forEach(btn => {
        btn.addEventListener('click', addRipple);
    });
}

// =============================================================================
// Initialization
// =============================================================================

async function init() {
    log('Solar Tracker Control UI initialized');

    // Initialize SVG gauges
    initCompassTicks();
    initAltitudeTicks();
    initAltitudeTicksBelow();
    initWindTicks();

    setupEventListeners();

    // Connect WebSocket
    connectWebSocket();

    // Refresh serial ports
    await refreshPorts();

    // Get initial status and auto-select connected port
    try {
        const status = await apiCall('/tracker/status');
        updateUI(status);

        // If already connected, select that port in dropdown
        if (status.connection?.connected && status.connection?.port) {
            elements.portSelect.value = status.connection.port;
            log(`Auto-connected to ${status.connection.port}`);
        }
    } catch (error) {
        log(`Failed to get initial status: ${error.message}`);
    }
}

// Start when DOM is ready
document.addEventListener('DOMContentLoaded', init);
