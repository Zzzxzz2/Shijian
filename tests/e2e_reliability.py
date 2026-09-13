"""Real browser acceptance against the isolated local review services.
Run explicitly; not part of pytest unit collection. Leaves only review fixtures.
"""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from run_permission_state_topic import call, BASE, TARGET, ROOT
from playwright.sync_api import sync_playwright, expect


def main():
    user=os.environ['E2E_ADMIN_USERNAME']; password=os.environ['E2E_ADMIN_PASSWORD']
    code,auth=call(BASE,'POST','/api/auth/login',{'username':user,'password':password})
    assert code == 200
    token=auth['access_token']
    _,project=call(BASE,'POST','/api/projects',{'name':'可靠性验收','url':TARGET},token)
    pid=project['id']
    ids=[]
    for name,path in [('快请求原始版本','/api/error/200'),('可取消慢请求','/api/slow?delay=10')]:
        code,case=call(BASE,'POST',f'/api/projects/{pid}/cases',{'name':name,'test_type':'api','content':{'method':'GET','url':path,'headers':{'Authorization':'Demo-private-credential'},'assertions':[{'type':'status_code','operator':'eq','expected':200}]}},token)
        assert code == 201
        ids.append(case['id'])
    out=ROOT/'test-results'/'reliability'; out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1280,'height':900})
        errors=[]; page.on('pageerror',lambda error: errors.append(str(error)))
        page.goto(BASE+'/app.html#/login')
        page.locator('#login-username').fill(user); page.locator('#login-password').fill(password); page.locator('#login-btn').click()
        expect(page).to_have_url(__import__('re').compile(r'#/projects$'))
        run_ids=[]
        for action,seconds in [('cancelled',30),('timeout',1)]:
            page.goto(BASE+f'/app.html#/projects/{pid}')
            expect(page.locator('#case-list .case-select')).to_have_count(2)
            page.locator('#select-all-cases').check()
            page.locator('#run-timeout').fill(str(seconds))
            page.locator('#execute-cases-btn').click()
            expect(page).to_have_url(__import__('re').compile(r'#/runs/\d+$'))
            rid=int(page.url.rsplit('/',1)[1]); run_ids.append(rid)
            if action == 'cancelled':
                expect(page.locator('#sum-pass')).to_have_text('1',timeout=15000)
                page.locator('#cancel-run-btn').click()
            expect(page.locator('#status-badge')).to_have_text('已取消' if action=='cancelled' else '执行超时',timeout=15000)
            expect(page.locator('#run-lifecycle')).to_contain_text('未完成：1')
            expect(page.locator('#cancel-run-btn')).to_be_hidden()
            expect(page.locator('#report-btn')).to_be_visible()
            page.get_by_text('执行输入快照',exact=True).click()
            expect(page.locator('#run-snapshot')).to_contain_text('[REDACTED]')
            assert 'Demo-private-credential' not in page.locator('#run-snapshot').inner_text()
            page.screenshot(path=str(out/(action+'.png')),full_page=True)
        call(BASE,'PATCH',f'/api/projects/{pid}/cases/{ids[0]}',{'name':'修改后的当前版本','content':{'url':'/changed'}},token)
        page.goto(BASE+f'/app.html#/runs/{run_ids[0]}')
        page.get_by_text('执行输入快照',exact=True).click()
        expect(page.locator('#run-snapshot')).to_contain_text('快请求原始版本')
        assert '修改后的当前版本' not in page.locator('#run-snapshot').inner_text()
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(out/'mobile-snapshot.png'),full_page=True)
        page.goto('http://127.0.0.1:5173/report/'+str(run_ids[0]))
        page.get_by_label('用户名').fill(user); page.get_by_label('密码').fill(password); page.get_by_role('button',name='登录',exact=True).click()
        expect(page.get_by_role('heading',name='执行详情')).to_be_visible()
        expect(page.get_by_text('已取消',exact=True)).to_be_visible()
        page.get_by_text('执行输入快照',exact=True).click()
        expect(page.get_by_label('执行输入快照内容')).to_contain_text('快请求原始版本')
        assert errors == [], errors
        browser.close()
    print(json.dumps({'browser_checks':'passed','project_id':pid,'cancelled_run':run_ids[0],'timeout_run':run_ids[1],'screenshots':str(out)}))


if __name__=='__main__': main()
