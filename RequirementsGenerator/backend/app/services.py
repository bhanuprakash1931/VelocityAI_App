import json, re
from datetime import datetime, timezone
from typing import Any
import httpx
from .config import settings, get_api_key, get_base_url, get_model
from .models import Column, RequirementTable, Version, Session
DEFAULT_COLUMNS=["Req ID","Category","Requirement Statement","Rationale / Source","Acceptance Criteria","Verification Method","Owner","Priority","Status","Comments"]
def _json(text:str):
    text=re.sub(r'^```(?:json)?|```$','',text.strip(),flags=re.M).strip(); a=text.find('{'); b=text.rfind('}')
    return json.loads(text[a:b+1])
async def llm_json(system:str,user:str,timeout:int=90)->dict|None:
    api_key=get_api_key()
    if not api_key:
        return None
    headers={'Authorization':f'Bearer {api_key}','Content-Type':'application/json'}
    payload={'model':get_model(),'temperature':0.2,'messages':[{'role':'system','content':system},{'role':'user','content':user}]}
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r=await c.post(get_base_url().rstrip('/')+'/chat/completions',headers=headers,json=payload)
            r.raise_for_status()
            return _json(r.json()['choices'][0]['message']['content'])
    except httpx.ConnectError:
        return None
    except httpx.TimeoutException:
        import logging; logging.getLogger('services').warning('llm_json timed out after %ds', timeout)
        return None
    except httpx.HTTPStatusError as e:
        import logging; logging.getLogger('services').warning('OpenAI HTTP error %s: %s', e.response.status_code, e.response.text[:200])
        return None
    except Exception:
        import logging; logging.getLogger('services').exception('llm_json unexpected error')
        return None
def demo_analysis(needs:str)->str:
    return (f"The requested system is analyzed from functional, performance, safety, reliability, usability, interface, manufacturing, and verification perspectives. "
            f"Primary stakeholder intent: {needs.strip()}. Ambiguous targets should be confirmed before release; every requirement must be measurable, traceable, and independently verifiable.")
def clarifications(needs:str)->list[str]:
    q=[]; low=needs.lower()
    if not re.search(r'\d',needs): q.append('What measurable performance targets and tolerances should apply?')
    if not any(x in low for x in ['standard','iec','iso','ul','regulation']): q.append('Which regulatory, safety, and industry standards apply?')
    if not any(x in low for x in ['environment','temperature','indoor','outdoor']): q.append('What operating and environmental conditions must be supported?')
    return q[:3]
def demo_table(needs:str, columns:list[str]|None=None)->RequirementTable:
    names=columns or DEFAULT_COLUMNS; cols=[Column(name=x) for x in names]
    # DFMEA demo table
    if _is_dfmea(names):
        product=needs.strip()[:60]
        dfmea_base=[
            ('Battery pack','Battery pack SHALL prevent thermal runaway','Cell overcharge / BMS failure','Fire, injury, product recall','9','Safety Critical','BMS IC failure; welded FET','3','Dual-threshold protection; BMS firmware validation','EOL charge/discharge cycle test','3','81','Add independent hardware cutoff; increase BMS test coverage','Electrical / Safety','TBD','Open'),
            ('Motor / Fan assembly','Motor SHALL maintain suction under nominal debris load','Motor stall due to blockage','Loss of suction; motor overheating; shutdown','7','Performance Critical','Debris bypass inlet grille; filter saturated','4','Inlet grille mesh 4 mm max; filter capacity analysis','Stall detection in firmware; EOL suction test','4','112','Reduce grille aperture; add thermal cutoff','Mechanical / Software','TBD','Open'),
            ('Filter assembly','Filter SHALL trap >= 99% of particles >= 0.3 µm','Filter bypass / seal failure','Dust emission; user exposure; EU standard non-compliance','7','Regulatory','Incorrect filter installation; seal deformation','3','Keyed filter housing; seal torque specification','Filtration efficiency test per EN 60312','3','63','Redesign filter latch; add installation indicator','Systems / Manufacturing','TBD','Open'),
            ('Charging base / interface','Charging system SHALL restore full charge within 4 h','Overcharge / wrong charge profile','Battery damage; safety event; reduced battery life','8','Safety Critical','Charger IC failure; firmware bug','2','Certified charger IC; charge profile validation','EOL charge current / voltage measurement','3','48','Add secondary hardware overvoltage cutoff','Power Electronics','TBD','Open'),
            ('Housing / structural shell','Housing SHALL withstand 1 m drop onto hard floor without cracking','Housing crack on drop','Loss of structural integrity; user injury; ingress of debris','6','Reliability','Wall thickness insufficient; material brittleness','3','FEA drop simulation; material selection review','1 m drop test on all faces (6 faces)','3','54','Increase wall thickness at critical joints; add rib structure','Mechanical','TBD','Open'),
        ]
        # Map each DFMEA base tuple to requested columns via role matching
        dfmea_default=['Item / Component','Function / Requirement','Potential Failure Mode',
                       'Potential Effects of Failure','Severity (S)','Classification / Special Characteristic',
                       'Potential Causes / Mechanisms','Occurrence (O)','Prevention Controls','Detection Controls',
                       'Detection (D)','RPN','Recommended Action','Owner','Target Date','Action Result']
        d_canon={n.lower():i for i,n in enumerate(dfmea_default)}
        rows=[]
        for raw in dfmea_base:
            row=[raw[d_canon[n.lower()]] if n.lower() in d_canon else 'TBD' for n in names]
            rows.append(row)
        return RequirementTable(title='DFMEA — '+product,columns=cols,rows=rows)
    # Standard requirements demo table
    base=[
      ('REQ-001','Functional',f'The system shall satisfy the stakeholder need: {needs.strip()}.','Stakeholder need','Demonstrated in an approved end-to-end scenario','Test','Systems','High','Draft',''),
      ('REQ-002','Performance','The system shall complete each primary operation within 2 seconds under nominal load.','Derived performance target','95th percentile response time shall be <= 2 seconds','Test','Software','High','Draft','Confirm load profile'),
      ('REQ-003','Reliability','The system shall recover from a transient processing failure without loss of committed data.','Reliability analysis','Recovery succeeds and committed records remain intact','Test','Software','High','Draft',''),
      ('REQ-004','Security','The system shall restrict protected operations to authenticated and authorized users.','Security baseline','All protected API tests reject unauthenticated and unauthorized access','Inspection/Test','Security','Critical','Draft',''),
      ('REQ-005','Usability','The user interface shall provide a visible outcome or error message for every submitted operation.','UX guideline','100% of documented actions show success, progress, or actionable error state','Inspection','UX','Medium','Draft',''),
      ('REQ-006','Maintainability','The system shall record timestamped diagnostic events for failed backend operations.','Operations need','Logs include timestamp, operation, correlation identifier, and sanitized error','Inspection','DevOps','Medium','Draft','')]
    canon={n.lower():i for i,n in enumerate(DEFAULT_COLUMNS)}; rows=[]
    for raw in base:
        rows.append([raw[canon[n.lower()]] if n.lower() in canon else '' for n in names])
    return RequirementTable(columns=cols,rows=rows)
async def analyze(needs:str,context:str=''):
    system='Return JSON only with keys analysis (string) and clarification_questions (array of strings). Analyze stakeholder needs for requirements engineering. Ask at most 3 essential questions.'
    result=await llm_json(system, needs + chr(10) + 'Additional context:' + chr(10) + context)
    if result is None:
        return (demo_analysis(needs), clarifications(needs))
    analysis=result.get('analysis') or ''
    questions=result.get('clarification_questions') or []
    if not isinstance(questions, list): questions=[]
    return (analysis or demo_analysis(needs), questions)
def _col_role(name:str)->str:
    """Map a column name to its semantic role for prompt guidance."""
    n=re.sub(r'[^a-z0-9 ]+','',name.lower()).strip()
    if any(x in n for x in ['req id','requirement id','serial','s no','sno','id','no']): return 'unique requirement ID e.g. REQ-001'
    if any(x in n for x in ['category','type','area','section','group']): return 'requirement category e.g. Functional / Performance / Safety / Interface / Reliability'
    if any(x in n for x in ['description','requirement statement','shall statement','requirement','function requirement','check item']): return 'measurable SHALL requirement statement'
    if any(x in n for x in ['source','rationale','origin','reference']): return 'source or rationale e.g. Stakeholder need / Standard / Derived'
    if any(x in n for x in ['verification','method','test method','i a t d']): return 'verification method: Inspection / Analysis / Test / Demonstration'
    if any(x in n for x in ['acceptance','criteria','target','value']): return 'measurable acceptance criteria with units and limits'
    if any(x in n for x in ['owner','responsibility','responsible']): return 'responsible team or role e.g. Systems / Hardware / Software'
    if any(x in n for x in ['priority']): return 'priority: Critical / High / Medium / Low'
    if any(x in n for x in ['status','result','answer','pass fail','yes no']): return 'status: Draft / Open / Verified / TBD'
    if any(x in n for x in ['comment','remarks','notes','reviewer']): return 'reviewer notes or open questions'
    # DFMEA columns
    if any(x in n for x in ['item','component']): return 'system item or component name'
    if 'failure mode' in n: return 'potential failure mode description'
    if 'failure effect' in n or 'effects of failure' in n: return 'potential effect of failure on system/user'
    if n in {'severity','severity s','s'}: return 'severity rating 1-10'
    if 'classification' in n or 'special characteristic' in n: return 'safety/special characteristic classification'
    if 'cause' in n or 'mechanism' in n: return 'potential cause or mechanism of failure'
    if n in {'occurrence','occurrence o','o'}: return 'occurrence rating 1-10'
    if 'prevention' in n: return 'current prevention control'
    if 'detection control' in n: return 'current detection control'
    if n in {'detection','detection d','d'}: return 'detection rating 1-10'
    if n=='rpn': return 'Risk Priority Number = Severity x Occurrence x Detection'
    if 'recommended action' in n: return 'recommended corrective action'
    if n in {'owner','responsibility'}: return 'action owner / responsible engineer'
    if 'target date' in n or 'due date' in n: return 'target completion date'
    if 'action result' in n or 'actions taken' in n: return 'result of action taken'
    return f'value for column "{name}"'

def _is_dfmea(names:list[str])->bool:
    """Return True if the column set looks like a DFMEA/FMEA template."""
    n=' '.join(re.sub(r'[^a-z0-9 ]+','',c.lower()) for c in names)
    hits=sum(1 for kw in ['failure mode','failure effect','effects of failure','severity','occurrence','detection','rpn','prevention','cause','mechanism'] if kw in n)
    return hits>=3

async def generate(needs:str,analysis_text:str,columns:list[str]|None=None):
    names=columns or DEFAULT_COLUMNS
    col_guidance='\n'.join(f'  col[{i}] "{n}" -> {_col_role(n)}' for i,n in enumerate(names))
    width=len(names)

    # Truncate analysis to keep total prompt size manageable
    analysis_short=analysis_text[:2000] if analysis_text else ''
    needs_short=needs[:800] if needs else ''

    if _is_dfmea(names):
        system=(
            'You are a DFMEA engineer. Return ONLY valid JSON - no markdown, no prose.\n'
            'Shape: {"title": string, "rows": [[val0, val1, ...]]}\n'
            'Rules: 12-16 rows. Each row = one failure mode. EXACTLY '+str(width)+' elements per row.\n'
            'All cells non-empty. Severity/Occurrence/Detection = integer 1-10. RPN = S*O*D.\n'
            'Subsystems to cover: battery, motor, suction, filter, housing, charger, UI, seal.\n'
            'Owner = engineering role. Do NOT repeat column names as values.\n'
            'Columns: '+', '.join(f'[{i}]{n}' for i,n in enumerate(names))
        )
        user=json.dumps({'product':needs_short,'context':analysis_short})
    else:
        system=(
            'You are a requirements engineer. Return ONLY valid JSON - no markdown, no prose.\n'
            'Shape: {"title": string, "rows": [[val0, val1, ...]]}\n'
            'Rules: 15-20 rows. EXACTLY '+str(width)+' elements per row. No header row in rows.\n'
            'Write measurable SHALL statements with units. Cover functional/performance/safety/interface/reliability.\n'
            'Column guidance:\n'+col_guidance
        )
        user=json.dumps({'stakeholder_needs':needs_short,'analysis':analysis_short,'columns':names})
    import logging; _log=logging.getLogger('services')
    result=await llm_json(system,user,timeout=120)
    if not result:
        _log.warning('generate: llm_json returned None, using demo_table (is_dfmea=%s, cols=%d)', _is_dfmea(names), width)
        return demo_table(needs,names)
    cols=[Column(name=n) for n in names]
    raw_rows=result.get('rows') or []
    _log.info('generate: llm returned %d rows for %d columns', len(raw_rows), width)
    if not isinstance(raw_rows,list) or not raw_rows:
        _log.warning('generate: no valid rows in LLM response, using demo_table')
        return demo_table(needs,names)
    rows=[]
    for r in raw_rows:
        if not isinstance(r,(list,tuple)): continue
        padded=(list(r)+['']*width)[:width]
        if [str(x).strip().lower() for x in padded]==[n.lower() for n in names]: continue
        if not any(str(x).strip() for x in padded): continue
        rows.append(padded)
    if not rows:
        _log.warning('generate: all rows were empty/header after filtering, using demo_table')
        return demo_table(needs,names)
    _log.info('generate: returning %d rows with %d columns', len(rows), width)
    return RequirementTable(title=result.get('title','Requirements Specification'),columns=cols,rows=rows)
def add_version(s:Session,table:RequirementTable,source:str):
    v=Version(version=f'v{len(s.versions)+1}',timestamp=datetime.now(timezone.utc).isoformat(),source=source,table=table,analysis=s.analysis,stakeholder_needs=s.stakeholder_needs)
    s.versions.append(v); s.active_version=len(s.versions)-1; return v
