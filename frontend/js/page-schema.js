/* Existing schema API, exposed as a project workflow without another app. */
(function () {
  'use strict';
  var projectId, stubs = [];
  var app = window.App;
  function coverage() {
    var id = projectId;
    return app.api.get('/api/projects/' + id + '/coverage', {showLoading: false}).then(function (data) {
      if (projectId !== id || !document.getElementById('schema-coverage')) return;
      document.getElementById('schema-coverage').textContent = data.mode === 'schema'
        ? '已有用例端点 ' + data.endpoints_covered + ' / ' + data.endpoints_total + ' · 待补齐 ' + data.endpoints_uncovered
        : '尚未建立 OpenAPI 端点基线';
      document.getElementById('schema-endpoints').innerHTML = data.endpoints.map(function (ep) {
        return '<p>' + (ep.covered ? '✓ 已有用例' : '○ 待补齐') + ' · ' + app.utils.escapeHtml(ep.key) + '</p>';
      }).join('');
    }).catch(function () {});
  }
  function init(id) {
    if (projectId !== id) { projectId = id; stubs = []; }
    coverage();
    var parse = document.getElementById('schema-parse');
    var save = document.getElementById('schema-save');
    parse.onclick = function () {
      if (parse.disabled) return;
      var spec = document.getElementById('schema-spec').value;
      try { JSON.parse(spec); } catch (e) { app.utils.showToast('请输入有效的 OpenAPI JSON', 'error'); return; }
      parse.disabled = true;
      save.disabled = true;
      app.api.post('/api/projects/' + id + '/schema/parse', {spec: spec, mode: document.getElementById('schema-mode').value})
        .then(function (data) {
          if (projectId !== id || !document.getElementById('schema-preview')) return;
          stubs = data.stubs;
          document.getElementById('schema-preview').innerHTML = '<p class="text-sm">生成 ' + stubs.length + ' 条候选用例，请确认后保存。</p>' + stubs.map(function (stub, i) {
            return '<label class="block text-sm p-2 border rounded"><input type="checkbox" class="schema-select" value="' + i + '" checked> ' + app.utils.escapeHtml(stub.name) + '</label>';
          }).join('');
          save.disabled = !stubs.length;
          coverage();
        }).catch(function () {}).finally(function () { parse.disabled = false; });
    };
    save.onclick = function () {
      if (save.disabled) return;
      var selected = Array.from(document.querySelectorAll('.schema-select:checked')).map(function (el) {
        var stub = stubs[Number(el.value)];
        return {name: stub.name, test_type: 'api', source: stub.source, content: Object.assign({}, stub.content, {coverage_key: stub.coverage_key}), tags: ['schema']};
      });
      if (!selected.length) { app.utils.showToast('请至少选择一个候选用例', 'error'); return; }
      save.disabled = true;
      parse.disabled = true;
      app.api.post('/api/projects/' + id + '/cases/batch', {cases: selected})
        .then(function () {
          stubs = [];
          var preview = document.getElementById('schema-preview');
          if (preview) preview.textContent = '已保存 ' + selected.length + ' 条用例。请到“测试用例”中检查参数与预期并执行。';
          app.utils.showToast('用例已保存', 'success');
          coverage();
          app.projectDetail.loadTags();
        }).catch(function () { save.disabled = false; }).finally(function () { parse.disabled = false; });
    };
  }
  app.schema = {init: init};
})();
