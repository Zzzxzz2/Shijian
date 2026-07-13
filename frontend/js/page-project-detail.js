/* global window.App */
(function () {
  'use strict';

  var page = {
    projectId: null,
    currentTab: 'cases',
    selectedCases: {},
    projectData: null,
  };

  page.init = function (params) {
    if (window.App.auth.isGuest()) {
      // Hide all action buttons
      ['new-case-btn', 'execute-cases-btn', 'batch-delete-cases-btn', 'export-cases-btn', 'import-cases-btn',
       'edit-project-btn', 'delete-project-btn', 'upload-doc-btn', 'ai-plan-btn',
       'new-schedule-btn', 'execute-by-tag-btn', 'select-all-cases'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.classList.add('hidden');
      });
    }
    page.projectId = params.id;
    page.currentTab = 'cases';
    page.selectedCases = {};
    page.projectData = null;
    document.getElementById('project-title').textContent = '\u9879\u76ee\u8be6\u60c5';
    page.switchTab('cases');
    page.bindTabButtons();
    page.bindAuthConfigEvents();
    page.loadProjectInfo();
    // Wire up AI plan button
    var aiBtn = document.getElementById('ai-plan-btn');
    if (aiBtn) {
      aiBtn.setAttribute('href', '#/projects/' + page.projectId + '/ai-plan');
      aiBtn.classList.remove('hidden');
    }
  };

  page.loadProjectInfo = function () {
    window.App.api.get('/api/projects/' + page.projectId)
      .then(function (data) {
        page.projectData = data;
        var el = document.getElementById('project-title');
        if (el) el.textContent = data.name || '\u9879\u76ee\u8be6\u60c5';
        page.loadAuthConfigForm(data.auth_config);
      })
      .catch(function (err) {
        console.error('Load project error:', err);
      });
  };

  page.switchTab = function (tab) {
    page.currentTab = tab;
    var contents = document.querySelectorAll('.tab-content');
    for (var i = 0; i < contents.length; i++) contents[i].classList.add('hidden');
    var active = document.getElementById('tab-' + tab);
    if (active) active.classList.remove('hidden');

    var btns = document.querySelectorAll('.tab-btn');
    for (var i = 0; i < btns.length; i++) {
      var btn = btns[i];
      if (btn.getAttribute('data-tab') === tab) {
        btn.className = 'tab-btn px-5 py-2.5 text-sm font-medium transition-colors border-b-2 border-primary-600 -mb-px text-primary-600';
      } else {
        btn.className = 'tab-btn px-5 py-2.5 text-sm font-medium transition-colors text-gray-500 hover:text-gray-700';
      }
    }

    if (tab === 'cases') page.loadCases();
    else if (tab === 'runs') page.loadRuns();
    else if (tab === 'schedules') page.loadSchedules();
    else if (tab === 'docs') page.loadDocs();
  };

  page.bindTabButtons = function () {
    var btns = document.querySelectorAll('.tab-btn');
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener('click', function () { page.switchTab(this.getAttribute('data-tab')); });
    }

    // Case filter
    var filter = document.getElementById('case-filter');
    if (filter) {
      filter.addEventListener('change', function () {
        page.selectedCases = {};
        page.updateSelectionButtons();
        page.loadCases();
      });
    }

    // Select all
    var selectAll = document.getElementById('select-all-cases');
    if (selectAll) {
      selectAll.addEventListener('change', function () {
        var checked = this.checked;
        var boxes = document.querySelectorAll('#case-list .case-select');
        page.selectedCases = {};
        for (var i = 0; i < boxes.length; i++) {
          boxes[i].checked = checked;
          if (checked) page.selectedCases[boxes[i].value] = true;
        }
        page.updateSelectionButtons();
      });
    }

    // Execute button
    var execBtn = document.getElementById('execute-cases-btn');
    if (execBtn) execBtn.addEventListener('click', function () { page.executeSelectedCases(); });

    // Batch delete button
    var batchDelBtn = document.getElementById('batch-delete-cases-btn');
    if (batchDelBtn) batchDelBtn.addEventListener('click', function () { page.batchDeleteCases(); });

    // New case button → open create modal
    var newCaseBtn = document.getElementById('new-case-btn');
    if (newCaseBtn) {
      newCaseBtn.addEventListener('click', function () { page.openCaseModal(null); });
    }

    // Case modal buttons
    var cmCancel = document.getElementById('cm-cancel');
    if (cmCancel) cmCancel.addEventListener('click', function () { page.closeCaseModal(); });
    var cmConfirm = document.getElementById('cm-confirm');
    if (cmConfirm) cmConfirm.addEventListener('click', function () { page.saveCase(); });
    var cmModal = document.getElementById('case-modal');
    if (cmModal) cmModal.addEventListener('click', function (e) { if (e.target === this) page.closeCaseModal(); });

    // Add assertion button
    var addAssert = document.getElementById('cm-add-assertion');
    if (addAssert) addAssert.addEventListener('click', function () { page.addAssertionRow(); });

    // Add step button
    var addStep = document.getElementById('cm-add-step');
    if (addStep) addStep.addEventListener('click', function () { page.addStepRow(); });

    // Type change toggle
    var cmType = document.getElementById('cm-type');
    if (cmType) {
      cmType.addEventListener('change', function () {
        page.toggleCaseTypeFields(this.value);
      });
    }

    // Project edit button
    var editProjBtn = document.getElementById('edit-project-btn');
    if (editProjBtn) editProjBtn.addEventListener('click', function () { page.openProjectEditModal(); });
    var peCancel = document.getElementById('pe-cancel');
    if (peCancel) peCancel.addEventListener('click', function () { document.getElementById('project-edit-modal').classList.add('hidden'); });
    var peConfirm = document.getElementById('pe-confirm');
    if (peConfirm) peConfirm.addEventListener('click', function () { page.saveProject(); });
    var peModal = document.getElementById('project-edit-modal');
    if (peModal) peModal.addEventListener('click', function (e) { if (e.target === this) this.classList.add('hidden'); });

    // Project delete button
    var delProjBtn = document.getElementById('delete-project-btn');
    if (delProjBtn) {
      delProjBtn.addEventListener('click', function () {
        if (!confirm('\u786e\u5b9a\u5220\u9664\u6b64\u9879\u76ee\uff1f\u5c06\u540c\u65f6\u5220\u9664\u6240\u6709\u7528\u4f8b\u548c\u6267\u884c\u8bb0\u5f55')) return;
        window.App.api.del('/api/projects/' + page.projectId)
          .then(function () {
            window.App.utils.showToast('\u9879\u76ee\u5df2\u5220\u9664', 'success');
            window.App.router.navigate('/projects');
          })
          .catch(function (err) { window.App.utils.showToast(err.detail || '\u5220\u9664\u5931\u8d25', 'error'); });
      });
    }

    // Upload doc button
    var uploadBtn = document.getElementById('upload-doc-btn');
    if (uploadBtn) {
      uploadBtn.addEventListener('click', function () {
        var input = document.createElement('input');
        input.type = 'file';
        input.accept = '.pdf,.docx,.txt,.md';
        input.onchange = function () {
          var file = input.files[0];
          if (!file) return;
          var fd = new FormData();
          fd.append('file', file);
          window.App.utils.showLoading();
          fetch('/api/projects/' + page.projectId + '/docs', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + window.App.auth.getToken() },
            body: fd,
          }).then(function (r) { if (!r.ok) throw new Error('Upload failed'); return r.json(); })
            .then(function () { window.App.utils.showToast('\u6587\u6863\u4e0a\u4f20\u6210\u529f', 'success'); page.loadDocs(); })
            .catch(function () { window.App.utils.showToast('\u4e0a\u4f20\u5931\u8d25', 'error'); })
            .finally(function () { window.App.utils.hideLoading(); });
        };
        input.click();
      });
    }

    // Export cases button
    var exportBtn = document.getElementById('export-cases-btn');
    if (exportBtn) {
      exportBtn.addEventListener('click', function () { page.exportCases(); });
    }

    // Import cases button
    var importBtn = document.getElementById('import-cases-btn');
    if (importBtn) {
      importBtn.addEventListener('click', function () { page.importCases(); });
    }

    // Tag filter
    var tagFilter = document.getElementById('tag-filter');
    if (tagFilter) {
      tagFilter.addEventListener('change', function () {
        page.selectedCases = {};
        page.updateSelectionButtons();
        page.loadCases();
        var execByTag = document.getElementById('execute-by-tag-btn');
        if (execByTag) execByTag.disabled = !this.value;
      });
    }

    // Execute by tag
    var execByTagBtn = document.getElementById('execute-by-tag-btn');
    if (execByTagBtn) {
      execByTagBtn.addEventListener('click', function () { page.executeByTag(); });
    }

    // Schedule modal buttons
    var newSchBtn = document.getElementById('new-schedule-btn');
    if (newSchBtn) newSchBtn.addEventListener('click', function () { page.openScheduleModal(null); });
    var smCancel = document.getElementById('sm-cancel');
    if (smCancel) smCancel.addEventListener('click', function () { document.getElementById('schedule-modal').classList.add('hidden'); });
    var smConfirm = document.getElementById('sm-confirm');
    if (smConfirm) smConfirm.addEventListener('click', function () { page.saveSchedule(); });
    var smModal = document.getElementById('schedule-modal');
    if (smModal) smModal.addEventListener('click', function (e) { if (e.target === this) this.classList.add('hidden'); });

    // Cron presets
    var presets = document.querySelectorAll('.cron-preset');
    for (var p = 0; p < presets.length; p++) {
      presets[p].addEventListener('click', function () {
        document.getElementById('sm-cron').value = this.getAttribute('data-cron');
      });
    }

    // Load tags on init
    page.loadTags();
  };

  /* ============ CHANGE 1: Project Edit/Delete ============ */
  page.openProjectEditModal = function () {
    var d = page.projectData;
    document.getElementById('pe-name').value = d ? d.name : '';
    document.getElementById('pe-desc').value = d ? (d.description || '') : '';
    document.getElementById('pe-url').value = d ? (d.url || '') : '';
    document.getElementById('project-edit-modal').classList.remove('hidden');
  };

  page.saveProject = function () {
    var name = document.getElementById('pe-name').value.trim();
    if (!name) { window.App.utils.showToast('\u8bf7\u8f93\u5165\u9879\u76ee\u540d\u79f0', 'error'); return; }
    var payload = {
      name: name,
      description: document.getElementById('pe-desc').value.trim(),
      url: document.getElementById('pe-url').value.trim(),
    };
    window.App.api.put('/api/projects/' + page.projectId, payload)
      .then(function () {
        window.App.utils.showToast('\u9879\u76ee\u5df2\u66f4\u65b0', 'success');
        document.getElementById('project-edit-modal').classList.add('hidden');
        page.loadProjectInfo();
      })
      .catch(function (err) { window.App.utils.showToast(err.detail || '\u66f4\u65b0\u5931\u8d25', 'error'); });
  };

  /* ============ CHANGE 2: Structured Case Form ============ */
  page.toggleCaseTypeFields = function (type) {
    var apiFields = document.getElementById('cm-api-fields');
    var uiFields = document.getElementById('cm-ui-fields');
    if (type === 'UI') {
      apiFields.classList.add('hidden');
      uiFields.classList.remove('hidden');
    } else {
      apiFields.classList.remove('hidden');
      uiFields.classList.add('hidden');
    }
  };

  page.openCaseModal = function (caseData) {
    var isEdit = !!caseData;
    document.getElementById('case-modal-title').textContent = isEdit ? '\u7f16\u8f91\u7528\u4f8b' : '\u65b0\u5efa\u7528\u4f8b';
    document.getElementById('cm-edit-id').value = isEdit ? caseData.id : '';
    document.getElementById('cm-name').value = isEdit ? caseData.name : '';
    var type = isEdit ? (caseData.test_type || 'API').toUpperCase() : 'API';
    document.getElementById('cm-type').value = type;
    page.toggleCaseTypeFields(type);

    var content = isEdit ? (caseData.content || {}) : {};
    document.getElementById('cm-method').value = content.method || 'GET';
    document.getElementById('cm-url').value = content.url || '';
    var hdrLines = [];
    if (content.headers) {
      for (var k in content.headers) {
        if (content.headers.hasOwnProperty(k)) hdrLines.push(k + ': ' + content.headers[k]);
      }
    }
    document.getElementById('cm-headers').value = hdrLines.join('\n');
    document.getElementById('cm-body').value = content.body ? JSON.stringify(content.body, null, 2) : '';

    // Build assertions
    var assertContainer = document.getElementById('cm-assertions');
    assertContainer.innerHTML = '';
    var assertions = content.assertions || [];
    if (assertions.length === 0) {
      page.addAssertionRow();
    } else {
      for (var i = 0; i < assertions.length; i++) {
        page.addAssertionRow(assertions[i]);
      }
    }

    // Build UI steps
    var stepsContainer = document.getElementById('cm-steps');
    stepsContainer.innerHTML = '';
    var steps = content.steps || [];
    if (steps.length === 0 && type === 'UI') {
      page.addStepRow();
    } else {
      for (var j = 0; j < steps.length; j++) {
        page.addStepRow(steps[j]);
      }
    }

    // skip_auth 勾选框
    document.getElementById('cm-skip-auth').checked = isEdit ? !!caseData.skip_auth : false;

    // 标签
    document.getElementById('cm-tags').value = isEdit && caseData.tags ? caseData.tags.join(', ') : '';

    document.getElementById('case-modal').classList.remove('hidden');
  };

  page.closeCaseModal = function () {
    document.getElementById('case-modal').classList.add('hidden');
  };

  page.addAssertionRow = function (data) {
    var container = document.getElementById('cm-assertions');
    var row = document.createElement('div');
    row.className = 'flex items-center gap-2 assertion-row';

    var typeOptions = '<option value="status_code"' + (data && data.type === 'status_code' ? ' selected' : '') + '>status_code</option>'
      + '<option value="json_path"' + (data && data.type === 'json_path' ? ' selected' : '') + '>json_path</option>'
      + '<option value="header"' + (data && data.type === 'header' ? ' selected' : '') + '>header</option>'
      + '<option value="body_contains"' + (data && data.type === 'body_contains' ? ' selected' : '') + '>body_contains</option>'
      + '<option value="regex"' + (data && data.type === 'regex' ? ' selected' : '') + '>regex</option>'
      + '<option value="element_exists"' + (data && data.type === 'element_exists' ? ' selected' : '') + '>element_exists</option>'
      + '<option value="text_contains"' + (data && data.type === 'text_contains' ? ' selected' : '') + '>text_contains</option>'
      + '<option value="url_contains"' + (data && data.type === 'url_contains' ? ' selected' : '') + '>url_contains</option>';

    var opOptions = '<option value="eq"' + (data && data.operator === 'eq' ? ' selected' : '') + '>eq</option>'
      + '<option value="ne"' + (data && data.operator === 'ne' ? ' selected' : '') + '>ne</option>'
      + '<option value="gt"' + (data && data.operator === 'gt' ? ' selected' : '') + '>gt</option>'
      + '<option value="lt"' + (data && data.operator === 'lt' ? ' selected' : '') + '>lt</option>'
      + '<option value="contains"' + (data && data.operator === 'contains' ? ' selected' : '') + '>contains</option>'
      + '<option value="regex"' + (data && data.operator === 'regex' ? ' selected' : '') + '>regex</option>';

    row.innerHTML = '<select class="assert-type px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-primary-500 w-28">' + typeOptions + '</select>'
      + '<input class="assert-target flex-1 px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-primary-500" placeholder="target" value="' + (data ? window.App.utils.escapeHtml(data.target || '') : '') + '" />'
      + '<select class="assert-op px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-primary-500 w-20">' + opOptions + '</select>'
      + '<input class="assert-expected flex-1 px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-primary-500" placeholder="expected" value="' + (data ? window.App.utils.escapeHtml(String(data.expected !== undefined ? data.expected : '')) : '') + '" />'
      + '<button class="remove-assertion text-red-400 hover:text-red-600 text-xs px-1">\u00d7</button>';

    row.querySelector('.remove-assertion').addEventListener('click', function () { row.remove(); });
    container.appendChild(row);
  };

  page.addStepRow = function (data) {
    var container = document.getElementById('cm-steps');
    var row = document.createElement('div');
    row.className = 'flex items-center gap-2 step-row';

    var actionOptions = '<option value="open_app"' + (data && data.action === 'open_app' ? ' selected' : '') + '>open_app</option>'
      + '<option value="navigate"' + (data && data.action === 'navigate' ? ' selected' : '') + '>navigate</option>'
      + '<option value="click"' + (data && data.action === 'click' ? ' selected' : '') + '>click</option>'
      + '<option value="type"' + (data && data.action === 'type' ? ' selected' : '') + '>type</option>'
      + '<option value="keypress"' + (data && data.action === 'keypress' ? ' selected' : '') + '>keypress</option>'
      + '<option value="scroll"' + (data && data.action === 'scroll' ? ' selected' : '') + '>scroll</option>'
      + '<option value="screenshot"' + (data && data.action === 'screenshot' ? ' selected' : '') + '>screenshot</option>'
      + '<option value="wait"' + (data && data.action === 'wait' ? ' selected' : '') + '>wait</option>';

    row.innerHTML = '<select class="step-action px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-primary-500 w-24">' + actionOptions + '</select>'
      + '<input class="step-target flex-1 px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-primary-500" placeholder="target (element/app)" value="' + (data ? window.App.utils.escapeHtml(data.target || '') : '') + '" />'
      + '<input class="step-value flex-1 px-2 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-primary-500" placeholder="value (text/url)" value="' + (data ? window.App.utils.escapeHtml(data.value || '') : '') + '" />'
      + '<label class="flex items-center gap-1 text-xs text-gray-500"><input type="checkbox" class="step-screenshot rounded border-gray-300 text-primary-600" ' + (data && data.screenshot ? 'checked' : '') + ' />截图</label>'
      + '<button class="remove-step text-red-400 hover:text-red-600 text-xs px-1">\u00d7</button>';

    row.querySelector('.remove-step').addEventListener('click', function () { row.remove(); });
    container.appendChild(row);
  };

  page.collectCaseFormData = function () {
    var name = document.getElementById('cm-name').value.trim();
    var type = document.getElementById('cm-type').value;
    if (!name) return null;

    var content = {};
    if (type === 'API') {
      content.method = document.getElementById('cm-method').value;
      content.url = document.getElementById('cm-url').value.trim();
      var hdrText = document.getElementById('cm-headers').value.trim();
      var headers = {};
      if (hdrText) {
        var lines = hdrText.split('\n');
        for (var i = 0; i < lines.length; i++) {
          var idx = lines[i].indexOf(':');
          if (idx > 0) headers[lines[i].substring(0, idx).trim()] = lines[i].substring(idx + 1).trim();
        }
      }
      if (Object.keys(headers).length > 0) content.headers = headers;
      var bodyText = document.getElementById('cm-body').value.trim();
      if (bodyText) {
        try { content.body = JSON.parse(bodyText); } catch (e) { content.body = bodyText; }
      }
    } else if (type === 'UI') {
      var steps = [];
      var stepRows = document.querySelectorAll('#cm-steps .step-row');
      for (var si = 0; si < stepRows.length; si++) {
        var sr = stepRows[si];
        var sAction = sr.querySelector('.step-action').value;
        var sTarget = sr.querySelector('.step-target').value.trim();
        var sValue = sr.querySelector('.step-value').value.trim();
        var sScreenshot = sr.querySelector('.step-screenshot').checked;
        if (sAction) {
          steps.push({ action: sAction, target: sTarget, value: sValue, screenshot: sScreenshot, wait_after: 0.5 });
        }
      }
      content.steps = steps;
    }

    var assertions = [];
    var assertRows = document.querySelectorAll('#cm-assertions .assertion-row');
    for (var j = 0; j < assertRows.length; j++) {
      var r = assertRows[j];
      var aType = r.querySelector('.assert-type').value;
      var aTarget = r.querySelector('.assert-target').value.trim();
      var aOp = r.querySelector('.assert-op').value;
      var aExpected = r.querySelector('.assert-expected').value.trim();
      if (aType && aOp) {
        var expVal = aExpected;
        if (aExpected !== '' && !isNaN(aExpected)) expVal = Number(aExpected);
        assertions.push({ type: aType, target: aTarget || 'status_code', operator: aOp, expected: expVal });
      }
    }
    if (assertions.length > 0) content.assertions = assertions;

    // 标签：逗号分隔转数组，去空白去空
    var tagsStr = document.getElementById('cm-tags').value.trim();
    var tags = tagsStr ? tagsStr.split(',').map(function (t) { return t.trim(); }).filter(function (t) { return t; }) : [];

    return {
      name: name,
      test_type: type,
      content: content,
      skip_auth: document.getElementById('cm-skip-auth').checked,
      tags: tags,
    };
  };

  page.saveCase = function () {
    var data = page.collectCaseFormData();
    if (!data) { window.App.utils.showToast('\u8bf7\u8f93\u5165\u7528\u4f8b\u540d\u79f0', 'error'); return; }

    var editId = document.getElementById('cm-edit-id').value;
    var url, method;
    if (editId) {
      url = '/api/projects/' + page.projectId + '/cases/' + editId;
      method = 'patch';
    } else {
      url = '/api/projects/' + page.projectId + '/cases';
      method = 'post';
    }

    window.App.api[method](url, data)
      .then(function () {
        window.App.utils.showToast(editId ? '\u7528\u4f8b\u5df2\u66f4\u65b0' : '\u7528\u4f8b\u521b\u5efa\u6210\u529f', 'success');
        page.closeCaseModal();
        page.loadCases();
      })
      .catch(function (err) { window.App.utils.showToast(err.detail || '\u4fdd\u5b58\u5931\u8d25', 'error'); });
  };

  /* ============ Cases List ============ */
  page.loadCases = function () {
    var filter = document.getElementById('case-filter');
    var filterVal = filter ? filter.value : '';
    var url = '/api/projects/' + page.projectId + '/cases?offset=0&limit=100';
    if (filterVal) url += '&test_type=' + filterVal;

    window.App.api.get(url)
      .then(function (data) {
        var cases = Array.isArray(data) ? data : (data.items || []);
        var tbody = document.getElementById('case-list');
        if (!tbody) return;
        if (cases.length === 0) {
          tbody.innerHTML = '<tr><td colspan="6" class="text-center py-12 text-gray-400">\u6682\u65e0\u7528\u4f8b</td></tr>';
          return;
        }
        var html = '';
        for (var i = 0; i < cases.length; i++) {
          var c = cases[i];
          var typeBadge = c.test_type || '-';
          var typeColor = typeBadge === 'API' ? 'bg-blue-100 text-blue-700'
            : typeBadge === 'UI' ? 'bg-purple-100 text-purple-700'
            : typeBadge === 'Perf' ? 'bg-orange-100 text-orange-700'
            : 'bg-gray-100 text-gray-700';
          var checked = page.selectedCases[c.id] ? ' checked' : '';
          var skipBadge = c.skip_auth ? ' <span class="text-xs text-yellow-600 font-medium">(\u8df3\u8fc7\u8ba4\u8bc1)</span>' : '';
          var tagsHtml = '';
          if (c.tags && c.tags.length > 0) {
            for (var ti = 0; ti < c.tags.length; ti++) {
              tagsHtml += '<span class="inline-block px-1.5 py-0.5 mr-1 mb-0.5 rounded text-xs bg-gray-100 text-gray-600">' + window.App.utils.escapeHtml(c.tags[ti]) + '</span>';
            }
            tagsHtml = '<div class="mt-0.5">' + tagsHtml + '</div>';
          }
          html += '<tr class="border-b border-gray-50">'
            + '<td class="px-3 py-3 text-center"><input type="checkbox" class="case-select rounded border-gray-300 text-primary-600 focus:ring-primary-500" value="' + c.id + '"' + checked + ' /></td>'
            + '<td class="px-4 py-3 font-medium text-gray-800">' + window.App.utils.escapeHtml(c.name) + skipBadge + tagsHtml + '</td>'
            + '<td class="px-4 py-3"><span class="inline-block px-2 py-0.5 rounded text-xs font-medium ' + typeColor + '">' + window.App.utils.escapeHtml(typeBadge) + '</span></td>'
            + '<td class="px-4 py-3 text-gray-500 hidden md:table-cell">' + window.App.utils.escapeHtml(c.source || 'manual') + '</td>'
            + '<td class="px-4 py-3 text-gray-500 hidden md:table-cell">' + window.App.utils.formatDate(c.created_at) + '</td>'
            + '<td class="px-4 py-3 text-center whitespace-nowrap">'
            +   '<button class="edit-case text-primary-600 hover:text-primary-800 text-xs font-medium mr-2" data-idx="' + i + '">\u7f16\u8f91</button>'
            +   '<button class="delete-case text-red-500 hover:text-red-700 text-xs font-medium" data-id="' + c.id + '">\u5220\u9664</button>'
            + '</td></tr>';
        }
        tbody.innerHTML = html;

        // Store cases for edit lookup
        page._casesList = cases;

        // Bind checkboxes
        var boxes = tbody.querySelectorAll('.case-select');
        for (var k = 0; k < boxes.length; k++) {
          boxes[k].addEventListener('change', function () {
            if (this.checked) page.selectedCases[this.value] = true;
            else delete page.selectedCases[this.value];
            page.updateSelectionButtons();
          });
        }

        // Bind edit buttons (Change 3)
        var editBtns = tbody.querySelectorAll('.edit-case');
        for (var m = 0; m < editBtns.length; m++) {
          editBtns[m].addEventListener('click', function () {
            var idx = parseInt(this.getAttribute('data-idx'));
            page.openCaseModal(page._casesList[idx]);
          });
        }

        // Bind delete buttons
        var delBtns = tbody.querySelectorAll('.delete-case');
        for (var j = 0; j < delBtns.length; j++) {
          delBtns[j].addEventListener('click', function () {
            var caseId = this.getAttribute('data-id');
            if (!confirm('\u786e\u5b9a\u5220\u9664\u8be5\u7528\u4f8b\uff1f')) return;
            window.App.api.del('/api/projects/' + page.projectId + '/cases/' + caseId)
              .then(function () {
                window.App.utils.showToast('\u5df2\u5220\u9664', 'success');
                delete page.selectedCases[caseId];
                page.updateSelectionButtons();
                page.loadCases();
              })
              .catch(function (err) { window.App.utils.showToast(err.detail || '\u5220\u9664\u5931\u8d25', 'error'); });
          });
        }
      })
      .catch(function (err) { console.error('Load cases error:', err); });
  };

  page.updateSelectionButtons = function () {
    var count = Object.keys(page.selectedCases).length;
    var execBtn = document.getElementById('execute-cases-btn');
    if (execBtn) {
      execBtn.disabled = count === 0;
      execBtn.textContent = count > 0 ? '\u6267\u884c\u9009\u4e2d\u7528\u4f8b (' + count + ')' : '\u6267\u884c\u9009\u4e2d\u7528\u4f8b';
    }
    var delBtn = document.getElementById('batch-delete-cases-btn');
    if (delBtn) {
      delBtn.disabled = count === 0;
      delBtn.textContent = count > 0 ? '\u5220\u9664\u9009\u4e2d (' + count + ')' : '\u5220\u9664\u9009\u4e2d';
    }
  };

  page.executeSelectedCases = function () {
    var caseIds = Object.keys(page.selectedCases).map(Number);
    if (caseIds.length === 0) { window.App.utils.showToast('\u8bf7\u81f3\u5c11\u9009\u62e9\u4e00\u4e2a\u7528\u4f8b', 'error'); return; }
    window.App.utils.showLoading();
    window.App.api.post('/api/projects/' + page.projectId + '/runs', { case_ids: caseIds })
      .then(function (data) {
        window.App.utils.showToast('\u6267\u884c\u5df2\u521b\u5efa', 'success');
        window.App.router.navigate('/runs/' + data.id);
      })
      .catch(function (err) { window.App.utils.showToast(err.detail || '\u521b\u5efa\u5931\u8d25', 'error'); })
      .finally(function () { window.App.utils.hideLoading(); });
  };

  /* ============ CHANGE 4: Batch Delete ============ */
  page.batchDeleteCases = function () {
    var caseIds = Object.keys(page.selectedCases).map(Number);
    if (caseIds.length === 0) return;
    if (!confirm('\u786e\u5b9a\u5220\u9664\u9009\u4e2d\u7684 ' + caseIds.length + ' \u6761\u7528\u4f8b\uff1f')) return;

    window.App.api.del('/api/projects/' + page.projectId + '/cases/batch', caseIds)
      .then(function () {
        window.App.utils.showToast('\u5df2\u5220\u9664 ' + caseIds.length + ' \u6761\u7528\u4f8b', 'success');
        page.selectedCases = {};
        page.updateSelectionButtons();
        page.loadCases();
      })
      .catch(function (err) { window.App.utils.showToast(err.detail || '\u5220\u9664\u5931\u8d25', 'error'); });
  };


  /* ---- Import / Export ---- */
  page.exportCases = function () {
    window.App.utils.showLoading();
    window.App.api.get('/api/projects/' + page.projectId + '/cases/export')
      .then(function (data) {
        var json = JSON.stringify(data, null, 2);
        var blob = new Blob([json], { type: 'application/json' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'test-cases-' + page.projectId + '.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        window.App.utils.showToast('\u5df2\u5bfc\u51fa ' + data.cases.length + ' \u6761\u7528\u4f8b', 'success');
      })
      .catch(function (err) { window.App.utils.showToast(err.detail || '\u5bfc\u51fa\u5931\u8d25', 'error'); })
      .finally(function () { window.App.utils.hideLoading(); });
  };

  page.importCases = function () {
    var input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = function () {
      var file = input.files[0];
      if (!file) return;
      window.App.utils.showLoading();
      var formData = new FormData();
      formData.append('file', file);
      fetch('/api/projects/' + page.projectId + '/cases/import', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + window.App.auth.getToken() },
        body: formData
      })
        .then(function (response) {
          return response.json().then(function (data) {
            if (!response.ok) return Promise.reject(data);
            return data;
          });
        })
        .then(function (result) {
          window.App.utils.showToast('\u5bfc\u5165\u5b8c\u6210\uff1a' + result.imported + ' \u6761\u65b0\u589e\uff0c' + result.skipped + ' \u6761\u8df3\u8fc7', 'success');
          page.loadCases();
          page.loadTags();
        })
        .catch(function (err) { window.App.utils.showToast(err.detail || '\u5bfc\u5165\u5931\u8d25', 'error'); })
        .finally(function () { window.App.utils.hideLoading(); });
    };
    input.click();
  };

  /* ---- Tags & By-tag execution ---- */
  page.loadTags = function () {
    window.App.api.get('/api/projects/' + page.projectId + '/cases/tags')
      .then(function (data) {
        var tags = data.tags || [];
        var filter = document.getElementById('tag-filter');
        var smTag = document.getElementById('sm-tag');
        if (filter) {
          var val = filter.value;
          filter.innerHTML = '<option value="">\u5168\u90e8\u6807\u7b7e</option>';
          for (var i = 0; i < tags.length; i++) {
            filter.innerHTML += '<option value="' + window.App.utils.escapeHtml(tags[i]) + '">' + window.App.utils.escapeHtml(tags[i]) + '</option>';
          }
          filter.value = val;
        }
        if (smTag) {
          var smVal = smTag.value;
          smTag.innerHTML = '<option value="">\u5168\u90e8\u7528\u4f8b</option>';
          for (var j = 0; j < tags.length; j++) {
            smTag.innerHTML += '<option value="' + window.App.utils.escapeHtml(tags[j]) + '">' + window.App.utils.escapeHtml(tags[j]) + '</option>';
          }
          smTag.value = smVal;
        }
      })
      .catch(function () { /* ignore */ });
  };

  page.executeByTag = function () {
    var tag = document.getElementById('tag-filter').value;
    if (!tag) { window.App.utils.showToast('\u8bf7\u5148\u9009\u62e9\u6807\u7b7e', 'error'); return; }
    window.App.utils.showLoading();
    window.App.api.post('/api/projects/' + page.projectId + '/runs/by-tag', { tag: tag })
      .then(function (data) {
        window.App.utils.showToast('\u6267\u884c\u5df2\u521b\u5efa\uff08\u6807\u7b7e: ' + tag + '\uff09', 'success');
        window.App.router.navigate('/runs/' + data.id);
      })
      .catch(function (err) { window.App.utils.showToast(err.detail || '\u521b\u5efa\u5931\u8d25', 'error'); })
      .finally(function () { window.App.utils.hideLoading(); });
  };

  /* ---- Schedules ---- */
  page.loadSchedules = function () {
    window.App.api.get('/api/projects/' + page.projectId + '/schedules')
      .then(function (data) {
        var schedules = Array.isArray(data) ? data : (data || []);
        var tbody = document.getElementById('schedule-list');
        if (!tbody) return;
        if (schedules.length === 0) {
          tbody.innerHTML = '<tr><td colspan="6" class="text-center py-12 text-gray-400">\u6682\u65e0\u8c03\u5ea6</td></tr>';
          return;
        }
        var html = '';
        for (var i = 0; i < schedules.length; i++) {
          var s = schedules[i];
          var statusBadge = s.enabled
            ? '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">\u542f\u7528</span>'
            : '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">\u505c\u7528</span>';
          html += '<tr class="border-b border-gray-50">'
            + '<td class="px-4 py-3 font-medium text-gray-800">' + window.App.utils.escapeHtml(s.tag || '\u5168\u90e8') + '</td>'
            + '<td class="px-4 py-3 font-mono text-sm text-gray-600">' + window.App.utils.escapeHtml(s.cron_expr) + '</td>'
            + '<td class="px-4 py-3 hidden md:table-cell">' + statusBadge + '</td>'
            + '<td class="px-4 py-3 text-gray-500 hidden md:table-cell">' + (s.last_run_at ? window.App.utils.formatDate(s.last_run_at) : '-') + '</td>'
            + '<td class="px-4 py-3 text-gray-500 hidden md:table-cell">' + (s.next_run_at ? window.App.utils.formatDate(s.next_run_at) : '-') + '</td>'
            + '<td class="px-4 py-3 text-center whitespace-nowrap">'
            +   '<button class="edit-schedule text-primary-600 hover:text-primary-800 text-xs font-medium mr-2" data-idx="' + i + '">\u7f16\u8f91</button>'
            +   '<button class="delete-schedule text-red-500 hover:text-red-700 text-xs font-medium" data-id="' + s.id + '">\u5220\u9664</button>'
            + '</td></tr>';
        }
        tbody.innerHTML = html;

        page._schedulesList = schedules;

        var editBtns = tbody.querySelectorAll('.edit-schedule');
        for (var m = 0; m < editBtns.length; m++) {
          editBtns[m].addEventListener('click', function () {
            page.openScheduleModal(page._schedulesList[parseInt(this.getAttribute('data-idx'))]);
          });
        }

        var delBtns = tbody.querySelectorAll('.delete-schedule');
        for (var j = 0; j < delBtns.length; j++) {
          delBtns[j].addEventListener('click', function () {
            var sid = this.getAttribute('data-id');
            if (!confirm('\u786e\u5b9a\u5220\u9664\u8be5\u8c03\u5ea6\uff1f')) return;
            window.App.api.del('/api/projects/' + page.projectId + '/schedules/' + sid)
              .then(function () { window.App.utils.showToast('\u5df2\u5220\u9664', 'success'); page.loadSchedules(); })
              .catch(function (err) { window.App.utils.showToast(err.detail || '\u5220\u9664\u5931\u8d25', 'error'); });
          });
        }
      })
      .catch(function (err) { console.error('Load schedules error:', err); });
  };

  page.openScheduleModal = function (sch) {
    var isEdit = !!sch;
    document.getElementById('schedule-modal-title').textContent = isEdit ? '\u7f16\u8f91\u8c03\u5ea6' : '\u65b0\u5efa\u8c03\u5ea6';
    document.getElementById('sm-edit-id').value = isEdit ? sch.id : '';
    document.getElementById('sm-tag').value = isEdit ? (sch.tag || '') : '';
    document.getElementById('sm-cron').value = isEdit ? sch.cron_expr : '';
    document.getElementById('sm-enabled').checked = isEdit ? sch.enabled : true;
    document.getElementById('schedule-modal').classList.remove('hidden');
  };

  page.saveSchedule = function () {
    var editId = document.getElementById('sm-edit-id').value;
    var cronExpr = document.getElementById('sm-cron').value.trim();
    if (!cronExpr) { window.App.utils.showToast('\u8bf7\u8f93\u5165 Cron \u8868\u8fbe\u5f0f', 'error'); return; }

    var payload = {
      tag: document.getElementById('sm-tag').value,
      cron_expr: cronExpr,
      enabled: document.getElementById('sm-enabled').checked,
    };

    var url, method;
    if (editId) {
      url = '/api/projects/' + page.projectId + '/schedules/' + editId;
      method = 'put';
    } else {
      url = '/api/projects/' + page.projectId + '/schedules';
      method = 'post';
    }

    window.App.api[method](url, payload)
      .then(function () {
        window.App.utils.showToast(editId ? '\u8c03\u5ea6\u5df2\u66f4\u65b0' : '\u8c03\u5ea6\u5df2\u521b\u5efa', 'success');
        document.getElementById('schedule-modal').classList.add('hidden');
        page.loadSchedules();
      })
      .catch(function (err) { window.App.utils.showToast(err.detail || '\u4fdd\u5b58\u5931\u8d25', 'error'); });
  };

  /* ---- Runs ---- */
  page.loadRuns = function () {
    window.App.api.get('/api/projects/' + page.projectId + '/runs?offset=0&limit=50')
      .then(function (data) {
        var runs = Array.isArray(data) ? data : (data.items || []);
        var tbody = document.getElementById('run-list');
        if (!tbody) return;
        if (runs.length === 0) {
          tbody.innerHTML = '<tr><td colspan="4" class="text-center py-12 text-gray-400">\u6682\u65e0\u6267\u884c\u8bb0\u5f55</td></tr>';
          return;
        }
        var html = '';
        for (var i = 0; i < runs.length; i++) {
          var r = runs[i];
          var statusColor = r.status === 'done' && r.result === 'pass' ? 'bg-green-100 text-green-700'
            : r.status === 'done' && r.result === 'fail' ? 'bg-red-100 text-red-700'
            : r.status === 'running' ? 'bg-yellow-100 text-yellow-700'
            : r.status === 'queued' ? 'bg-blue-100 text-blue-700'
            : 'bg-gray-100 text-gray-700';
          var statusLabel = r.status === 'done' ? (r.result || 'done') : r.status;
          html += '<tr class="border-b border-gray-50 hover:bg-gray-50 cursor-pointer run-row" data-run-id="' + r.id + '">'
            + '<td class="px-4 py-3"><span class="inline-block px-2 py-0.5 rounded text-xs font-medium ' + statusColor + '">' + window.App.utils.escapeHtml(statusLabel) + '</span></td>'
            + '<td class="px-4 py-3 text-gray-600">' + window.App.utils.formatDate(r.created_at) + '</td>'
            + '<td class="px-4 py-3 text-gray-500 hidden md:table-cell">' + window.App.utils.escapeHtml(r.summary || '-') + '</td>'
            + '<td class="px-4 py-3 text-center"><span class="text-xs text-gray-400">\u67e5\u770b</span></td></tr>';
        }
        tbody.innerHTML = html;

        var rows = tbody.querySelectorAll('.run-row');
        for (var j = 0; j < rows.length; j++) {
          rows[j].addEventListener('click', function () {
            window.App.router.navigate('/runs/' + this.getAttribute('data-run-id'));
          });
        }
      })
      .catch(function (err) { console.error('Load runs error:', err); });
  };

  /* ---- Docs ---- */
  page.loadDocs = function () {
    window.App.api.get('/api/projects/' + page.projectId + '/docs')
      .then(function (data) {
        var docs = Array.isArray(data) ? data : (data.items || []);
        var tbody = document.getElementById('doc-list');
        if (!tbody) return;
        if (docs.length === 0) {
          tbody.innerHTML = '<tr><td colspan="3" class="text-center py-12 text-gray-400">\u6682\u65e0\u6587\u6863</td></tr>';
          return;
        }
        var html = '';
        for (var i = 0; i < docs.length; i++) {
          var d = docs[i];
          html += '<tr class="border-b border-gray-50">'
            + '<td class="px-4 py-3 text-gray-800">' + window.App.utils.escapeHtml(d.filename || d.file_name || '-') + '</td>'
            + '<td class="px-4 py-3 text-gray-500">' + window.App.utils.formatDate(d.created_at) + '</td>'
            + '<td class="px-4 py-3 text-center">'
            +   '<button class="delete-doc text-red-500 hover:text-red-700 text-xs font-medium" data-id="' + d.id + '">\u5220\u9664</button>'
            + '</td></tr>';
        }
        tbody.innerHTML = html;

        var delBtns = tbody.querySelectorAll('.delete-doc');
        for (var j = 0; j < delBtns.length; j++) {
          delBtns[j].addEventListener('click', function () {
            var docId = this.getAttribute('data-id');
            if (!confirm('\u786e\u5b9a\u5220\u9664\u8be5\u6587\u6863\uff1f')) return;
            window.App.api.del('/api/projects/' + page.projectId + '/docs/' + docId)
              .then(function () { window.App.utils.showToast('\u5df2\u5220\u9664', 'success'); page.loadDocs(); })
              .catch(function (err) { window.App.utils.showToast(err.detail || '\u5220\u9664\u5931\u8d25', 'error'); });
          });
        }
      })
      .catch(function (err) { console.error('Load docs error:', err); });
  };

  /* ============ Auth Config Panel ============ */
  page.bindAuthConfigEvents = function () {
    // Collapsible toggle
    var toggle = document.getElementById('auth-config-toggle');
    if (toggle) {
      toggle.addEventListener('click', function () {
        var panel = document.getElementById('auth-config-panel');
        var arrow = document.getElementById('auth-config-arrow');
        if (!panel) return;
        var isHidden = panel.classList.contains('hidden');
        panel.classList.toggle('hidden');
        if (arrow) arrow.style.transform = isHidden ? 'rotate(0deg)' : 'rotate(-90deg)';
      });
    }

    // Method dropdown toggle
    var method = document.getElementById('ac-method');
    if (method) {
      method.addEventListener('change', function () {
        page.toggleAuthMethodFields(this.value);
      });
    }

    // Test auth button
    var testBtn = document.getElementById('ac-test-btn');
    if (testBtn) {
      testBtn.addEventListener('click', function () { page.testAuthConfig(); });
    }

    // Save button
    var saveBtn = document.getElementById('ac-save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', function () { page.saveAuthConfig(); });
    }
  };

  page.loadAuthConfigForm = function (authConfig) {
    var ac = authConfig || {};
    var enabled = document.getElementById('ac-enabled');
    var method = document.getElementById('ac-method');
    if (!enabled) return;
    enabled.checked = ac.enabled || false;
    page.toggleAuthMethodFields(ac.token_value ? 'token' : 'login');
    if (method) method.value = ac.token_value ? 'token' : 'login';
    var setVal = function (id, val) { var el = document.getElementById(id); if (el) el.value = val || ''; };
    setVal('ac-login-url', ac.login_url);
    setVal('ac-login-body', ac.login_body ? JSON.stringify(ac.login_body, null, 2) : '');
    setVal('ac-token-path', ac.token_json_path || 'token');
    setVal('ac-token-value', ac.token_value);
    setVal('ac-header-name', ac.header_name || 'Authorization');
    setVal('ac-header-format', ac.header_format || 'Bearer {token}');
    page.updateAuthBadge(ac.enabled || false);
  };

  page.toggleAuthMethodFields = function (method) {
    var loginFields = document.getElementById('ac-login-fields');
    var tokenFields = document.getElementById('ac-token-fields');
    if (!loginFields || !tokenFields) return;
    if (method === 'token') {
      loginFields.classList.add('hidden');
      tokenFields.classList.remove('hidden');
    } else {
      loginFields.classList.remove('hidden');
      tokenFields.classList.add('hidden');
    }
  };

  page.updateAuthBadge = function (enabled) {
    var badge = document.getElementById('auth-config-badge');
    if (badge) {
      if (enabled) {
        badge.classList.remove('hidden');
      } else {
        badge.classList.add('hidden');
      }
    }
  };

  page.collectAuthConfig = function () {
    var enabled = document.getElementById('ac-enabled');
    var method = document.getElementById('ac-method');
    var loginUrl = document.getElementById('ac-login-url');
    var loginBody = document.getElementById('ac-login-body');
    var tokenPath = document.getElementById('ac-token-path');
    var tokenValue = document.getElementById('ac-token-value');
    var headerName = document.getElementById('ac-header-name');
    var headerFormat = document.getElementById('ac-header-format');
    if (!enabled) return null;

    var loginBodyParsed = {};
    try {
      if (loginBody && loginBody.value.trim()) {
        loginBodyParsed = JSON.parse(loginBody.value.trim());
      }
    } catch (e) { /* ignore parse errors */ }

    var config = {
      enabled: enabled.checked,
      login_url: loginUrl ? loginUrl.value.trim() : '',
      login_body: loginBodyParsed,
      token_json_path: tokenPath ? tokenPath.value.trim() || 'token' : 'token',
      token_value: method && method.value === 'token' ? (tokenValue ? tokenValue.value.trim() : '') : '',
      header_name: headerName ? headerName.value.trim() || 'Authorization' : 'Authorization',
      header_format: headerFormat ? headerFormat.value.trim() || 'Bearer {token}' : 'Bearer {token}',
    };
    return config;
  };

  page.saveAuthConfig = function () {
    var config = page.collectAuthConfig();
    if (!config) { window.App.utils.showToast('\u8ba4\u8bc1\u914d\u7f6e\u9875\u9762\u672a\u52a0\u8f7d', 'error'); return; }
    window.App.utils.showLoading();
    window.App.api.put('/api/projects/' + page.projectId, { auth_config: config })
      .then(function () {
        page.loadProjectInfo();
        window.App.utils.showToast('\u8ba4\u8bc1\u914d\u7f6e\u5df2\u4fdd\u5b58', 'success');
      })
      .catch(function (err) {
        window.App.utils.showToast(err.detail || '\u4fdd\u5b58\u5931\u8d25', 'error');
      })
      .finally(function () {
        window.App.utils.hideLoading();
      });
  };

  page.testAuthConfig = function () {
    var config = page.collectAuthConfig();
    if (!config) return;
    var statusEl = document.getElementById('ac-status');
    if (statusEl) statusEl.textContent = '\u6b63\u5728\u6d4b\u8bd5...';
    window.App.api.post('/api/projects/' + page.projectId + '/test-auth', config)
      .then(function (data) {
        if (statusEl) {
          if (data.success) {
            statusEl.textContent = '\u2713 ' + data.message + ' (' + data.token_preview + ')';
            statusEl.className = 'text-xs text-green-600';
          } else {
            statusEl.textContent = '\u2717 ' + data.message;
            statusEl.className = 'text-xs text-red-600';
          }
        }
      })
      .catch(function (err) {
        if (statusEl) {
          statusEl.textContent = '\u2717 \u6d4b\u8bd5\u5931\u8d25\uff1a' + (err.detail || err.message || '\u672a\u77e5\u9519\u8bef');
          statusEl.className = 'text-xs text-red-600';
        }
      });
  };

  window.App = window.App || {};
  window.App.projectDetail = page;
})();
