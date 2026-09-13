"""Import and run the topic against the local platform and its bundled target.
Credentials for the platform come from E2E_ADMIN_USERNAME/E2E_ADMIN_PASSWORD.
Leaves evidence and returns nonzero for any failed business assertion.
"""
import json
import os
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv("SHIJIAN_BASE_URL", "http://127.0.0.1:8010").rstrip('/')
TARGET = os.getenv("SHIJIAN_TARGET_URL", "http://127.0.0.1:8013").rstrip('/')


def call(base, method, path, data=None, token=None):
    headers = {'Content-Type':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    request = Request(base+path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response: return response.status, json.loads(response.read() or b'null')
    except HTTPError as error:
        return error.code, error.read().decode('utf-8', errors='replace')


def main():
    if any(urlsplit(url).hostname not in ('127.0.0.1','localhost','::1') for url in (BASE,TARGET)):
        raise SystemExit('This fixture runner only accepts local hosts.')
    code, auth = call(BASE,'POST','/api/auth/login',{'username':os.environ['E2E_ADMIN_USERNAME'],'password':os.environ['E2E_ADMIN_PASSWORD']})
    assert code == 200, f'Platform login failed: {code}'
    token=auth['access_token']
    for actor in ('owner','other'):
        credentials={'username':'qa_topic_'+actor,'password':'Target-demo-only!'}
        code,_=call(TARGET,'POST','/api/login',credentials)
        if code == 401:
            code,_=call(TARGET,'POST','/api/register',{**credentials,'email':actor+'@topic.example'})
        assert code in (200,201), f'Target fixture failed: {code}'
    code, project=call(BASE,'POST','/api/projects',{'name':'权限与状态流转专题','description':'决策表、状态转换、负向与复测证据','url':TARGET},token)
    assert code == 201
    pid=project['id']
    payload=json.loads((ROOT/'examples/permission-state-cases.json').read_text(encoding='utf-8'))
    ids=[]
    for case in payload['cases']:
        code, saved=call(BASE,'POST',f'/api/projects/{pid}/cases',case,token)
        assert code == 201
        ids.append(saved['id'])
    code,run=call(BASE,'POST',f'/api/projects/{pid}/runs',{'case_ids':ids},token)
    assert code == 201
    rid=run['id']
    for _ in range(360):
        _,run=call(BASE,'GET',f'/api/runs/{rid}',token=token)
        if run['status'] not in ('queued','pending','running'): break
        time.sleep(1)
    _,results=call(BASE,'GET',f'/api/runs/{rid}/results',token=token)
    names={c['id']:c['name'] for c in run['cases']}
    evidence={'project_id':pid,'run_id':rid,'status':run['status'],'summary':json.loads(run['summary'] or '{}'),'cases':[]}
    for result in results:
        failed=[{'name':s.get('name'), 'status':s['status'], 'assertions':s.get('assertions',[]), 'status_code':s.get('detail',{}).get('status_code')} for s in result.get('detail',{}).get('steps',[]) if s['status'] != 'pass']
        evidence['cases'].append({'id':result['case_id'],'name':names[result['case_id']],'status':result['status'],'failed_steps':failed})
    out=ROOT/'test-results'/'permission-state'
    out.mkdir(parents=True,exist_ok=True)
    (out/f'run-{rid}.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(evidence,ensure_ascii=True))
    return 0 if run.get('result')=='pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
