from fastapi.testclient import TestClient
from app.main import app
c=TestClient(app)
def test_flow():
    s=c.post('/api/sessions').json(); sid=s['id']
    assert c.post(f'/api/sessions/{sid}/analyze',json={'stakeholder_needs':'A secure web portal'}).status_code==200
    assert c.post(f'/api/sessions/{sid}/generate',json={}).json()['success']
    assert c.get(f'/api/sessions/{sid}/diagram').status_code==200
