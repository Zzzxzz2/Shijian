/* global window.App */
(function () {
  'use strict';

  var BASE = window.location.origin;

  function getToken() {
    return localStorage.getItem('token');
  }

  function request(method, path, data, opts) {
    opts = opts || {};
    if (opts.showLoading !== false) {
      window.App.utils.showLoading();
    }

    var headers = { 'Content-Type': 'application/json' };
    var token = getToken();
    if (token) {
      headers['Authorization'] = 'Bearer ' + token;
    }

    var fetchOpts = {
      method: method,
      headers: headers,
    };
    if (data) {
      fetchOpts.body = JSON.stringify(data);
    }
    if (opts.signal) {
      fetchOpts.signal = opts.signal;
    }

    return fetch(BASE + path, fetchOpts)
      .then(function (resp) {
        if (resp.status === 401) {
          localStorage.removeItem('token');
          localStorage.removeItem('user');
          window.App.router.navigate('/login');
          return Promise.reject(new Error('未登录或登录已过期'));
        }
        // 204 No Content — no body to parse
        if (resp.status === 204) {
          return null;
        }
        return resp.json().then(function (json) {
          if (!resp.ok) {
            var detail = json.detail || (json.detail && json.detail[0] && json.detail[0].msg) || '请求失败';
            return Promise.reject({ status: resp.status, detail: detail, body: json });
          }
          return json;
        });
      })
      .catch(function (err) {
        if (err && err.status) {
          window.App.utils.showToast(err.detail || '请求失败', 'error');
          throw err;
        }
        if (err.name === 'AbortError') throw err;
        window.App.utils.showToast('网络错误或请求失败', 'error');
        throw err;
      })
      .finally(function () {
        if (opts.showLoading !== false) {
          window.App.utils.hideLoading();
        }
      });
  }

  var api = {};
  api.get = function (path, opts) { return request('GET', path, null, opts); };
  api.post = function (path, data, opts) { return request('POST', path, data, opts); };
  api.patch = function (path, data, opts) { return request('PATCH', path, data, opts); };
  api.put = function (path, data, opts) { return request('PUT', path, data, opts); };
  api.del = function (path, data, opts) { return request('DELETE', path, data, opts); };

  window.App = window.App || {};
  window.App.api = api;
})();
