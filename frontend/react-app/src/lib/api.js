/**
 * HTTP client with JWT injection, loading state, 401 redirect.
 *
 * Usage:
 *   import api from '../lib/api';
 *   const data = await api.get('/api/projects/1/coverage');
 *   const result = await api.post('/api/runs', body, { skipLoading: true });
 */

const BASE = window.location.origin;

function getToken() {
  return localStorage.getItem('token');
}

function request(method, path, data, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const fetchOpts = {
    method,
    headers,
    signal: opts.signal || controller.signal,
  };
  if (data) {
    fetchOpts.body = JSON.stringify(data);
  }

  return fetch(BASE + path, fetchOpts)
    .then((resp) => {
      if (resp.status === 401) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        // Redirect to V2 login
        window.location.hash = '#/login';
        return Promise.reject(new Error('未登录或登录已过期'));
      }
      if (resp.status === 204) return null;
      return resp.json().then((json) => {
        if (!resp.ok) {
          const detail = json.detail || (json.detail?.[0]?.msg) || '请求失败';
          return Promise.reject({ status: resp.status, detail, body: json });
        }
        return json;
      });
    })
    .catch((err) => {
      if (err?.status) throw err;
      if (err.name === 'AbortError') throw err;
      throw new Error('网络错误或请求失败');
    });
}

const api = {
  get: (path, opts) => request('GET', path, null, opts),
  post: (path, data, opts) => request('POST', path, data, opts),
  patch: (path, data, opts) => request('PATCH', path, data, opts),
  put: (path, data, opts) => request('PUT', path, data, opts),
  del: (path, data, opts) => request('DELETE', path, data, opts),
};

export default api;
