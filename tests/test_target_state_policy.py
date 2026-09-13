"""Bundled target regression, with its own temporary SQLite database."""
import importlib.util
from pathlib import Path
import pytest
import tempfile
from fastapi.testclient import TestClient


@pytest.fixture
def target_db_path():
    parent = Path(__file__).resolve().parents[1] / 'test-results'
    parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='target-state-', dir=parent) as directory:
        yield Path(directory)


@pytest.mark.parametrize('actor,state,expected', [('owner','done',400),('other','doing',403),('owner','doing',200),('admin','doing',200)])
def test_status_transition_and_ownership(actor,state,expected,target_db_path,monkeypatch):
    monkeypatch.setenv('TARGET_DATABASE_PATH',str(target_db_path/'target.db'))
    spec=importlib.util.spec_from_file_location('target_state_fixture',Path(__file__).resolve().parents[1]/'target-system'/'main.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with TestClient(module.app) as client:
        tokens={}
        for who in ('owner','other','admin'):
            password='admin123' if who=='admin' else 'test-only-password'
            if who!='admin':
                assert client.post('/api/register',json={'username':who,'password':password,'email':who+'@example.com'}).status_code==201
            response=client.post('/api/login',json={'username':who,'password':password})
            assert response.status_code==200
            tokens[who]={'Authorization':'Bearer '+response.json()['access_token']}
        created=client.post('/api/tasks',json={'title':'State test'},headers=tokens['owner']).json()
        response=client.put(f"/api/tasks/{created['id']}/status",json={'status':state},headers=tokens[actor])
        assert response.status_code==expected, response.text
        actual=client.get(f"/api/tasks/{created['id']}",headers=tokens['owner']).json()['status']
        assert actual == (state if expected==200 else 'todo')
