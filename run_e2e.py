"""One-shot V3 E2E acceptance runner.  It intentionally leaves test data for inspection."""
import json, os, time, uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = os.getenv("SHIJIAN_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TARGET = os.getenv("SHIJIAN_TARGET_URL", "http://127.0.0.1:8003").rstrip("/")
ADMIN_USERNAME = os.getenv("E2E_ADMIN_USERNAME", "e2e_admin")
ADMIN_PASSWORD = os.getenv("E2E_ADMIN_PASSWORD", "E2E-Only-Change-Me-123!")
out = []

def call(method, path, body=None, token=None, raw=False):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    headers = {"Content-Type": "application/json"} if data else {}
    if token: headers["Authorization"] = "Bearer " + token
    try:
        r = urlopen(Request((path if path.startswith("http") else BASE + path), data=data, headers=headers, method=method), timeout=20)
        b = r.read()
        if raw: return r.status, b, dict(r.headers)
        try: b = json.loads(b or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError): b = {"text": b.decode("utf-8", "replace")}
        return r.status, b, dict(r.headers)
    except HTTPError as e:
        b = e.read()
        try: b = json.loads(b)
        except Exception: pass
        return e.code, b, dict(e.headers)
    except URLError as e: return 0, {"error": str(e)}, {}

def check(name, got, expected, detail=""):
    ok = got in expected if isinstance(expected, (tuple, list, set)) else got == expected
    out.append((name, ok, f"HTTP {got}" + (f" — {detail}" if detail else "")))
    return ok

def getid(x): return x.get("id") or x.get("project_id") or x.get("run_id")
def auth(token): return token
def run(pid, cid, tk):
    s, x, _ = call("POST", f"/api/projects/{pid}/runs", {"case_ids":[cid]}, tk); check(f"run {cid}",s,201)
    rid = getid(x)
    for _ in range(30):
        rs, meta, _ = call("GET", f"/api/projects/{pid}/runs/{rid}", token=tk)
        s, x, _ = call("GET", f"/api/projects/{pid}/runs/{rid}/results", token=tk)
        if rs == 200 and meta.get("status") in ("done", "failed"):
            return rid, {"status": meta["status"], "results": x} if isinstance(x, list) else x
        time.sleep(1)
    return rid, x

def main():
    # readiness + authentication
    for name, url in (
        ("backend docs", BASE + "/docs"),
        ("target root", TARGET + "/"),
        ("target OpenAPI", TARGET + "/openapi.json"),
    ):
        s, _, _ = call("GET", url); check(name, s, 200)
    s, x, _ = call("POST", "/api/auth/login", {"username":ADMIN_USERNAME,"password":ADMIN_PASSWORD})
    if s == 401:
        s, x, _ = call("POST", "/api/auth/register", {"username":ADMIN_USERNAME,"password":ADMIN_PASSWORD,"email":"e2e-admin@example.com"})
    check("login",s,(200,201)); tk=x.get("access_token")
    s,x,_=call("GET","/api/auth/me",token=tk); check("auth me",s,200)
    s,_,_=call("PUT","/api/auth/change-password",{"old_password":"wrong","new_password":"T1!"},tk); check("bad password rejected",s,400)
    s,_,_=call("POST","/api/auth/guest-token",{},tk); check("guest token",s,200)
    s,_,_=call("POST",f"{TARGET}/api/login",{"username":"demo","password":"123456"});
    if s == 401:
        s,_,_=call("POST",f"{TARGET}/api/register",{"username":"demo","password":"123456","email":"demo@example.com"})
    check("target demo user",s,(200,201))

    # projects/cases
    project = {"name":"E2E 全功能验收项目","description":"V3 全功能验收","url":TARGET,"auth_config":{"enabled":True,"login_url":TARGET+"/api/login","login_body":{"username":"demo","password":"123456"},"token_json_path":"access_token"}}
    s,x,_=call("POST","/api/projects",project,tk); check("create project",s,201); pid=getid(x)
    s,_,_=call("PUT",f"/api/projects/{pid}",{"name":"E2E V3 验证项目"},tk); check("update project",s,200)
    for name,path in [("search project",f"/api/projects?search=V3&offset=0&limit=10"),("project stats",f"/api/projects/{pid}/stats"),("coverage",f"/api/projects/{pid}/coverage"),("test auth",f"/api/projects/{pid}/test-auth")]:
        s,_,_=call("GET" if name != "test auth" else "POST",path,{} if name=="test auth" else None,tk); check(name,s,200)
    def case(name, content, typ="api"):
        s,x,_=call("POST",f"/api/projects/{pid}/cases",{"name":name,"test_type":typ,"source":"manual","content":content},tk); check("case "+name,s,201); return getid(x)
    api={"method":"GET","url":"/api/tasks","headers":{},"body":None,"assertions":[{"type":"status_code","target":"status_code","operator":"eq","expected":200}]}
    cid=case("GET 笔记列表",api)
    ui=case("打开靶场首页截图",{"url":TARGET,"steps":[{"action":"navigate","url":TARGET},{"action":"screenshot","full_page":True}]},"ui")
    wf={"workflow":[
      {"name":"Login","method":"POST","url":TARGET+"/api/login","body":{"username":"demo","password":"123456"},"headers":{"Content-Type":"application/json"},"assertions":[{"type":"status_code","operator":"eq","expected":200}],"capture":[{"variable":"token","json_path":"access_token"}]},
      {"name":"CreateTask","method":"POST","url":TARGET+"/api/tasks","body":{"title":"E2E task","description":"created by workflow","priority":"medium"},"headers":{"Content-Type":"application/json","Authorization":"Bearer {{token}}"},"assertions":[{"type":"status_code","operator":"eq","expected":201}],"capture":[{"variable":"task_id","json_path":"id"}]},
      {"name":"GetTask","method":"GET","url":TARGET+"/api/tasks/{{task_id}}","headers":{"Authorization":"Bearer {{token}}"},"assertions":[{"type":"status_code","operator":"eq","expected":200}]},
      {"name":"DeleteTask","method":"DELETE","url":TARGET+"/api/tasks/{{task_id}}","headers":{"Authorization":"Bearer {{token}}"},"assertions":[{"type":"status_code","operator":"eq","expected":204}]}]}
    wcid=case("靶场任务全流程",wf)
    schema={"type":"object","properties":{"items":{"type":"array"},"total":{"type":"integer"},"page":{"type":"integer"},"limit":{"type":"integer"}},"required":["items","total","page","limit"]}
    ccid=case("Contract 验证任务列表结构",{"method":"GET","url":"/api/tasks","assertions":api["assertions"]+[{"type":"schema_match","target":schema,"operator":"eq","expected":True}]})
    ecid=case("靶场 error 400",{"method":"GET","url":"/api/error/400","headers":{},"assertions":[{"type":"status_code","target":"status_code","operator":"eq","expected":400}]})
    s,_,_=call("PATCH",f"/api/projects/{pid}/cases/{cid}",{"name":"GET 笔记列表(已更新)"},tk); check("case patch",s,200)
    for p in (f"/api/projects/{pid}/cases?test_type=api",f"/api/projects/{pid}/cases/tags"):
        s,_,_=call("GET",p,token=tk); check("case list/tags",s,200)

    # execution and high-value generated features
    r1,res=run(pid,cid,tk); api_result=(res.get("results") or [{}])[0]; detail=api_result.get("detail",{}); check("API result fields",200 if res.get("status")=="done" and "failure_category" in api_result and all(k in detail for k in ("status_code","response_body","duration_ms")) else 0,200)
    _,res=run(pid,wcid,tk); steps=(res.get("results") or [{}])[0].get("detail",{}).get("steps",[]); check("workflow four steps",len(steps),4)
    _,res=run(pid,ccid,tk); assertions=(res.get("results") or [{}])[0].get("detail",{}).get("assertions",[]); check("contract completed",200 if len(assertions)>1 and assertions[1].get("actual") is True else 0,200)
    s,_,_=call("PATCH",f"/api/projects/{pid}/cases/{ecid}",{"content":{"method":"GET","url":TARGET+"/api/error/400","assertions":[{"type":"status_code","target":"status_code","operator":"eq","expected":400}]}},tk); check("target case patch",s,200)
    run(pid,ecid,tk); run(pid,cid,tk)
    s,_,_=call("GET",f"/api/runs/{r1}/diff",token=tk); check("run diff",s,200)
    s,_,_=call("POST",f"/api/projects/{pid}/ai-plan",{"requirement":"测试靶场登录、创建任务和查询任务","context_doc_ids":[]},tk); check("AI plan",s,200)
    spec={"openapi":"3.0.0","info":{"title":"Tasks","version":"1"},"paths":{"/tasks":{"get":{"responses":{"200":{"description":"OK"}}}}}}
    for mode in ("coverage","fuzz","security","all"):
        s,_,_=call("POST",f"/api/projects/{pid}/schema/parse",{"spec":json.dumps(spec),"mode":mode},tk); check("schema "+mode,s,200)
    # mocks, suite, schedule
    s,_,_=call("GET",f"/api/projects/{pid}/mocks/config",token=tk); check("mock config",s,200)
    s,_,_=call("POST",f"/api/projects/{pid}/mocks/start-recording",{},tk); check("start recording",s,(200,201)); run(pid,cid,tk)
    s,mocks,_=call("GET",f"/api/projects/{pid}/mocks?limit=10",token=tk); check("recorded mock",s,200)
    items=mocks.get("items",mocks if isinstance(mocks,list) else []); mid=getid(items[0]) if items else None
    if mid:
        for meth,p,b,lab,exp in [("GET",f"/api/projects/{pid}/mocks/{mid}",None,"mock detail",200),("PATCH",f"/api/projects/{pid}/mocks/{mid}",{"response_status":200,"response_body":"{\"edited\":true}"},"mock edit",200),("POST",f"/api/projects/{pid}/mocks/{mid}/toggle",None,"mock toggle",200),("POST",f"/api/projects/{pid}/mocks/convert",{"mock_ids":[mid]},"mock convert",201),("DELETE",f"/api/projects/{pid}/mocks/{mid}",None,"mock delete",204)]:
            s,_,_=call(meth,p,b,tk); check(lab,s,exp)
    for meth,p,b,lab,exp in [("POST",f"/api/projects/{pid}/mocks/stop-recording",{},"stop recording",200),("PATCH",f"/api/projects/{pid}/mocks/config",{"mode":"replay"},"mock replay",200)]:
        s,_,_=call(meth,p,b,tk); check(lab,s,exp)
    s,x,_=call("POST",f"/api/projects/{pid}/suites",{"name":"冒烟测试","case_ids":[cid,ecid]},tk); check("suite create",s,201); sid=getid(x)
    for meth,p,b,lab,exp in [("GET",f"/api/projects/{pid}/suites",None,"suite list",200),("GET",f"/api/projects/{pid}/suites/{sid}",None,"suite detail",200),("PUT",f"/api/projects/{pid}/suites/{sid}",{"name":"冒烟测试 v2"},"suite update",200),("POST",f"/api/projects/{pid}/suites/{sid}/run",None,"suite run",200),("DELETE",f"/api/projects/{pid}/suites/{sid}",None,"suite delete",204)]:
        s,_,_=call(meth,p,b,tk); check(lab,s,exp)
    s,x,_=call("POST",f"/api/projects/{pid}/schedules",{"name":"每日回归","cron_expr":"0 6 * * *","case_ids":[cid],"enabled":True},tk); check("schedule create",s,201); sch=getid(x)
    for meth,p,b,lab,exp in [("GET",f"/api/projects/{pid}/schedules",None,"schedule list",200),("POST",f"/api/projects/{pid}/schedules/{sch}/trigger",None,"schedule trigger",200),("PUT",f"/api/projects/{pid}/schedules/{sch}",{"enabled":False},"schedule disable",200),("DELETE",f"/api/projects/{pid}/schedules/{sch}",None,"schedule delete",204)]:
        s,_,_=call(meth,p,b,tk); check(lab,s,exp)
    # miscellaneous endpoint reachability and target hardening
    for meth,p,b,lab,exp in [("GET","/api/api-keys",None,"api keys",200),("POST",f"/api/projects/{pid}/security/generate",{"base_url":TARGET},"security generate",200),("POST",f"/api/projects/{pid}/security/generate",{"base_url":TARGET,"categories":["sql_injection","xss"]},"security filter",200),("GET","/api/user/profile",None,"profile",200),("GET","/api/admin/stats",None,"admin stats",200),("GET","/api/admin/system-stats",None,"system stats",200),("GET","/api/token-stats",None,"token stats",200),("POST","/api/analytics/enter",{"page":"/projects","referrer":""},"analytics enter",201)]:
        s,_,_=call(meth,p,b,tk); check(lab,s,exp)
    for code in (400,401,403,500):
        s,_,_=call("GET",f"{TARGET}/api/error/{code}"); check(f"target error {code}",s,code)
    s,_,_=call("GET",f"{TARGET}/api/slow?delay=1"); check("target slow",s,200)
    s,x,_=call("GET","/api/projects",token=None); check("unauthenticated 401",s,401)
    Path("e2e-results.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    passed=sum(ok for _,ok,_ in out); print(f"E2E: {passed}/{len(out)} passed")
    for n,ok,d in out: print(("PASS" if ok else "FAIL"),n,d)
if __name__ == "__main__": main()
