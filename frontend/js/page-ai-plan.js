/* global window.App */
(function () {
  'use strict';

  var page = {
    projectId: null,
    docs: [],
    generatedCases: [],
  };

  page.init = function (params) {
    page.projectId = params.id;
    page.generatedCases = [];
    page.loadProjectInfo();
    page.loadDocs();
    page.bindEvents();
    page.showPhase('input');
  };

  page.loadProjectInfo = function () {
    window.App.api.get('/api/projects/' + page.projectId)
      .then(function (data) {
        var el = document.querySelector('#project-name span');
        if (el) el.textContent = data.name || '';
        var backLink = document.getElementById('back-link');
        if (backLink) backLink.setAttribute('href', '#/projects/' + page.projectId);
      });
  };

  page.loadDocs = function () {
    window.App.api.get('/api/projects/' + page.projectId + '/docs')
      .then(function (data) {
        var docs = Array.isArray(data) ? data : (data.items || []);
        page.docs = docs;
        page.renderDocs();
      });
  };

  page.renderDocs = function () {
    var container = document.getElementById('doc-list');
    if (!container) return;
    if (page.docs.length === 0) {
      container.innerHTML = '<p class="text-sm text-gray-400">\u6682\u65e0\u6587\u6863\uff08\u53ef\u9009\uff09</p>';
      return;
    }
    var html = '';
    for (var i = 0; i < page.docs.length; i++) {
      var d = page.docs[i];
      var hasText = d.content_text && d.content_text.trim().length > 0;
      var statusIcon = hasText
        ? '<span class="text-green-500 text-xs">\u2713 \u5df2\u63d0\u53d6</span>'
        : '<span class="text-gray-400 text-xs">\u672a\u63d0\u53d6</span>';
      html += '<div class="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">'
        + '<div class="flex items-center gap-2">'
        +   '<span class="text-gray-600 text-sm">' + window.App.utils.escapeHtml(d.filename) + '</span>'
        +   statusIcon
        + '</div>'
        + '<label class="flex items-center gap-1 text-xs text-gray-500 cursor-pointer">'
        +   '<input type="checkbox" class="doc-check rounded border-gray-300 text-primary-600 focus:ring-primary-500" value="' + d.id + '" ' + (hasText ? 'checked' : '') + ' />'
        +   '\u5f15\u7528'
        + '</label></div>';
    }
    container.innerHTML = html;
  };

  page.bindEvents = function () {
    // Generate
    document.getElementById('generate-btn').addEventListener('click', function () {
      page.generate();
    });

    // Upload doc
    document.getElementById('doc-upload').addEventListener('change', function (e) {
      var file = e.target.files[0];
      if (!file) return;
      page.uploadDoc(file);
    });

    // Regenerate
    document.getElementById('regenerate-btn').addEventListener('click', function () {
      page.generatedCases = [];
      page.showPhase('input');
    });

    // Save
    document.getElementById('save-btn').addEventListener('click', function () {
      page.saveCases();
    });

    // Add row
    document.getElementById('add-row-btn').addEventListener('click', function () {
      page.addEmptyRow();
    });

    // Delegated delete
    document.getElementById('preview-list').addEventListener('click', function (e) {
      if (e.target.closest('.delete-row')) {
        var idx = parseInt(e.target.closest('.delete-row').getAttribute('data-idx'));
        page.generatedCases.splice(idx, 1);
        page.renderPreview();
      }
    });
  };

  page.showPhase = function (phase) {
    var input = document.getElementById('phase-input');
    var preview = document.getElementById('phase-preview');
    if (phase === 'input') {
      input.classList.remove('hidden');
      preview.classList.add('hidden');
      document.getElementById('loading-state').classList.add('hidden');
      document.getElementById('token-usage').classList.add('hidden');
    } else {
      input.classList.add('hidden');
      preview.classList.remove('hidden');
    }
  };

  page.generate = function () {
    var req = document.getElementById('requirement').value.trim();
    if (!req) {
      window.App.utils.showToast('\u8bf7\u8f93\u5165\u6d4b\u8bd5\u9700\u6c42', 'error');
      return;
    }

    // Collect checked doc ids
    var docIds = [];
    var checks = document.querySelectorAll('.doc-check:checked');
    for (var i = 0; i < checks.length; i++) {
      docIds.push(parseInt(checks[i].value));
    }

    // Show loading
    document.getElementById('loading-state').classList.remove('hidden');
    document.getElementById('generate-btn').disabled = true;

    window.App.api.post('/api/projects/' + page.projectId + '/ai-plan', {
      requirement: req,
      doc_ids: docIds,
    })
      .then(function (data) {
        page.generatedCases = data.cases || [];
        page.showTokenUsage(data.token_usage);
        page.showPhase('preview');
        page.renderPreview();
      })
      .catch(function (err) {
        var msg = err.detail || '\u751f\u6210\u5931\u8d25';
        window.App.utils.showToast(msg, 'error');
      })
      .finally(function () {
        document.getElementById('loading-state').classList.add('hidden');
        document.getElementById('generate-btn').disabled = false;
      });
  };

  page.showTokenUsage = function (usage) {
    if (!usage) return;
    var total = (usage.input_tokens || 0) + (usage.output_tokens || 0);
    document.getElementById('token-count').textContent = total;
    document.getElementById('token-usage').classList.remove('hidden');
  };

  page.renderPreview = function () {
    var tbody = document.getElementById('preview-list');
    if (page.generatedCases.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="text-center py-8 text-gray-400">\u6682\u65e0\u751f\u6210\u7ed3\u679c</td></tr>';
      return;
    }

    var html = '';
    for (var i = 0; i < page.generatedCases.length; i++) {
      var c = page.generatedCases[i];
      var content = c.content || {};
      var method = content.method || '-';
      var url = content.url || '-';
      var assertions = content.assertions || [];
      var assertText = assertions.map(function (a) {
        return (a.target || '') + ' ' + (a.operator || '') + ' ' + (a.expected !== undefined ? a.expected : '');
      }).join('; ') || '-';

      var typeOptions = '<option value="API"' + (c.test_type === 'api' ? ' selected' : '') + '>API</option>'
        + '<option value="UI"' + (c.test_type === 'ui' ? ' selected' : '') + '>UI</option>'
        + '<option value="Perf"' + (c.test_type === 'perf' ? ' selected' : '') + '>Perf</option>';

      html += '<tr class="border-b border-gray-50" data-idx="' + i + '">'
        + '<td class="px-3 py-2 text-gray-400">' + (i + 1) + '</td>'
        + '<td class="px-3 py-2"><input class="case-name w-full px-2 py-1 border border-gray-200 rounded text-sm focus:outline-none focus:ring-1 focus:ring-primary-500" value="' + window.App.utils.escapeHtml(c.name || '') + '" /></td>'
        + '<td class="px-3 py-2"><select class="case-type w-full px-2 py-1 border border-gray-200 rounded text-sm focus:outline-none focus:ring-1 focus:ring-primary-500">' + typeOptions + '</select></td>'
        + '<td class="px-3 py-2 text-gray-600 text-xs">' + window.App.utils.escapeHtml(method) + '</td>'
        + '<td class="px-3 py-2 text-gray-600 text-xs truncate max-w-[160px]">' + window.App.utils.escapeHtml(url) + '</td>'
        + '<td class="px-3 py-2 text-gray-500 text-xs truncate max-w-[200px]">' + window.App.utils.escapeHtml(assertText) + '</td>'
        + '<td class="px-3 py-2 text-center"><button class="delete-row text-red-400 hover:text-red-600 text-xs" data-idx="' + i + '">\u5220\u9664</button></td>'
        + '</tr>';
    }
    tbody.innerHTML = html;

    // Bind input changes
    var rows = tbody.querySelectorAll('tr');
    for (var j = 0; j < rows.length; j++) {
      (function (row) {
        var idx = parseInt(row.getAttribute('data-idx'));
        var nameInput = row.querySelector('.case-name');
        var typeSelect = row.querySelector('.case-type');
        if (nameInput) {
          nameInput.addEventListener('input', function () {
            page.generatedCases[idx].name = this.value;
          });
        }
        if (typeSelect) {
          typeSelect.addEventListener('change', function () {
            page.generatedCases[idx].test_type = this.value.toLowerCase();
          });
        }
      })(rows[j]);
    }
  };

  page.addEmptyRow = function () {
    page.generatedCases.push({
      name: '',
      test_type: 'api',
      content: { method: 'GET', url: '', assertions: [] },
    });
    page.renderPreview();
    // Focus the new name input
    var inputs = document.querySelectorAll('.case-name');
    if (inputs.length > 0) inputs[inputs.length - 1].focus();
  };

  page.saveCases = function () {
    if (page.generatedCases.length === 0) {
      window.App.utils.showToast('\u6ca1\u6709\u53ef\u4fdd\u5b58\u7684\u7528\u4f8b', 'error');
      return;
    }

    // Collect current values from inputs
    var rows = document.querySelectorAll('#preview-list tr[data-idx]');
    for (var i = 0; i < rows.length; i++) {
      var idx = parseInt(rows[i].getAttribute('data-idx'));
      var nameInput = rows[i].querySelector('.case-name');
      var typeSelect = rows[i].querySelector('.case-type');
      if (nameInput) page.generatedCases[idx].name = nameInput.value;
      if (typeSelect) page.generatedCases[idx].test_type = typeSelect.value.toLowerCase();
    }

    // Build batch payload
    var cases = [];
    for (var j = 0; j < page.generatedCases.length; j++) {
      var c = page.generatedCases[j];
      if (!c.name || !c.name.trim()) continue;
      cases.push({
        name: c.name.trim(),
        test_type: c.test_type || 'api',
        source: 'ai_generated',
        content: c.content || {},
      });
    }

    if (cases.length === 0) {
      window.App.utils.showToast('\u8bf7\u81f3\u5c11\u586b\u5199\u4e00\u4e2a\u7528\u4f8b\u540d\u79f0', 'error');
      return;
    }

    window.App.utils.showLoading();
    window.App.api.post('/api/projects/' + page.projectId + '/cases/batch', { cases: cases })
      .then(function () {
        window.App.utils.showToast('\u5df2\u4fdd\u5b58 ' + cases.length + ' \u6761\u7528\u4f8b', 'success');
        window.App.router.navigate('/projects/' + page.projectId);
      })
      .catch(function (err) {
        window.App.utils.showToast(err.detail || '\u4fdd\u5b58\u5931\u8d25', 'error');
      })
      .finally(function () {
        window.App.utils.hideLoading();
      });
  };

  page.uploadDoc = function (file) {
    var formData = new FormData();
    formData.append('file', file);

    window.App.utils.showLoading();
    fetch('/api/projects/' + page.projectId + '/docs', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + window.App.auth.getToken() },
      body: formData,
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error('Upload failed');
        return resp.json();
      })
      .then(function () {
        window.App.utils.showToast('\u6587\u6863\u4e0a\u4f20\u6210\u529f', 'success');
        page.loadDocs();
      })
      .catch(function () {
        window.App.utils.showToast('\u4e0a\u4f20\u5931\u8d25', 'error');
      })
      .finally(function () {
        window.App.utils.hideLoading();
      });
  };

  window.App = window.App || {};
  window.App.aiPlan = page;
})();
