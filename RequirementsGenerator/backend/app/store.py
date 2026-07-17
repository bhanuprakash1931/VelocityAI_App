import json, threading
from pathlib import Path
from .config import settings
from .models import Session
_lock=threading.Lock()
def path(sid:str)->Path: return settings.data_dir/'sessions'/f'{sid}.json'
def save(s:Session):
    with _lock: path(s.id).write_text(s.model_dump_json(indent=2),encoding='utf-8')
def load(sid:str)->Session:
    p=path(sid)
    if not p.exists(): raise FileNotFoundError(sid)
    return Session.model_validate_json(p.read_text(encoding='utf-8'))
def list_all():
    out=[]
    for p in sorted((settings.data_dir/'sessions').glob('*.json'),key=lambda x:x.stat().st_mtime,reverse=True):
        try:
            s=Session.model_validate_json(p.read_text(encoding='utf-8')); out.append({'id':s.id,'title':s.title,'versions':len(s.versions)})
        except Exception: pass
    return out
def delete(sid:str): path(sid).unlink(missing_ok=True)
