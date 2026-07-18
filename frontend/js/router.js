/* global window.App */
(function () {
  'use strict';

  var routes = {
    '/login':               { page: '/pages/login.html',          title: '登录',           auth: false },
    '/projects':            { page: '/pages/projects.html',       title: '项目列表',       auth: true  },
    '/projects/:id':        { page: '/pages/project-detail.html',  title: '项目详情',       auth: true  },
    '/api-keys':            { page: '/pages/api-keys.html',       title: 'API Key 管理',   auth: true  },
    '/admin':               { page: '/pages/admin.html',           title: '管理面板',       auth: true  },
    '/projects/:id/ai-plan':  { page: '/pages/ai-plan.html',      title: 'AI 生成',       auth: true  },
    '/runs/:id':              { page: '/pages/run-detail.html',    title: '执行详情',       auth: true  },
    '/token-stats':           { page: '/pages/token-stats.html',   title: 'Token 统计',    auth: true  },
    '/profile':               { page: '/pages/profile.html',        title: '个人中心',       auth: true  },
    '/analytics':             { page: '/pages/analytics.html',       title: '浏览统计',       auth: false },
  };

  function matchRoute(hash) {
    // exact match first
    if (routes[hash]) return { route: routes[hash], params: {} };
    // param match
    for (var key in routes) {
      if (!routes.hasOwnProperty(key)) continue;
      var parts = key.split('/');
      var hashParts = hash.split('/');
      if (parts.length !== hashParts.length) continue;
      var match = true;
      var params = {};
      for (var i = 0; i < parts.length; i++) {
        if (parts[i].startsWith(':')) {
          params[parts[i].slice(1)] = hashParts[i];
        } else if (parts[i] !== hashParts[i]) {
          match = false;
          break;
        }
      }
      if (match) return { route: routes[key], params: params };
    }
    return null;
  }

  var router = {};

  router.navigate = function (hash) {
    if (!hash.startsWith('/')) hash = '/' + hash;
    window.location.hash = '#' + hash;
  };

  router.init = function () {
    var hash = window.location.hash.replace(/^#/, '') || '/login';
    if (hash === '/' || hash === '') hash = '/login';
    window.location.hash = '#' + hash;
    // Will trigger hashchange
  };

  function handleRoute() {
    var rawHash = window.location.hash.replace(/^#/, '') || '/login';
    if (rawHash === '/' || rawHash === '') rawHash = '/login';

    var match = matchRoute(rawHash);
    if (!match) {
      // unknown route -> redirect
      router.navigate('/projects');
      return;
    }

    var route = match.route;

    // Analytics page init hook (runs before nav guard for the special case)
    if (rawHash === '/analytics') {
      // Re-fetch analytics data each time you visit
    }

    // Auth guard
    if (route.auth && !window.App.auth.isLoggedIn()) {
      router.navigate('/login');
      return;
    }
    if (!route.auth && window.App.auth.isLoggedIn() && rawHash === '/login') {
      router.navigate('/projects');
      return;
    }

    // Show nav for authed pages
    var nav = document.getElementById('nav');
    if (route.auth) {
      nav.classList.remove('hidden');
      window.App.auth.initNav();
    } else {
      nav.classList.add('hidden');
    }

    // Track navigation via analytics
    if (window.__analytics__ && typeof window.__analytics__.nav === 'function') {
      window.__analytics__.nav(window.location.pathname + rawHash);
    }

    // Fetch page content
    window.App.utils.showLoading();
    fetch(route.page)
      .then(function (resp) {
        if (!resp.ok) throw new Error('Page not found');
        return resp.text();
      })
      .then(function (html) {
        document.getElementById('app').innerHTML = html;
        document.title = route.title + ' - 试剑 V3';

        // Call page init if exists — use route page file, not raw hash (handles /projects/:id)
        var pageFile = route.page.split('/').pop().replace('.html', '');
        var pageMap = {
          'login': 'login',
          'projects': 'projects',
          'project-detail': 'projectDetail',
          'api-keys': 'apiKeys',
          'admin': 'admin',
          'ai-plan': 'aiPlan',
          'run-detail': 'runDetail',
          'token-stats': 'tokenStats',
          'profile': 'profile',
        };
        var initFn = window.App[pageMap[pageFile]];
        if (initFn && typeof initFn.init === 'function') {
          initFn.init(match.params);
        }
      })
      .catch(function (err) {
        console.error('Router catch:', err && err.message ? err.message : err);
        if (err && err.stack) console.error('Router stack:', err.stack);
        document.getElementById('app').innerHTML = '<div class="text-center py-20 text-gray-400">\u9875\u9762\u52a0\u8f7d\u5931\u8d25</div>';
      })
      .finally(function () {
        window.App.utils.hideLoading();
      });
  }

  window.addEventListener('hashchange', handleRoute);

  // Boot
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      handleRoute();
    });
  } else {
    handleRoute();
  }

  window.App = window.App || {};
  window.App.router = router;
})();
