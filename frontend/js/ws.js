/**
 * WebSocket wrapper for real-time updates.
 * Usage: window.App.ws.connect(runId, onMessage)
 */

(function () {
  'use strict';

  var ws = null;
  var reconnectAttempts = 0;
  var maxReconnectAttempts = 3;
  var reconnectDelay = 3000;
  var reconnectTimer = null;
  var currentRunId = null;
  var messageHandler = null;

  function connect(runId, onMessage) {
    // Close existing connection
    close();

    currentRunId = runId;
    messageHandler = onMessage;
    reconnectAttempts = 0;

    _connect();
  }

  function _connect() {
    if (!currentRunId) return;

    var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    var wsUrl = protocol + '//' + window.location.host + '/ws/runs/' + currentRunId;

    try {
      ws = new WebSocket(wsUrl);

      ws.onopen = function () {
        reconnectAttempts = 0;
      };

      ws.onmessage = function (event) {
        try {
          var msg = JSON.parse(event.data);
          if (messageHandler) {
            messageHandler(msg);
          }
        } catch (e) {
          console.error('WS message parse error:', e);
        }
      };

      ws.onclose = function () {
        ws = null;
        _attemptReconnect();
      };

      ws.onerror = function () {
        // onclose will be called after onerror
      };
    } catch (e) {
      console.error('WS connection error:', e);
      _attemptReconnect();
    }
  }

  function _attemptReconnect() {
    if (reconnectAttempts >= maxReconnectAttempts) {
      console.warn('WS max reconnect attempts reached, falling back to polling');
      return;
    }

    reconnectAttempts++;
    reconnectTimer = setTimeout(function () {
      _connect();
    }, reconnectDelay);
  }

  function close() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }

    if (ws) {
      try {
        ws.close();
      } catch (e) {
        // ignore
      }
      ws = null;
    }

    currentRunId = null;
    messageHandler = null;
    reconnectAttempts = 0;
  }

  function isConnected() {
    return ws && ws.readyState === WebSocket.OPEN;
  }

  // Expose to App namespace
  window.App = window.App || {};
  window.App.ws = {
    connect: connect,
    close: close,
    isConnected: isConnected,
  };
})();
