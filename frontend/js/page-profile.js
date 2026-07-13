/* global window.App */
(function () {
  'use strict';

  var page = {};

  page.init = function () {
    if (window.App.auth.isGuest()) {
      document.getElementById('app').innerHTML = '<div class="text-center py-20 text-gray-400">访客模式下无法查看个人中心</div>';
      return;
    }
    page.loadInfo();
    page.bindEvents();
  };

  page.loadInfo = function () {
    window.App.api.get('/api/auth/me')
      .then(function (u) {
        document.getElementById('profile-username').textContent = u.username;
        var roleBadge = u.role === 'admin'
          ? '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700">admin</span>'
          : '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">user</span>';
        document.getElementById('profile-role').innerHTML = roleBadge;
        document.getElementById('profile-created').textContent = window.App.utils.formatDate(u.created_at);
      })
      .catch(function (err) {
        window.App.utils.showToast('\u52a0\u8f7d\u5931\u8d25', 'error');
      });
  };

  page.bindEvents = function () {
    document.getElementById('change-pwd-form').addEventListener('submit', function (e) {
      e.preventDefault();
      var oldPwd = document.getElementById('old-password').value;
      var newPwd = document.getElementById('new-password').value;
      var confirmPwd = document.getElementById('confirm-password').value;

      if (newPwd !== confirmPwd) {
        window.App.utils.showToast('\u4e24\u6b21\u8f93\u5165\u7684\u65b0\u5bc6\u7801\u4e0d\u4e00\u81f4', 'error');
        return;
      }
      if (newPwd.length < 6) {
        window.App.utils.showToast('\u65b0\u5bc6\u7801\u957f\u5ea6\u4e0d\u80fd\u5c11\u4e8e 6 \u4f4d', 'error');
        return;
      }

      window.App.api.put('/api/auth/change-password', {
        old_password: oldPwd,
        new_password: newPwd
      })
        .then(function () {
          window.App.utils.showToast('\u5bc6\u7801\u5df2\u4fee\u6539\uff0c\u8bf7\u91cd\u65b0\u767b\u5f55', 'success');
          document.getElementById('old-password').value = '';
          document.getElementById('new-password').value = '';
          document.getElementById('confirm-password').value = '';
          setTimeout(function () {
            window.App.auth.logout();
          }, 1500);
        })
        .catch(function (err) {
          window.App.utils.showToast(err.detail || '\u4fee\u6539\u5931\u8d25', 'error');
        });
    });
  };

  window.App = window.App || {};
  window.App.profile = page;
})();
