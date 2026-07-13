/* global window.App */
(function () {
  'use strict';

  function init() {
    // Toggle login/register
    var gotoRegister = document.getElementById('goto-register');
    var gotoLogin = document.getElementById('goto-login');
    if (gotoRegister) gotoRegister.addEventListener('click', function (e) {
      e.preventDefault();
      document.getElementById('login-form').classList.add('hidden');
      document.getElementById('register-form').classList.remove('hidden');
    });
    if (gotoLogin) gotoLogin.addEventListener('click', function (e) {
      e.preventDefault();
      document.getElementById('register-form').classList.add('hidden');
      document.getElementById('login-form').classList.remove('hidden');
    });

    // Login
    var loginBtn = document.getElementById('login-btn');
    if (loginBtn) loginBtn.addEventListener('click', function () {
      var username = document.getElementById('login-username').value.trim();
      var password = document.getElementById('login-password').value;
      if (!username || !password) {
        window.App.utils.showToast('请填写用户名和密码', 'error');
        return;
      }
      this.disabled = true;
      this.textContent = '登录中...';
      window.App.auth.login(username, password)
        .catch(function () {})
        .finally(function () {
          loginBtn.disabled = false;
          loginBtn.textContent = '登录';
        });
    });

    // Register
    var registerBtn = document.getElementById('register-btn');
    if (registerBtn) registerBtn.addEventListener('click', function () {
      var username = document.getElementById('reg-username').value.trim();
      var password = document.getElementById('reg-password').value;
      var confirm = document.getElementById('reg-confirm').value;
      if (!username || !password || !confirm) {
        window.App.utils.showToast('请填写所有字段', 'error');
        return;
      }
      if (password !== confirm) {
        window.App.utils.showToast('两次密码输入不一致', 'error');
        return;
      }
      this.disabled = true;
      this.textContent = '注册中...';
      window.App.auth.register(username, password)
        .catch(function () {})
        .finally(function () {
          registerBtn.disabled = false;
          registerBtn.textContent = '注册';
        });
    });

    // Guest button
    var guestBtn = document.getElementById('guest-btn');
    if (guestBtn) guestBtn.addEventListener('click', function () {
      this.disabled = true;
      this.textContent = '进入中...';
      window.App.auth.guestLogin()
        .catch(function () {})
        .finally(function () {
          guestBtn.disabled = false;
          guestBtn.textContent = '访客查看';
        });
    });

    // Enter key support
    var loginPw = document.getElementById('login-password');
    if (loginPw) loginPw.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') document.getElementById('login-btn').click();
    });
    var regConfirm = document.getElementById('reg-confirm');
    if (regConfirm) regConfirm.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') document.getElementById('register-btn').click();
    });
  }

  window.App = window.App || {};
  window.App.login = { init: init };
})();
