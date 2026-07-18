/* global window.App */
(function () {
  'use strict';

  var page = {
    runId: null,
    projectId: null,
    pollTimer: null,
    runData: null,
    results: [],
    cases: [],
  };

  page.init = function (params) {
    page.runId = params.id;
    page.projectId = null;
    page.pollTimer = null;
    page.ws = null;
    page.wsRetries = 0;
    page.maxWsRetries = 10;
    page.isDone = false;
    page.loadRun();

    // Report button
    var reportBtn = document.getElementById('report-btn');
    if (reportBtn) {
      reportBtn.addEventListener('click', function () {
        if (!page.projectId) return;
        var reportWindow = window.open('', '_blank');
        if (!reportWindow) {
          window.App.utils.showToast('浏览器阻止了报告窗口', 'error');
          return;
        }
        var token = localStorage.getItem('token');
        fetch('/api/projects/' + page.projectId + '/runs/' + page.runId + '/report', {
          headers: token ? { 'Authorization': 'Bearer ' + token } : {},
        })
          .then(function (resp) {
            if (!resp.ok) throw new Error('生成报告失败 (' + resp.status + ')');
            return resp.text();
          })
          .then(function (html) {
            reportWindow.document.open();
            reportWindow.document.write(html);
            reportWindow.document.close();
          })
          .catch(function (err) {
            reportWindow.close();
            window.App.utils.showToast(err.message || '生成报告失败', 'error');
          });
      });
    }
  };

  page.loadRun = function () {
    // Use the standalone run endpoint (no project_id needed)
    window.App.api.get('/api/runs/' + page.runId)
      .then(function (data) {
        page.projectId = data.project_id;
        page.runData = data;
        page.cases = data.cases || [];
        page.renderRun();
        page.loadResults();
        // Update back link
        document.getElementById('back-link').setAttribute('href', '#/projects/' + page.projectId);
        // Try to get project name from the run's project_id
        window.App.api.get('/api/projects/' + page.projectId, { showLoading: false })
          .then(function (proj) {
            var el = document.querySelector('#project-name span');
            if (el) el.textContent = proj.name || '';
          })
          .catch(function () { /* ignore */ });
        // Start WebSocket or polling
        if (data.status === 'queued' || data.status === 'running') {
          page.connectWebSocket();
        } else {
          page.isDone = true;
        }
      })
      .catch(function (err) {
        console.error('Load run error:', err);
        var el = document.getElementById('case-results');
        if (el) el.innerHTML = '<p class="text-center py-8 text-gray-400">\u672a\u627e\u5230\u6267\u884c\u8bb0\u5f55</p>';
      });
  };

  page.loadResults = function () {
    if (!page.projectId) return;
    window.App.api.get('/api/runs/' + page.runId + '/results')
      .then(function (data) {
        page.results = Array.isArray(data) ? data : (data.items || []);
        page.renderResults();
      });
    // Load diff when run is done
    if (page.runData && page.runData.status === 'done') {
      page.loadDiff();
    }
  };

  page.renderRun = function () {
    var run = page.runData;
    if (!run) return;

    // Status badge
    var badge = document.getElementById('status-badge');
    var statusMap = {
      'queued': { text: '\u6392\u961f\u4e2d', cls: 'bg-yellow-100 text-yellow-700' },
      'running': { text: '\u6267\u884c\u4e2d', cls: 'bg-blue-100 text-blue-700' },
      'done': { text: '\u5df2\u5b8c\u6210', cls: 'bg-green-100 text-green-700' },
      'failed': { text: '\u5931\u8d25', cls: 'bg-red-100 text-red-700' },
    };
    var s = statusMap[run.status] || { text: run.status, cls: 'bg-gray-100 text-gray-600' };
    badge.textContent = s.text;
    badge.className = 'px-3 py-1 rounded-full text-sm font-medium ' + s.cls;

    // Show report button only when run is done
    var reportBtn = document.getElementById('report-btn');
    if (reportBtn) {
      reportBtn.classList.toggle('hidden', run.status !== 'done');
    }

    // Summary from run.summary
    try {
      var summary = JSON.parse(run.summary || '{}');
      document.getElementById('sum-total').textContent = summary.total || 0;
      document.getElementById('sum-pass').textContent = summary.pass || 0;
      document.getElementById('sum-fail').textContent = summary.fail || 0;
      document.getElementById('sum-error').textContent = summary.error || 0;
    } catch (e) {
      // ignore
    }

    // Timing
    document.getElementById('started-at').textContent = run.started_at ? window.App.utils.formatDate(run.started_at) : '-';
    document.getElementById('finished-at').textContent = run.finished_at ? window.App.utils.formatDate(run.finished_at) : '-';
    if (run.started_at && run.finished_at) {
      var dur = (new Date(run.finished_at) - new Date(run.started_at)) / 1000;
      document.getElementById('total-duration').textContent = dur.toFixed(1) + 's';
    } else if (run.started_at) {
      document.getElementById('total-duration').textContent = '\u6267\u884c\u4e2d...';
    }

    // Load diff if done
    if (run.status === 'done') {
      page.loadDiff();
    }
  };

  page.loadDiff = function () {
    if (page._diffLoaded) return;
    page._diffLoaded = true;
    window.App.api.get('/api/runs/' + page.runId + '/diff')
      .then(function (data) {
        page.renderDiff(data);
      })
      .catch(function () { /* no previous run or error */ });
  };

  page.renderDiff = function (data) {
    if (!data || !data.diff || data.diff.length === 0) return;
    var section = document.getElementById('diff-section');
    if (!section) return;
    section.classList.remove('hidden');

    // Summary
    var summary = data.summary || {};
    var summaryEl = document.getElementById('diff-summary');
    summaryEl.innerHTML = '';
    if (summary.new_failures > 0) summaryEl.innerHTML += '<span class="px-3 py-1 rounded-full text-sm font-medium bg-red-100 text-red-700">' + summary.new_failures + ' \u4e2a\u65b0\u589e\u5931\u8d25</span>';
    if (summary.new_passes > 0) summaryEl.innerHTML += '<span class="px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-700">' + summary.new_passes + ' \u4e2a\u65b0\u901a\u8fc7</span>';
    summaryEl.innerHTML += '<span class="px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-700">' + summary.unchanged + ' \u4e2a\u672a\u53d8\u5316</span>';

    // Diff table
    var tbody = document.getElementById('diff-list');
    var html = '';
    for (var i = 0; i < data.diff.length; i++) {
      var d = data.diff[i];
      var prevBadge = d.previous ? '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium ' + (d.previous === 'pass' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700') + '">' + d.previous + '</span>' : '<span class="text-gray-400">-</span>';
      var currBadge = '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium ' + (d.current === 'pass' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700') + '">' + d.current + '</span>';
      var changeBadge = '';
      if (d.status === 'new_failure') changeBadge = '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">\u65b0\u589e\u5931\u8d25</span>';
      else if (d.status === 'new_pass') changeBadge = '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">\u65b0\u901a\u8fc7</span>';
      else if (d.status === 'new_case') changeBadge = '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700">\u65b0\u7528\u4f8b</span>';
      else changeBadge = '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">\u672a\u53d8\u5316</span>';
      html += '<tr class="border-b border-gray-50">'
        + '<td class="px-4 py-3 font-medium text-gray-800">' + window.App.utils.escapeHtml(d.case_name) + '</td>'
        + '<td class="px-4 py-3 text-center">' + prevBadge + '</td>'
        + '<td class="px-4 py-3 text-center">' + currBadge + '</td>'
        + '<td class="px-4 py-3 text-center">' + changeBadge + '</td>'
        + '</tr>';
    }
    tbody.innerHTML = html;
  };

  page.renderResults = function () {
    var container = document.getElementById('case-results');
    if (page.results.length === 0) {
      container.innerHTML = '<p class="text-center py-8 text-gray-400">\u6682\u65e0\u7ed3\u679c</p>';
      return;
    }

    // Also try loading diff after results are rendered
    if (page.runData && page.runData.status === 'done' && !page._diffLoaded) {
      page.loadDiff();
    }

    // Build with DocumentFragment for batch DOM rendering
    var fragment = document.createDocumentFragment();

    for (var i = 0; i < page.results.length; i++) {
      var r = page.results[i];
      var caseName = '\u7528\u4f8b #' + r.case_id;
      // Try to find case name from cases list
      for (var j = 0; j < page.cases.length; j++) {
        if (page.cases[j].id === r.case_id) {
          caseName = page.cases[j].name;
          break;
        }
      }

      var statusDot = r.status === 'pass' ? 'bg-green-500'
        : r.status === 'fail' ? 'bg-red-500'
        : 'bg-yellow-500';
      var durationText = r.duration_ms ? (r.duration_ms / 1000).toFixed(2) + 's' : '-';

      var div = document.createElement('div');
      div.className = 'bg-white rounded-lg border border-gray-200 overflow-hidden';

      // Header (always visible)
      var header = document.createElement('div');
      header.className = 'flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors';
      header.setAttribute('data-idx', i);
      header.innerHTML = '<div class="flex items-center gap-2">'
        + '<span class="inline-block w-2 h-2 rounded-full ' + statusDot + '"></span>'
        + '<span class="text-sm font-medium text-gray-800">' + window.App.utils.escapeHtml(caseName) + '</span>'
        + '</div>'
        + '<div class="flex items-center gap-3">'
        + '<span class="text-xs text-gray-500">' + durationText + '</span>'
        + '<svg class="w-4 h-4 text-gray-400 transform transition-transform expand-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>'
        + '</div>';

      header.addEventListener('click', function () {
        var detail = this.nextElementSibling;
        var icon = this.querySelector('.expand-icon');
        if (detail.classList.contains('hidden')) {
          detail.classList.remove('hidden');
          icon.style.transform = 'rotate(180deg)';
        } else {
          detail.classList.add('hidden');
          icon.style.transform = 'rotate(0deg)';
        }
      });

      // Detail (hidden by default)
      var detail = document.createElement('div');
      detail.className = 'hidden px-4 py-3 border-t border-gray-100 bg-gray-50 text-xs';
      detail.innerHTML = page.renderResultDetail(r);

      div.appendChild(header);
      div.appendChild(detail);
      fragment.appendChild(div);
    }

    container.innerHTML = '';
    container.appendChild(fragment);
  };

  page.renderResultDetail = function (r) {
    var d = r.detail || {};
    var html = '';
    var assetToken = encodeURIComponent(localStorage.getItem('token') || '');

    // Check if this is a UI result (has steps)
    if (d.steps && d.steps.length > 0) {
      html += '<div class="mb-3">'
        + '<p class="font-semibold text-gray-600 mb-2">\u64cd\u4f5c\u6b65\u9aa4</p>';
      for (var si = 0; si < d.steps.length; si++) {
        var step = d.steps[si];
        var stepStatus = step.status === 'pass' ? 'text-green-500' : step.status === 'error' ? 'text-red-500' : 'text-yellow-500';
        var stepIcon = step.status === 'pass' ? '\u2713' : step.status === 'error' ? '\u2717' : '?';
        html += '<div class="mb-2 p-2 bg-white rounded border border-gray-200">'
          + '<div class="flex items-center gap-2 mb-1">'
          + '<span class="' + stepStatus + ' font-bold">' + stepIcon + '</span>'
          + '<span class="font-medium text-gray-700">' + window.App.utils.escapeHtml(step.action || '') + '</span>';
        if (step.target) html += ' <span class="text-gray-500">' + window.App.utils.escapeHtml(step.target) + '</span>';
        if (step.value) html += ' <span class="text-gray-400">\u2192 ' + window.App.utils.escapeHtml(step.value) + '</span>';
        html += '<span class="ml-auto text-xs text-gray-400">' + (step.duration_ms ? (step.duration_ms / 1000).toFixed(2) + 's' : '') + '</span>'
          + '</div>';
        if (step.error) {
          html += '<p class="text-red-500 text-xs mt-1">' + window.App.utils.escapeHtml(step.error) + '</p>';
        }
        if (step.screenshot) {
          html += '<div class="mt-2"><img src="/api/screenshots/' + page.runId + '/' + r.case_id + '/' + encodeURIComponent(step.screenshot.split(/[/\\]/).pop()) + '?token=' + assetToken + '" class="max-w-full h-auto rounded border border-gray-200" style="max-height:200px" /></div>';
        }
        html += '</div>';
      }
      html += '</div>';

      // Screenshots gallery
      if (d.screenshots && d.screenshots.length > 0) {
        html += '<div class="mb-3">'
          + '<p class="font-semibold text-gray-600 mb-2">\u622a\u56fe</p>'
          + '<div class="flex flex-wrap gap-2">';
        for (var ss = 0; ss < d.screenshots.length; ss++) {
          var ssPath = d.screenshots[ss];
          var filename = ssPath.split(/[/\\]/).pop();
          var protectedUrl = '/api/screenshots/' + page.runId + '/' + r.case_id + '/' + encodeURIComponent(filename) + '?token=' + assetToken;
          html += '<a href="' + protectedUrl + '" target="_blank" rel="noreferrer">'
            + '<img src="' + protectedUrl + '" class="w-24 h-18 object-cover rounded border border-gray-200 hover:border-primary-400" />'
            + '</a>';
        }
        html += '</div></div>';
      }
    } else {
      // API result detail (existing logic)
      html += '<div class="mb-3">'
        + '<p class="font-semibold text-gray-600 mb-1">\u8bf7\u6c42</p>'
        + '<p class="text-gray-700 font-mono">' + window.App.utils.escapeHtml(d.method || '') + ' ' + window.App.utils.escapeHtml(d.request_url || '') + '</p>'
        + '</div>';

      html += '<div class="mb-3">'
        + '<p class="font-semibold text-gray-600 mb-1">\u54cd\u5e94</p>'
        + '<p class="text-gray-700 font-mono">Status: ' + (d.status_code || '-') + '</p>'
        + '</div>';

      if (d.response_body !== undefined && d.response_body !== null) {
        var bodyStr = typeof d.response_body === 'object' ? JSON.stringify(d.response_body, null, 2) : String(d.response_body);
        if (bodyStr.length > 500) bodyStr = bodyStr.substring(0, 500) + '...';
        html += '<div class="mb-3">'
          + '<p class="font-semibold text-gray-600 mb-1">\u54cd\u5e94\u4f53</p>'
          + '<pre class="bg-white p-2 rounded border border-gray-200 overflow-x-auto max-h-32">' + window.App.utils.escapeHtml(bodyStr) + '</pre>'
          + '</div>';
      }
    }

    // Error
    if (d.error) {
      html += '<div class="mb-3">'
        + '<p class="font-semibold text-red-600 mb-1">\u9519\u8bef</p>'
        + '<p class="text-red-500">' + window.App.utils.escapeHtml(d.error) + '</p>'
        + '</div>';
    }

    // Assertions
    if (d.assertions && d.assertions.length > 0) {
      html += '<div>'
        + '<p class="font-semibold text-gray-600 mb-1">\u65ad\u8a00</p>';
      for (var i = 0; i < d.assertions.length; i++) {
        var a = d.assertions[i];
        var passed = a.passed;
        var icon = passed ? '<span class="text-green-500">\u2713</span>' : '<span class="text-red-500">\u2717</span>';
        var rule = a.rule || {};
        html += '<div class="flex items-start gap-2 mb-1">'
          + icon
          + '<span class="text-gray-700">' + window.App.utils.escapeHtml((rule.type || '') + ' ' + (rule.target || '') + ' ' + (rule.operator || '') + ' ' + (rule.expected !== undefined ? rule.expected : '')) + '</span>'
          + '</div>';
        if (!passed) {
          html += '<div class="ml-5 text-gray-500">\u5b9e\u9645\u503c: ' + window.App.utils.escapeHtml(String(a.actual !== null && a.actual !== undefined ? a.actual : '-')) + '</div>';
          if (a.error) {
            html += '<div class="ml-5 text-red-400">' + window.App.utils.escapeHtml(a.error) + '</div>';
          }
        }
      }
      html += '</div>';
    }

    return html;
  };

  page.startPolling = function () {
    if (page.pollTimer) clearInterval(page.pollTimer);
    page.pollTimer = setInterval(function () {
      window.App.api.get('/api/runs/' + page.runId)
        .then(function (data) {
          page.runData = data;
          page.cases = data.cases || page.cases;
          page.renderRun();
          page.loadResults();
          if (data.status === 'done' || data.status === 'failed') {
            page.stopPolling();
            page.isDone = true;
          }
        });
    }, 2000);
  };

  page.stopPolling = function () {
    if (page.pollTimer) {
      clearInterval(page.pollTimer);
      page.pollTimer = null;
    }
  };

  page.connectWebSocket = function () {
    if (page.ws) {
      try { page.ws.close(); } catch (e) { /* ignore */ }
      page.ws = null;
    }

    var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    var wsUrl = protocol + '//' + window.location.host + '/ws/runs/' + page.runId
      + '?token=' + encodeURIComponent(localStorage.getItem('token') || '');

    try {
      var socket = new WebSocket(wsUrl);
      page.ws = socket;

      socket.onopen = function () {
        page.wsRetries = 0;
      };

      socket.onmessage = function (event) {
        var msg;
        try {
          msg = JSON.parse(event.data);
        } catch (e) {
          console.error('WS message parse error:', e);
          return;
        }
        switch (msg.type) {
          case 'case_done':
            page.appendCaseResult(msg.data);
            break;
          case 'progress':
            page.updateProgress(msg.data);
            break;
          case 'run_done':
            page.setRunDone(msg.data);
            break;
          case 'error':
            window.App.utils.showToast(msg.data.message, 'error');
            break;
        }
      };

      socket.onclose = function () {
        page.ws = null;
        if (page.isDone) return;
        if (page.wsRetries < page.maxWsRetries) {
          page.wsRetries++;
          setTimeout(function () { page.connectWebSocket(); }, 3000);
        } else {
          console.warn('WS max retries (' + page.maxWsRetries + ') reached, falling back to polling');
          page.startPolling();
        }
      };

      socket.onerror = function () {
        // onclose will fire after onerror
      };
    } catch (e) {
      console.error('WS connection error:', e);
      if (!page.isDone) {
        page.startPolling();
      }
    }
  };

  page.closeWebSocket = function () {
    if (page.ws) {
      try { page.ws.close(); } catch (e) { /* ignore */ }
      page.ws = null;
    }
    page.stopPolling();
  };

  page.appendCaseResult = function (data) {
    var container = document.getElementById('case-results');
    // Remove "no results" placeholder
    if (container.querySelector('.text-gray-400')) {
      container.innerHTML = '';
    }

    var statusDot = data.status === 'pass' ? 'bg-green-500'
      : data.status === 'fail' ? 'bg-red-500'
      : 'bg-yellow-500';
    var durationText = data.duration_ms ? (data.duration_ms / 1000).toFixed(2) + 's' : '-';

    var div = document.createElement('div');
    div.className = 'bg-white rounded-lg border border-gray-200 overflow-hidden';

    var header = document.createElement('div');
    header.className = 'flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors';
    header.innerHTML = '<div class="flex items-center gap-2">'
      + '<span class="inline-block w-2 h-2 rounded-full ' + statusDot + '"></span>'
      + '<span class="text-sm font-medium text-gray-800">' + window.App.utils.escapeHtml(data.case_name || 'Case #' + data.case_id) + '</span>'
      + '</div>'
      + '<div class="flex items-center gap-3">'
      + '<span class="text-xs text-gray-500">' + durationText + '</span>'
      + '<svg class="w-4 h-4 text-gray-400 transform transition-transform expand-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>'
      + '</div>';

    header.addEventListener('click', function () {
      var detail = this.nextElementSibling;
      var icon = this.querySelector('.expand-icon');
      if (detail.classList.contains('hidden')) {
        detail.classList.remove('hidden');
        icon.style.transform = 'rotate(180deg)';
      } else {
        detail.classList.add('hidden');
        icon.style.transform = 'rotate(0deg)';
      }
    });

    var detail = document.createElement('div');
    detail.className = 'hidden px-4 py-3 border-t border-gray-100 bg-gray-50 text-xs';
    detail.innerHTML = page.renderResultDetail({ detail: data.detail, status: data.status, duration_ms: data.duration_ms });

    div.appendChild(header);
    div.appendChild(detail);
    container.appendChild(div);
  };

  page.updateProgress = function (data) {
    document.getElementById('sum-total').textContent = data.total || 0;
    document.getElementById('sum-pass').textContent = data.passed || 0;
    document.getElementById('sum-fail').textContent = data.failed || 0;
  };

  page.setRunDone = function (data) {
    page.isDone = true;
    page.stopPolling();
    page.closeWebSocket();
    // Merge WS data into runData without overwriting summary
    // (WS run_done lacks summary and may arrive before loadRun completes)
    if (page.runData) {
      page.runData.status = data.status;
      page.runData.result = data.result;
    } else {
      page.runData = { status: data.status, result: data.result };
    }
    // Re-fetch full run data from standalone endpoint
    window.App.api.get('/api/runs/' + page.runId)
      .then(function (fullData) {
        page.runData = fullData;
        page.cases = fullData.cases || page.cases;
        page.renderRun();
        page.loadResults();
      })
      .catch(function () { /* ignore */ });
  };

  // Cleanup on navigation
  window.addEventListener('hashchange', function () {
    page.closeWebSocket();
  }, { once: true });

  window.App = window.App || {};
  window.App.runDetail = page;
})();
