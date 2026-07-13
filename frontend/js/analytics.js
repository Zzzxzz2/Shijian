/* global window */
/**
 * Analytics tracking module.
 * Tracks page entries/leaves via POST /api/analytics/enter and PUT /api/analytics/leave/:id.
 * Uses sendBeacon for leave events to ensure delivery on page unload.
 */
(function () {
  'use strict';

  var sessionId = generateUUID();
  var currentViewId = null;
  var enterTime = null;
  var enabled = true;
  var baseUrl = '';

  function generateUUID() {
    // Simple UUID v4 for session identification
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0;
      var v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }

  function getReferrer() {
    return document.referrer || '';
  }

  function getUserAgent() {
    return navigator.userAgent || '';
  }

  /**
   * Send a page enter event.
   * @param {string} path - The page path (e.g. '/projects/123')
   * @returns {Promise<number|null>} view_id from server, or null on failure
   */
  function trackEnter(path) {
    if (!enabled) return Promise.resolve(null);
    // Avoid tracking analytics page itself to prevent loops
    if (path === '/analytics') return Promise.resolve(null);

    return fetch(baseUrl + '/api/analytics/enter', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({
        path: path,
        referrer: getReferrer(),
        user_agent: getUserAgent(),
        session_id: sessionId
      })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        currentViewId = data.view_id;
        enterTime = Date.now();
        return data.view_id;
      })
      .catch(function (err) {
        console.warn('Analytics enter failed:', err);
        return null;
      });
  }

  /**
   * Send a page leave event. Uses sendBeacon for reliability.
   */
  function trackLeave() {
    if (!enabled || currentViewId === null || enterTime === null) return;
    var duration = Date.now() - enterTime;
    var data = JSON.stringify({ duration_ms: duration });

    try {
      var blob = new Blob([data], { type: 'application/json' });
      navigator.sendBeacon(baseUrl + '/api/analytics/leave/' + currentViewId, blob);
    } catch (e) {
      // Fallback to fetch
      fetch(baseUrl + '/api/analytics/leave/' + currentViewId, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: data,
        credentials: 'same-origin',
        keepalive: true
      }).catch(function () {});
    }

    currentViewId = null;
    enterTime = null;
  }

  /**
   * Called by the router whenever navigation occurs.
   * Sends leave for the old page, then enter for the new page.
   * @param {string} newPath
   */
  function nav(newPath) {
    trackLeave();
    trackEnter(newPath);
  }

  // ── Expose global API ────────────────────────────────────────────────
  window.__analytics__ = {
    nav: nav,
    trackEnter: trackEnter,
    trackLeave: trackLeave,
    sessionId: sessionId
  };
})();
