// Run: node tests/frontend_maturity_check.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const values = new Map();
const nodes = new Map();
function element(id) {
  if (!nodes.has(id)) nodes.set(id, {value: '', checked: false, classList: {add() {}, remove() {}, toggle() {}}, addEventListener() {}, setAttribute() {}});
  return nodes.get(id);
}
const context = {window: {App: {}, location: {hash: ''}, addEventListener() {}}, document: {
  getElementById: element,
  querySelectorAll: () => [],
  createElement: () => ({appendChild(n) {this.innerHTML = n.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}),
  createTextNode: x => String(x),
}, localStorage: {getItem: k => values.get(k), setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k)}, setTimeout, clearTimeout, Date};
vm.createContext(context);
for (const name of ['utils', 'auth', 'page-project-detail']) vm.runInContext(fs.readFileSync('frontend/js/' + name + '.js','utf8'), context);
const app = context.window.App;
assert.equal(app.utils.escapeHtml('" onfocus="bad'), '&quot; onfocus=&quot;bad');
assert.equal(app.utils.escapeHtml(0), '0');
assert.equal(app.utils.formatDate('2026-09-11T03:25:00'), app.utils.formatDate('2026-09-11T03:25:00Z'));
const page = app.projectDetail;
element('cm-name').value = 'Workflow';
element('cm-type').value = 'API';
page.advancedContent = true;
element('cm-raw-content').value = JSON.stringify({workflow: [{method:'GET',url:'/items'}], custom: true});
assert.equal(page.collectCaseFormData().content.workflow[0].url, '/items');
assert.equal(page.collectCaseFormData().content.custom, true);
page.advancedContent = false;
page.originalContent = {coverage_key:'GET /items', body:false};
element('cm-body').value = 'false';
const result = page.collectCaseFormData();
assert.equal(result.content.coverage_key, 'GET /items');
assert.equal(result.content.body, false);
page._casesList = [{id:1, name:'Visible'}];
page.openScheduleModal({id:3, case_ids:[1,99], cron_expr:'0 * * * *', enabled:true});
assert.match(element('sm-case-ids').innerHTML, /value="99" selected/);
values.set('guest','true');
app.api = {post: async () => ({access_token:'test'}), get: async () => ({username:'review'})};
app.router = {navigate() {}};
app.utils.showToast = () => {};
app.auth.login('review','test').then(() => {assert.equal(app.auth.isGuest(), false); console.log('Frontend maturity checks passed');}).catch(e => {console.error(e); process.exitCode=1;});

import('../frontend/react-app/src/lib/date.js').then(({apiDate}) => { assert.equal(apiDate('2026-09-11T15:07:58').getTime(), apiDate('2026-09-11T15:07:58Z').getTime()); }).catch(e => {console.error(e); process.exitCode=1;});
