/* global window.App */
(function () {
  'use strict';

  var auth = {};

  auth.login = function (username, password) {
    return window.App.api.post('/api/auth/login', { username: username, password: password })
      .then(function (data) {
        localStorage.setItem('token', data.access_token);
        return auth.getUser().then(function () {
          window.App.router.navigate('/projects');
          window.App.utils.showToast('登录成功', 'success');
        });
      })
      .catch(function (err) {
        var msg = err.detail || '登录失败';
        window.App.utils.showToast(msg, 'error');
        throw err;
      });
  };

  auth.register = function (username, password) {
    return window.App.api.post('/api/auth/register', { username: username, password: password })
      .then(function () {
        return auth.login(username, password);
      })
      .catch(function (err) {
        var msg = err.detail || '注册失败';
        window.App.utils.showToast(msg, 'error');
        throw err;
      });
  };

  auth.guestLogin = function () {
    return window.App.api.post('/api/auth/guest-token', {})
      .then(function (data) {
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('guest', 'true');
        window.App.router.navigate('/projects');
        window.App.utils.showToast('已进入访客模式', 'success');
      })
      .catch(function (err) {
        var msg = err.detail || '访客登录失败';
        window.App.utils.showToast(msg, 'error');
        throw err;
      });
  };

  auth.isGuest = function () {
    return localStorage.getItem('guest') === 'true';
  };

  auth.logout = function () {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('guest');
    document.getElementById('nav').classList.add('hidden');
    window.App.router.navigate('/login');
  };

  auth.isLoggedIn = function () {
    return !!localStorage.getItem('token');
  };

  auth.getToken = function () {
    return localStorage.getItem('token');
  };

  auth.getUser = function () {
    return window.App.api.get('/api/auth/me')
      .then(function (user) {
        localStorage.setItem('user', JSON.stringify(user));
        var infoEl = document.getElementById('user-info');
        if (infoEl) infoEl.textContent = user.username;
        return user;
      })
      .catch(function () {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        return null;
      });
  };

  auth.initNav = function () {
    // Guest mode
    if (auth.isGuest()) {
      document.getElementById('user-info').textContent = '访客模式';
      var adminLink = document.getElementById('admin-link');
      if (adminLink) adminLink.classList.add('hidden');
      var apiKeysLink = document.getElementById('nav-api-keys');
      if (apiKeysLink) apiKeysLink.classList.add('hidden');
      var profileLink = document.getElementById('nav-profile');
      if (profileLink) profileLink.classList.add('hidden');
      var tokenStatsLink = document.getElementById('nav-token-stats');
      if (tokenStatsLink) tokenStatsLink.classList.add('hidden');
      var logoutBtn = document.getElementById('nav-logout');
      if (logoutBtn) logoutBtn.classList.add('hidden');
      // Show login button
      var loginLink = document.getElementById('nav-login');
      if (loginLink) loginLink.classList.remove('hidden');
      return;
    }
    var userData = localStorage.getItem('user');
    if (userData) {
      try {
        var u = JSON.parse(userData);
        document.getElementById('user-info').textContent = u.username;
        var adminLink = document.getElementById('admin-link');
        if (adminLink) {
          if (u.role === 'admin') {
            adminLink.classList.remove('hidden');
          } else {
            adminLink.classList.add('hidden');
          }
        }
      } catch (e) { /* ignore */ }
    }
  };

  window.App = window.App || {};
  window.App.auth = auth;
})();
