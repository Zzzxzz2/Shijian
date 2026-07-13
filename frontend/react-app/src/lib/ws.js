/**
 * WebSocket client wrapper.
 *
 * Usage:
 *   import ws from '../lib/ws';
 *   ws.connect('/ws/runs/123', (msg) => console.log(msg));
 *   ws.close();
 */

let wsInstance = null;
let reconnectAttempts = 0;
const MAX_RETRIES = 3;
const RETRY_DELAY = 3000;
let reconnectTimer = null;
let currentPath = null;
let messageHandler = null;

function connect(path, onMessage) {
  close();

  currentPath = path;
  messageHandler = onMessage;
  reconnectAttempts = 0;

  _connect();
}

function _connect() {
  if (!currentPath) return;

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = protocol + '//' + window.location.host + currentPath;

  try {
    wsInstance = new WebSocket(url);

    wsInstance.onopen = () => {
      reconnectAttempts = 0;
    };

    wsInstance.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (messageHandler) messageHandler(msg);
      } catch (e) {
        console.error('WS parse error:', e);
      }
    };

    wsInstance.onclose = () => {
      wsInstance = null;
      _attemptReconnect();
    };

    wsInstance.onerror = () => {
      // onclose fires after onerror
    };
  } catch (e) {
    console.error('WS connection error:', e);
    _attemptReconnect();
  }
}

function _attemptReconnect() {
  if (reconnectAttempts >= MAX_RETRIES) {
    console.warn('WS max reconnect reached');
    return;
  }
  reconnectAttempts++;
  reconnectTimer = setTimeout(_connect, RETRY_DELAY);
}

function close() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (wsInstance) {
    try { wsInstance.close(); } catch (e) { /* ignore */ }
    wsInstance = null;
  }
  currentPath = null;
  messageHandler = null;
  reconnectAttempts = 0;
}

function isConnected() {
  return wsInstance?.readyState === WebSocket.OPEN;
}

export default { connect, close, isConnected };
