import { useEffect, useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import CoveragePage from './pages/CoveragePage';
import RunDetailPage from './pages/RunDetailPage';
import api from './lib/api';

function DirectReport({ runId }) {
  const [authenticated, setAuthenticated] = useState(Boolean(localStorage.getItem('token')));
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [projectId, setProjectId] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!authenticated) return;
    api.get(`/api/runs/${runId}`)
      .then((run) => setProjectId(run.project_id))
      .catch((e) => setError(e?.detail || e.message || '加载报告失败'));
  }, [authenticated, runId]);

  const login = async (event) => {
    event.preventDefault();
    setError('');
    try {
      const data = await api.post('/api/auth/login', { username, password });
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('user', JSON.stringify(data.user));
      setAuthenticated(true);
    } catch (e) {
      setError(e?.detail || e.message || '登录失败');
    }
  };

  if (!authenticated) return (
    <form onSubmit={login} className="max-w-sm mx-auto mt-24 p-6 bg-surface-raised border border-border rounded-xl space-y-4">
      <h1 className="text-xl font-bold text-gray-100">登录查看报告</h1>
      <input aria-label="用户名" value={username} onChange={(e) => setUsername(e.target.value)} className="w-full p-2 rounded bg-surface border border-border" />
      <input aria-label="密码" type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full p-2 rounded bg-surface border border-border" />
      {error && <p className="text-sm text-red-400">{error}</p>}
      <button className="w-full p-2 rounded bg-accent-blue text-white">登录</button>
    </form>
  );

  if (error) return <div className="p-8 text-red-400">{error}</div>;
  if (!projectId) return <div className="p-8 text-gray-400">正在加载报告…</div>;
  return <Navigate to={`/projects/${projectId}/runs/${runId}`} replace />;
}

export default function App() {
  const directReport = !window.location.hash && window.location.pathname.match(/^\/report\/(\d+)\/?$/);
  if (directReport) return <DirectReport runId={directReport[1]} />;

  return (
    <div className="min-h-screen bg-surface">
      <Routes>
        <Route path="/projects/:projectId/coverage" element={<CoveragePage />} />
        <Route path="/projects/:projectId/runs/:runId" element={<RunDetailPage />} />
        <Route path="*" element={<Navigate to="/projects/1/coverage" replace />} />
      </Routes>
    </div>
  );
}
