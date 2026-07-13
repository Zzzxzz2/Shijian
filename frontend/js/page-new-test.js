/* global window.App */
(function () {
  'use strict';

  var page = {
    projectId: null,
  };

  page.init = function (params) {
    page.projectId = params.id;
    page.loadProjectInfo();
    page.loadCases();
    page.bindEvents();
  };

  page.loadProjectInfo = function () {
    window.App.api.get('/api/projects/' + page.projectId)
      .then(function (data) {
        var el = document.querySelector('#project-name span');
        if (el) el.textContent = data.name || '';
      })
      .catch(function (err) {
        console.error('Load project error:', err);
      });
  };

  page.bindEvents = function () {
    // Select all
    document.getElementById('select-all').addEventListener('change', function () {
      var checked = this.checked;
      var checkboxes = document.querySelectorAll('#case-list input[type="checkbox"].case-select');
      for (var i = 0; i < checkboxes.length; i++) {
        checkboxes[i].checked = checked;
      }
    });

    // Filter
    document.getElementById('case-filter').addEventListener('change', function () {
      page.loadCases();
    });

    // Start run
    document.getElementById('start-run-btn').addEventListener('click', function () {
      page.startRun();
    });
  };

  page.loadCases = function () {
    var filter = document.getElementById('case-filter');
    var filterVal = filter ? filter.value : '';
    var url = '/api/projects/' + page.projectId + '/cases?offset=0&limit=200';
    if (filterVal) url += '&test_type=' + filterVal;

    window.App.api.get(url)
      .then(function (data) {
        var cases = Array.isArray(data) ? data : (data.items || []);
        page.renderCases(cases);
      })
      .catch(function (err) {
        console.error('Load cases error:', err);
      });
  };

  page.renderCases = function (cases) {
    var tbody = document.getElementById('case-list');
    if (cases.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="text-center py-12 text-gray-400">\u6682\u65e0\u7528\u4f8b</td></tr>';
      return;
    }

    var html = '';
    for (var i = 0; i < cases.length; i++) {
      var c = cases[i];
      var typeBadge = c.test_type || '-';
      var typeColor = typeBadge === 'API' ? 'bg-blue-100 text-blue-700'
        : typeBadge === 'UI' ? 'bg-purple-100 text-purple-700'
        : typeBadge === 'Perf' ? 'bg-orange-100 text-orange-700'
        : 'bg-gray-100 text-gray-700';

      html += '<tr class="border-b border-gray-50">'
        + '<td class="px-3 py-3 text-center"><input type="checkbox" class="case-select rounded border-gray-300 text-primary-600 focus:ring-primary-500" value="' + c.id + '" /></td>'
        + '<td class="px-3 py-3 font-medium text-gray-800">' + window.App.utils.escapeHtml(c.name) + '</td>'
        + '<td class="px-3 py-3"><span class="inline-block px-2 py-0.5 rounded text-xs font-medium ' + typeColor + '">' + window.App.utils.escapeHtml(typeBadge) + '</span></td>'
        + '<td class="px-3 py-3 text-gray-500 hidden md:table-cell">' + window.App.utils.escapeHtml(c.source || 'manual') + '</td></tr>';
    }
    tbody.innerHTML = html;

    // Reset select-all state
    document.getElementById('select-all').checked = false;
  };

  page.startRun = function () {
    var checkboxes = document.querySelectorAll('#case-list input[type="checkbox"].case-select:checked');
    var caseIds = [];
    for (var i = 0; i < checkboxes.length; i++) {
      caseIds.push(parseInt(checkboxes[i].value));
    }

    if (caseIds.length === 0) {
      window.App.utils.showToast('\u8bf7\u81f3\u5c11\u9009\u62e9\u4e00\u4e2a\u6d4b\u8bd5\u7528\u4f8b', 'error');
      return;
    }

    window.App.utils.showLoading();
    window.App.api.post('/api/projects/' + page.projectId + '/runs', { case_ids: caseIds })
      .then(function (data) {
        window.App.utils.showToast('\u6267\u884c\u5df2\u521b\u5efa', 'success');
        var runId = data.id;
        window.App.router.navigate('/runs/' + runId);
      })
      .catch(function (err) {
        window.App.utils.showToast(err.detail || '\u521b\u5efa\u5931\u8d25', 'error');
      })
      .finally(function () {
        window.App.utils.hideLoading();
      });
  };

  window.App = window.App || {};
  window.App.newTest = page;
})();
