/* global window.App */
(function () {
  'use strict';

  var state = {
    currentPage: 1,
    pageSize: 10,
    searchTimer: null,
    abortController: null,
  };

  function init() {
    if (window.App.auth.isGuest()) {
      var btn = document.getElementById('new-project-btn');
      if (btn) btn.classList.add('hidden');
    }
    state.currentPage = 1;
    bindEvents();
    loadProjects();
  }

  function bindEvents() {
    // Search debounce
    var searchInput = document.getElementById('search-input');
    if (searchInput) searchInput.addEventListener('input', function () {
      clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(function () {
        state.currentPage = 1;
        loadProjects();
      }, 300);
    });

    // New project modal
    var newBtn = document.getElementById('new-project-btn');
    if (newBtn) newBtn.addEventListener('click', function () {
      var modal = document.getElementById('new-project-modal');
      if (modal) modal.classList.remove('hidden');
      var npName = document.getElementById('np-name');
      if (npName) { npName.value = ''; npName.focus(); }
      var npDesc = document.getElementById('np-desc');
      if (npDesc) npDesc.value = '';
    });

    var npCancel = document.getElementById('np-cancel');
    if (npCancel) npCancel.addEventListener('click', function () {
      document.getElementById('new-project-modal').classList.add('hidden');
    });

    var npConfirm = document.getElementById('np-confirm');
    if (npConfirm) npConfirm.addEventListener('click', function () {
      var name = document.getElementById('np-name').value.trim();
      var desc = document.getElementById('np-desc').value.trim();
      var url = document.getElementById('np-url').value.trim();
      if (!name) {
        window.App.utils.showToast('请输入项目名称', 'error');
        return;
      }
      window.App.api.post('/api/projects', { name: name, description: desc || undefined, url: url || undefined })
        .then(function () {
          window.App.utils.showToast('项目创建成功', 'success');
          document.getElementById('new-project-modal').classList.add('hidden');
          state.currentPage = 1;
          loadProjects();
        })
        .catch(function (err) {
          window.App.utils.showToast(err.detail || '创建失败', 'error');
        });
    });

    // Close modal on backdrop click
    var npModal = document.getElementById('new-project-modal');
    if (npModal) npModal.addEventListener('click', function (e) {
      if (e.target === this) this.classList.add('hidden');
    });
  }

  function loadProjects() {
    if (state.abortController) state.abortController.abort();
    state.abortController = new AbortController();

    var search = document.getElementById('search-input').value.trim();
    var offset = (state.currentPage - 1) * state.pageSize;

    window.App.api.get('/api/projects?search=' + encodeURIComponent(search) + '&offset=' + offset + '&limit=' + state.pageSize,
      { signal: state.abortController.signal })
      .then(function (data) {
        var items = data.items || (Array.isArray(data) ? data : []);
        var total = data.total || items.length;
        renderTable(items, Math.max(1, Math.ceil(total / state.pageSize)));
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') return;
      });
  }

  function renderTable(projects, totalPages) {
    var tbody = document.getElementById('project-list');
    if (!tbody) return;
    if (projects.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="text-center py-12 text-gray-400">暂无项目</td></tr>';
      var p = document.getElementById('pagination');
      if (p) p.innerHTML = '';
      return;
    }

    var html = '';
    for (var i = 0; i < projects.length; i++) {
      var p = projects[i];
      html += '<tr class="border-b border-gray-50 hover:bg-gray-50 cursor-pointer" data-id="' + p.id + '">'
        + '<td class="px-4 py-3 font-medium text-gray-800">' + window.App.utils.escapeHtml(p.name) + '</td>'
        + '<td class="px-4 py-3 text-gray-500 hidden md:table-cell">' + window.App.utils.escapeHtml(p.description || '-') + '</td>'
        + '<td class="px-4 py-3 text-center text-gray-500">' + (p.case_count || 0) + '</td>'
        + '<td class="px-4 py-3 text-center"><span class="inline-block w-2 h-2 rounded-full bg-green-400"></span></td>'
        + '</tr>';
    }
    tbody.innerHTML = html;

    // Bind row clicks
    var rows = tbody.querySelectorAll('tr[data-id]');
    for (var j = 0; j < rows.length; j++) {
      rows[j].addEventListener('click', function () {
        window.App.router.navigate('/projects/' + this.getAttribute('data-id'));
      });
    }

    // Pagination
    var pagiHtml = '';
    if (state.currentPage > 1) {
      pagiHtml += '<button class="px-3 py-1 text-sm border rounded hover:bg-gray-100" data-page="' + (state.currentPage - 1) + '">上一页</button>';
    }
    pagiHtml += '<span class="px-3 py-1 text-sm text-gray-500">第 ' + state.currentPage + ' 页</span>';
    if (projects.length >= state.pageSize) {
      pagiHtml += '<button class="px-3 py-1 text-sm border rounded hover:bg-gray-100" data-page="' + (state.currentPage + 1) + '">下一页</button>';
    }
    var pagiEl = document.getElementById('pagination');
    if (pagiEl) {
      pagiEl.innerHTML = pagiHtml;
      var pagiBtns = pagiEl.querySelectorAll('button[data-page]');
      for (var k = 0; k < pagiBtns.length; k++) {
        pagiBtns[k].addEventListener('click', function () {
          state.currentPage = parseInt(this.getAttribute('data-page'));
          loadProjects();
          window.scrollTo({ top: 0, behavior: 'smooth' });
        });
      }
    }
  }

  window.App = window.App || {};
  window.App.projects = { init: init };
})();
