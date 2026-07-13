/* global window.App */
(function () {
  'use strict';

  var page = {};

  page.init = function () {
    if (window.App.auth.isGuest()) {
      var btn = document.getElementById('add-key-btn');
      if (btn) btn.classList.add('hidden');
    }
    page.loadKeys();
    page.bindEvents();
  };

  var providerDefaults = {
    deepseek: { base_url: 'https://api.deepseek.com', model: 'deepseek-chat' },
    openai: { base_url: 'https://api.openai.com', model: 'gpt-4o' },
    anthropic: { base_url: 'https://api.anthropic.com', model: 'claude-sonnet-4-20250514' },
    mimo: { base_url: 'https://token-plan-cn.xiaomimimo.com/v1', model: 'mimo-v2.5-pro' },
    glm: { base_url: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-plus' },
    qwen: { base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-max' },
    kimi: { base_url: 'https://api.moonshot.cn', model: 'moonshot-v1-8k' },
  };

  page.resetModal = function () {
    document.getElementById('ak-edit-id').value = '';
    document.getElementById('ak-key').value = '';
    document.getElementById('ak-key').disabled = false;
    document.getElementById('ak-key').style.display = 'block';
    document.getElementById('ak-key').previousElementSibling.textContent = 'API Key *';
    document.getElementById('add-key-modal').querySelector('h3').textContent = '添加 API Key';
    var pv = document.getElementById('ak-provider').value || 'deepseek';
    var def = providerDefaults[pv] || {};
    document.getElementById('ak-base-url').value = def.base_url || '';
    document.getElementById('ak-model').value = def.model || '';
  };

  page.bindEvents = function () {
    document.getElementById('add-key-btn').addEventListener('click', function () {
      page.resetModal();
      document.getElementById('ak-provider').value = 'deepseek';
      document.getElementById('add-key-modal').classList.remove('hidden');
    });

    document.getElementById('ak-cancel').addEventListener('click', function () {
      document.getElementById('add-key-modal').classList.add('hidden');
    });

    document.getElementById('ak-save').addEventListener('click', function () {
      var editId = document.getElementById('ak-edit-id').value;
      if (editId) {
        page.updateKey(editId);
      } else {
        page.createKey();
      }
    });

    document.getElementById('add-key-modal').addEventListener('click', function (e) {
      if (e.target === this) this.classList.add('hidden');
    });

    // Provider change → update default base_url and model
    document.getElementById('ak-provider').addEventListener('change', function () {
      var def = providerDefaults[this.value] || {};
      document.getElementById('ak-base-url').value = def.base_url || '';
      document.getElementById('ak-model').value = def.model || '';
    });
  };

  page.loadKeys = function () {
    window.App.api.get('/api/api-keys')
      .then(function (data) {
        var keys = Array.isArray(data) ? data : (data.items || []);
        page.renderKeys(keys);
      })
      .catch(function (err) {
        console.error('Load keys error:', err);
      });
  };

  page.renderKeys = function (keys) {
    var tbody = document.getElementById('api-key-list');
    if (keys.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="text-center py-12 text-gray-400">暂无 API Key</td></tr>';
      return;
    }

    var html = '';
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      var statusDot = k.is_valid
        ? '<span class="inline-block w-2 h-2 rounded-full bg-green-500"></span>'
        : '<span class="inline-block w-2 h-2 rounded-full bg-red-500"></span>';
      var tested = k.last_tested_at
        ? window.App.utils.formatDate(k.last_tested_at)
        : '-';
      var model = k.model || '-';

      html += '<tr class="border-b border-gray-50">'
        + '<td class="px-4 py-3 font-medium text-gray-800 capitalize">' + window.App.utils.escapeHtml(k.provider) + '</td>'
        + '<td class="px-4 py-3 text-gray-700 font-mono text-xs">' + window.App.utils.escapeHtml(model) + '</td>'
        + '<td class="px-4 py-3 text-gray-600 font-mono text-xs">' + window.App.utils.escapeHtml(k.api_key_masked) + '</td>'
        + '<td class="px-4 py-3 text-gray-500 text-xs hidden md:table-cell truncate max-w-[200px]">' + window.App.utils.escapeHtml(k.base_url || '-') + '</td>'
        + '<td class="px-4 py-3 text-center">' + statusDot + '</td>'
        + '<td class="px-4 py-3 text-gray-500 text-xs hidden md:table-cell">' + tested + '</td>'
        + '<td class="px-4 py-3 text-center">'
        +   '<div class="flex items-center justify-center gap-2">'
        +     '<button class="test-key text-xs text-primary-600 hover:text-primary-800 font-medium" data-id="' + k.id + '">测试</button>'
        +     '<button class="edit-key text-xs text-amber-600 hover:text-amber-800 font-medium" data-id="' + k.id + '">编辑</button>'
        +     '<button class="delete-key text-xs text-red-500 hover:text-red-700 font-medium" data-id="' + k.id + '">删除</button>'
        +   '</div>'
        + '</td></tr>';
    }
    tbody.innerHTML = html;

    // Bind test buttons
    var testBtns = tbody.querySelectorAll('.test-key');
    for (var j = 0; j < testBtns.length; j++) {
      testBtns[j].addEventListener('click', function () {
        var id = this.getAttribute('data-id');
        page.testKey(id);
      });
    }

    // Bind edit buttons
    var editBtns = tbody.querySelectorAll('.edit-key');
    for (var j = 0; j < editBtns.length; j++) {
      editBtns[j].addEventListener('click', function () {
        var id = parseInt(this.getAttribute('data-id'));
        page.editKey(id);
      });
    }

    // Bind delete buttons
    var delBtns = tbody.querySelectorAll('.delete-key');
    for (var j = 0; j < delBtns.length; j++) {
      delBtns[j].addEventListener('click', function () {
        var id = this.getAttribute('data-id');
        if (!confirm('\u786e\u5b9a\u5220\u9664\u8be5 API Key\uff1f')) return;
        page.deleteKey(id);
      });
    }
  };

  page.createKey = function () {
    var provider = document.getElementById('ak-provider').value;
    var apiKey = document.getElementById('ak-key').value.trim();
    var baseUrl = document.getElementById('ak-base-url').value.trim();
    var model = document.getElementById('ak-model').value.trim();

    if (!apiKey) {
      window.App.utils.showToast('\u8bf7\u8f93\u5165 API Key', 'error');
      return;
    }

    window.App.api.post('/api/api-keys', {
      provider: provider,
      api_key: apiKey,
      base_url: baseUrl || undefined,
      model: model || undefined,
    })
      .then(function () {
        window.App.utils.showToast('\u6dfb\u52a0\u6210\u529f', 'success');
        document.getElementById('add-key-modal').classList.add('hidden');
        page.loadKeys();
      })
      .catch(function (err) {
        window.App.utils.showToast(err.detail || '\u6dfb\u52a0\u5931\u8d25', 'error');
      });
  };

  page.editKey = function (id) {
    // Find key data from rendered list
    window.App.api.get('/api/api-keys')
      .then(function (data) {
        var keys = Array.isArray(data) ? data : (data.items || []);
        var key = null;
        for (var i = 0; i < keys.length; i++) {
          if (keys[i].id === id) { key = keys[i]; break; }
        }
        if (!key) {
          window.App.utils.showToast('Key not found', 'error');
          return;
        }

        // Populate modal
        document.getElementById('ak-edit-id').value = key.id;
        document.getElementById('ak-provider').value = key.provider;
        document.getElementById('ak-key').value = '';
        document.getElementById('ak-key').disabled = true;
        document.getElementById('ak-key').style.display = 'none';
        document.getElementById('ak-key').previousElementSibling.textContent = 'API Key (留空不修改)';
        document.getElementById('ak-base-url').value = key.base_url || '';
        document.getElementById('ak-model').value = key.model || '';
        document.getElementById('add-key-modal').querySelector('h3').textContent = '\u7f16\u8f91 API Key';
        document.getElementById('add-key-modal').classList.remove('hidden');
      })
      .catch(function (err) {
        window.App.utils.showToast(err.detail || '\u52a0\u8f7d\u5931\u8d25', 'error');
      });
  };

  page.updateKey = function (id) {
    var provider = document.getElementById('ak-provider').value;
    var baseUrl = document.getElementById('ak-base-url').value.trim();
    var model = document.getElementById('ak-model').value.trim();

    window.App.api.patch('/api/api-keys/' + id, {
      provider: provider,
      base_url: baseUrl || undefined,
      model: model || undefined,
    })
      .then(function () {
        window.App.utils.showToast('\u66f4\u65b0\u6210\u529f', 'success');
        document.getElementById('add-key-modal').classList.add('hidden');
        page.loadKeys();
      })
      .catch(function (err) {
        window.App.utils.showToast(err.detail || '\u66f4\u65b0\u5931\u8d25', 'error');
      });
  };

  page.deleteKey = function (id) {
    window.App.api.del('/api/api-keys/' + id)
      .then(function () {
        window.App.utils.showToast('\u5df2\u5220\u9664', 'success');
        page.loadKeys();
      })
      .catch(function (err) {
        window.App.utils.showToast(err.detail || '\u5220\u9664\u5931\u8d25', 'error');
      });
  };

  page.testKey = function (id) {
    window.App.api.post('/api/api-keys/' + id + '/test', {})
      .then(function (data) {
        var msg = (data && data.message) || '\u6d4b\u8bd5\u6210\u529f';
        window.App.utils.showToast(msg, 'success');
        page.loadKeys();
      })
      .catch(function (err) {
        window.App.utils.showToast(err.detail || '\u6d4b\u8bd5\u5931\u8d25', 'error');
        page.loadKeys();
      });
  };

  window.App = window.App || {};
  window.App.apiKeys = page;
})();
