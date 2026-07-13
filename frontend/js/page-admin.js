/* global window.App */
(function () {
  'use strict';

  var page = {};

  page.init = function () {
    if (window.App.auth.isGuest()) {
      document.getElementById('app').innerHTML = '<div class="text-center py-20 text-gray-400">访客模式下无法访问管理面板</div>';
      return;
    }
    var userData = localStorage.getItem('user');
    var user = userData ? JSON.parse(userData) : null;
    if (!user || user.role !== 'admin') {
      document.getElementById('app').innerHTML =
        '<div class="text-center py-20 text-gray-400">\u65e0\u6743\u8bbf\u95ee\uff0c\u4ec5 admin \u53ef\u67e5\u770b\u7ba1\u7406\u9762\u677f</div>';
      return;
    }
    page.loadStats();
    page.loadUsers();
    page.bindEvents();
  };

  page.bindEvents = function () {
    document.getElementById('user-list').addEventListener('click', function (e) {
      var btn = e.target.closest('.toggle-role');
      if (btn) {
        page.updateRole(btn.getAttribute('data-id'), btn.getAttribute('data-role'));
        return;
      }
      var delBtn = e.target.closest('.delete-user');
      if (delBtn) {
        page.confirmDelete(delBtn.getAttribute('data-id'), delBtn.getAttribute('data-name'));
        return;
      }
      var resetBtn = e.target.closest('.reset-pwd');
      if (resetBtn) {
        page.promptResetPassword(resetBtn.getAttribute('data-id'), resetBtn.getAttribute('data-name'));
        return;
      }
    });
  };

  page.loadStats = function () {
    window.App.api.get('/api/admin/stats')
      .then(function (data) {
        document.getElementById('stat-users').textContent = data.users || 0;
        document.getElementById('stat-projects').textContent = data.projects || 0;
        document.getElementById('stat-runs').textContent = data.test_runs || 0;
      })
      .catch(function (err) {
        console.error('Load stats error:', err);
      });
  };

  page.loadUsers = function () {
    window.App.api.get('/api/admin/users')
      .then(function (data) {
        var users = Array.isArray(data) ? data : (data.items || []);
        page.renderUsers(users);
      })
      .catch(function (err) {
        console.error('Load users error:', err);
      });
  };

  page.renderUsers = function (users) {
    var tbody = document.getElementById('user-list');
    var currentUserId = window.App.auth.getUser() ? window.App.auth.getUser().id : -1;
    if (users.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-center py-12 text-gray-400">\u6682\u65e0\u7528\u6237</td></tr>';
      return;
    }

    var html = '';
    for (var i = 0; i < users.length; i++) {
      var u = users[i];
      var roleBadge = u.role === 'admin'
        ? '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700">admin</span>'
        : '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">user</span>';
      var toggleRole = u.role === 'admin' ? 'user' : 'admin';
      var toggleLabel = u.role === 'admin' ? '\u964d\u4e3a user' : '\u5347\u4e3a admin';

      var actions = '<button class="toggle-role text-xs text-primary-600 hover:text-primary-800 font-medium mr-3" data-id="' + u.id + '" data-role="' + toggleRole + '">' + toggleLabel + '</button>';
      actions += '<button class="reset-pwd text-xs text-blue-600 hover:text-blue-800 font-medium mr-3" data-id="' + u.id + '" data-name="' + window.App.utils.escapeHtml(u.username) + '">\u91cd\u7f6e\u5bc6\u7801</button>';
      if (u.id !== currentUserId) {
        actions += '<button class="delete-user text-xs text-red-600 hover:text-red-800 font-medium" data-id="' + u.id + '" data-name="' + window.App.utils.escapeHtml(u.username) + '">\u5220\u9664</button>';
      }

      html += '<tr class="border-b border-gray-50">'
        + '<td class="px-4 py-3 font-medium text-gray-800">' + window.App.utils.escapeHtml(u.username) + '</td>'
        + '<td class="px-4 py-3">' + roleBadge + '</td>'
        + '<td class="px-4 py-3 text-gray-500 hidden md:table-cell">' + window.App.utils.formatDate(u.created_at) + '</td>'
        + '<td class="px-4 py-3 text-center">' + actions + '</td></tr>';
    }
    tbody.innerHTML = html;
  };

  page.updateRole = function (userId, newRole) {
    window.App.api.put('/api/admin/users/' + userId + '/role', { role: newRole })
      .then(function () {
        window.App.utils.showToast('\u89d2\u8272\u5df2\u66f4\u65b0', 'success');
        page.loadUsers();
      })
      .catch(function (err) {
        window.App.utils.showToast(err.detail || '\u66f4\u65b0\u5931\u8d25', 'error');
      });
  };

  page.confirmDelete = function (userId, username) {
    if (!confirm('\u786e\u8ba4\u5220\u9664\u7528\u6237 ' + username + ' \uff1f\n\u8be5\u7528\u6237\u7684\u9879\u76ee\u5c06\u8f6c\u79fb\u7ed9\u5f53\u524d\u7ba1\u7406\u5458\u3002')) return;
    window.App.api.del('/api/admin/users/' + userId)
      .then(function () {
        window.App.utils.showToast('\u7528\u6237\u5df2\u5220\u9664', 'success');
        page.loadUsers();
      })
      .catch(function (err) {
        window.App.utils.showToast(err.detail || '\u5220\u9664\u5931\u8d25', 'error');
      });
  };

  page.promptResetPassword = function (userId, username) {
    var newPwd = prompt('\u8bf7\u8f93\u5165 ' + username + ' \u7684\u65b0\u5bc6\u7801\uff086\u4f4d\u4ee5\u4e0a\uff09\uff1a');
    if (!newPwd || newPwd.length < 6) {
      if (newPwd !== null) window.App.utils.showToast('\u5bc6\u7801\u957f\u5ea6\u4e0d\u80fd\u5c11\u4e8e 6 \u4f4d', 'error');
      return;
    }
    window.App.api.put('/api/admin/users/' + userId + '/reset-password', { new_password: newPwd })
      .then(function () {
        window.App.utils.showToast(username + ' \u5bc6\u7801\u5df2\u91cd\u7f6e', 'success');
      })
      .catch(function (err) {
        window.App.utils.showToast(err.detail || '\u91cd\u7f6e\u5931\u8d25', 'error');
      });
  };

  window.App = window.App || {};
  window.App.admin = page;
})();
