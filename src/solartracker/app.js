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

    // Parameters
    windSpeed: document.getElementById('wind-speed'),
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
// WebSocket Functions
// =============================================================================

function connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        log('WebSocket connected');
        updateWsStatus(true);
        clearTimeout(wsReconnectTimer);
    };

    ws.onclose = () => {
        log('WebSocket disconnected');
        updateWsStatus(false);
        // Attempt to reconnect after 3 seconds
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

    // Update sun position
    if (status.sun_position) {
        elements.sunAzimuth.textContent =
            status.sun_position.azimuth !== null ? status.sun_position.azimuth.toFixed(2) : '--';
        elements.sunAltitude.textContent =
            status.sun_position.altitude !== null ? status.sun_position.altitude.toFixed(2) : '--';
    }

    // Update panel position
    if (status.position) {
        elements.posHorizontal.textContent =
            status.position.horizontal !== null ? status.position.horizontal.toFixed(2) : '--';
        elements.posVertical.textContent =
            status.position.vertical !== null ? status.position.vertical.toFixed(2) : '--';
    }

    // Update wind
    elements.windSpeed.textContent =
        status.wind_speed !== null ? status.wind_speed : '--';
    if (status.max_wind_threshold !== null) {
        elements.maxWindInput.value = status.max_wind_threshold;
    }

    // Update alarms
    updateAlarms(status.alarms || []);
    updateAlarmHistory(status.alarm_history || []);
}

function updateSerialStatus(connected) {
    elements.serialStatus.classList.toggle('connected', connected);
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
    // Alarm names (matching STcontrol terminology)
    // "fim de curso" = end of travel / limit switch
    const alarmNames = {
        'vertical_limit': 'Vertical Limit',
        'east_limit': 'Horizontal Limit (East)',
        'west_limit': 'Horizontal Limit (West)',
        'wind_speed': 'Wind Speed Exceeded',
        'actuator_current': 'Actuator Current',
        'rotation_current': 'Rotation Current',
        'horizontal_limit': 'Horizontal Limit',
        'encoder_error': 'Encoder Error',
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
// Event Listeners
// =============================================================================

function setupEventListeners() {
    // Connection
    elements.refreshPortsBtn.addEventListener('click', refreshPorts);
    elements.connectBtn.addEventListener('click', connect);
    elements.disconnectBtn.addEventListener('click', disconnect);

    // Mode
    elements.modeManualBtn.addEventListener('click', () => setMode('manual'));
    elements.modeAutoBtn.addEventListener('click', () => setMode('automatic'));

    // Movement - D-Pad buttons with press and release
    document.querySelectorAll('.dpad-btn[data-direction]').forEach(btn => {
        const direction = btn.dataset.direction;

        // Mouse events
        btn.addEventListener('mousedown', () => startMove(direction));
        btn.addEventListener('mouseup', () => stopMove(direction));
        btn.addEventListener('mouseleave', () => stopMove(direction));

        // Touch events for mobile
        btn.addEventListener('touchstart', (e) => {
            e.preventDefault();
            startMove(direction);
        });
        btn.addEventListener('touchend', (e) => {
            e.preventDefault();
            stopMove(direction);
        });
    });

    // Stop button
    elements.stopBtn.addEventListener('click', stopAll);

    // Alarms
    elements.clearAlarmsBtn.addEventListener('click', clearAlarms);

    // Parameters
    elements.setWindBtn.addEventListener('click', setMaxWind);

    // Debug
    elements.debugPanel.querySelector('h2').addEventListener('click', () => {
        elements.debugPanel.classList.toggle('collapsed');
    });
    elements.sendRawBtn.addEventListener('click', sendRaw);
    elements.rawHex.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendRaw();
    });
}

// =============================================================================
// Initialization
// =============================================================================

async function init() {
    log('Solar Tracker Control UI initialized');

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
