/* global window.App */
(function () {
  'use strict';

  var page = {};

  page.init = function () {
    page.loadStats();
  };

  page.loadStats = function () {
    window.App.api.get('/api/token-stats')
      .then(function (data) {
        page.render(data);
      })
      .catch(function (err) {
        console.error('Load token stats error:', err);
      });
  };

  page.render = function (data) {
    // Summary cards
    document.getElementById('stat-total').textContent = (data.total_tokens || 0).toLocaleString();
    document.getElementById('stat-input').textContent = (data.total_input || 0).toLocaleString();
    document.getElementById('stat-output').textContent = (data.total_output || 0).toLocaleString();

    // Cost estimate: rough MiMo pricing (~0.5 yuan per 1M tokens)
    var totalTokens = data.total_tokens || 0;
    var costEstimate = (totalTokens / 1000000) * 0.5;
    document.getElementById('stat-cost').textContent = costEstimate < 0.01 ? '<\u00a50.01' : '\u00a5' + costEstimate.toFixed(2);

    // By date
    page.renderTable('table-date', data.by_date || [], function (r) {
      return '<td class="px-4 py-3 text-gray-800">' + window.App.utils.escapeHtml(r.date) + '</td>'
        + '<td class="px-4 py-3 text-right text-gray-600">' + (r.input_tokens || 0).toLocaleString() + '</td>'
        + '<td class="px-4 py-3 text-right text-gray-600">' + (r.output_tokens || 0).toLocaleString() + '</td>'
        + '<td class="px-4 py-3 text-right font-medium text-gray-800">' + ((r.input_tokens || 0) + (r.output_tokens || 0)).toLocaleString() + '</td>';
    });

    // By provider
    page.renderTable('table-provider', data.by_provider || [], function (r) {
      return '<td class="px-4 py-3 text-gray-800 capitalize">' + window.App.utils.escapeHtml(r.provider) + '</td>'
        + '<td class="px-4 py-3 text-right text-gray-600">' + (r.input_tokens || 0).toLocaleString() + '</td>'
        + '<td class="px-4 py-3 text-right text-gray-600">' + (r.output_tokens || 0).toLocaleString() + '</td>'
        + '<td class="px-4 py-3 text-right font-medium text-gray-800">' + ((r.input_tokens || 0) + (r.output_tokens || 0)).toLocaleString() + '</td>';
    });

    // By project
    page.renderTable('table-project', data.by_project || [], function (r) {
      return '<td class="px-4 py-3 text-gray-800">' + window.App.utils.escapeHtml(r.project_name) + '</td>'
        + '<td class="px-4 py-3 text-right text-gray-600">' + (r.input_tokens || 0).toLocaleString() + '</td>'
        + '<td class="px-4 py-3 text-right text-gray-600">' + (r.output_tokens || 0).toLocaleString() + '</td>'
        + '<td class="px-4 py-3 text-right font-medium text-gray-800">' + ((r.input_tokens || 0) + (r.output_tokens || 0)).toLocaleString() + '</td>';
    });
  };

  page.renderTable = function (tbodyId, rows, renderRow) {
    var tbody = document.getElementById(tbodyId);
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="text-center py-8 text-gray-400">\u6682\u65e0\u6570\u636e</td></tr>';
      return;
    }
    var html = '';
    for (var i = 0; i < rows.length; i++) {
      html += '<tr class="border-b border-gray-50">' + renderRow(rows[i]) + '</tr>';
    }
    tbody.innerHTML = html;
  };

  window.App = window.App || {};
  window.App.tokenStats = page;
})();
