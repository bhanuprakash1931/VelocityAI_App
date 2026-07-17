import{useEffect,useMemo,useRef,useState}from'react';import{api,BASE}from'./api';
// For direct browser navigations (the Export XLSX <a href>) we need an absolute
// URL. In dev BASE is '' (proxy mode), so we fall back to the network address.
const HREF_BASE=BASE||`${window.location.protocol}//${window.location.hostname}:8000`;
type Col={name:string;data_type:string;editable:boolean};type Table={title:string;columns:Col[];rows:any[][]};type Stage='idle'|'analysis_complete'|'clarification'|'complete';
type LlmConfig={openai_api_key:string;openai_base_url:string;openai_model:string;has_key:boolean;source:string};
export default function App(){const[sid,setSid]=useState('');const[needs,setNeeds]=useState('');const[analysis,setAnalysis]=useState('');const[qs,setQs]=useState<string[]>([]);const[answers,setAnswers]=useState('');const[table,setTable]=useState<Table|null>(null);const[tab,setTab]=useState('analysis');const[busy,setBusy]=useState(false);const[msg,setMsg]=useState('Ready');const[cols,setCols]=useState<string[]|undefined>();const[stage,setStage]=useState<Stage>('idle');const[showSettings,setShowSettings]=useState(false);const[llmCfg,setLlmCfg]=useState<LlmConfig>({openai_api_key:'',openai_base_url:'https://api.openai.com/v1',openai_model:'gpt-4.1-mini',has_key:false,source:'none'});const dark=useMemo(()=>localStorage.theme==='dark',[]);
useEffect(()=>{
  document.documentElement.dataset.theme=dark?'dark':'light';
  api('/api/sessions',{method:'POST'}).then(s=>setSid(s.id)).catch(e=>setMsg('Cannot reach backend — '+e.message));
  api('/api/config').then(cfg=>setLlmCfg(cfg)).catch(()=>{});
},[]);
async function run(path:string,body:any){setBusy(true);setMsg('Working…');try{const r=await api(`/api/sessions/${sid}/${path}`,{method:'POST',body:JSON.stringify(body)});const d=r.data||{};if(d.analysis){setAnalysis(d.analysis)}if(d.clarification_questions?.length){setQs(d.clarification_questions);setStage('clarification')}else if(r.stage==='analysis_complete'){setStage('analysis_complete');setQs([])}if(d.table){setTable(d.table);setTab('table');setStage('complete')}setMsg(r.stage==='clarification'?'Clarification needed':r.stage==='analysis_complete'?'Analysis complete — click Generate':'Complete')}catch(e:any){setMsg('Error: '+(e.message||'Unknown error'))}finally{setBusy(false)}}
async function upload(f:File){const fd=new FormData();fd.append('file',f);setBusy(true);try{const r=await api(`/api/sessions/${sid}/upload`,{method:'POST',body:fd});if(r.template_columns?.length)setCols(r.template_columns);setMsg(`Uploaded ${r.file}`)}catch(e:any){setMsg(e.message)}finally{setBusy(false)}}
function edit(r:number,c:number,v:string){if(!table)return;const rows=table.rows.map((x,i)=>i===r?x.map((y,j)=>j===c?v:y):x);setTable({...table,rows})}
async function save(){if(!table)return;await api(`/api/sessions/${sid}/table`,{method:'PUT',body:JSON.stringify({columns:table.columns,rows:table.rows,source:'user_edit'})});setMsg('Saved as new version')}
async function saveConfig(key:string,url:string,model:string){
  setBusy(true);setMsg('Saving config…');
  try{
    const r=await api('/api/config',{method:'PUT',body:JSON.stringify({openai_api_key:key,openai_base_url:url,openai_model:model})});
    setMsg(r.llm_mode==='configured'?'LLM connected ✓':r.llm_mode==='unreachable'?'Warning: LLM unreachable — '+r.llm_error:'Config saved (demo mode)');
    api('/api/config').then(cfg=>setLlmCfg(cfg)).catch(()=>{});
    setShowSettings(false);
  }catch(e:any){setMsg('Error: '+(e.message||'Unknown'));}finally{setBusy(false);}
}
return <div className="app"><header><div className="header-brand"><img src="/assets/CapgeminiEngineering_Logo_2COL_RGB.svg" alt="Capgemini Engineering" className="brand-logo"/><b>Velocity AI</b><span>Requirements Generator</span></div><div className="header-right"><span className={`llm-badge ${llmCfg.has_key?'llm-on':'llm-off'}`}>{llmCfg.has_key?'● LLM':'○ Demo'}</span><button className="settings-btn" onClick={()=>setShowSettings(v=>!v)} title="LLM Settings">⚙</button><div className="status">{busy?'● ':''}{msg}</div></div></header>
{showSettings&&<SettingsPanel cfg={llmCfg} onSave={saveConfig} onClose={()=>setShowSettings(false)} busy={busy}/>}<main><aside><h2>Stakeholder needs</h2><textarea value={needs}onChange={e=>setNeeds(e.target.value)}placeholder="Describe the product, system, goals, users, constraints, and expected outcomes…"/><label className="upload">Attach documents / Excel template<input type="file"onChange={e=>e.target.files?.[0]&&upload(e.target.files[0])}/></label>{cols&&<small>{cols.length} template columns detected</small>}<button disabled={!sid||!needs.trim()||busy}onClick={()=>run('analyze',{stakeholder_needs:needs,clarification_answers:answers,template_columns:cols,direct_generation:false})}>Analyze</button><button className="primary"disabled={!analysis||busy}onClick={()=>run('generate',{template_columns:cols})}>Generate requirements</button>{stage==='analysis_complete'&&!table&&<p className="hint" style={{color:'var(--accent)'}}>✓ Analysis ready — click Generate requirements.</p>}{qs.length>0&&<section className="clarify"><h3>Clarification</h3>{qs.map(q=><p key={q}>• {q}</p>)}<textarea value={answers}onChange={e=>setAnswers(e.target.value)}placeholder="Provide answers…"/><button className="primary" disabled={!answers.trim()||busy} onClick={()=>run('analyze',{stakeholder_needs:needs,clarification_answers:answers,template_columns:cols,direct_generation:false})}>Submit answers</button></section>}<p className="hint">LLM mode is set by the backend. Without an API key, deterministic demo mode is used.</p></aside><section className="workspace"><nav>{['analysis','table','diagram'].map(x=><button className={tab===x?'active':''}onClick={()=>setTab(x)}key={x}>{x}</button>)}</nav>{tab==='analysis'&&<article><h1>Analysis</h1><div className="prose">{analysis||'Run analysis to see the engineering assessment and clarification questions.'}</div></article>}{tab==='table'&&<article><div className="toolbar"><h1>{table?.title||'Requirements'}</h1><button onClick={save}disabled={!table}>Save version</button><a className="button"href={`${HREF_BASE}/api/sessions/${sid}/export.xlsx`}>Export XLSX</a></div>{table?<div className="tablewrap"><table><thead><tr>{table.columns.map(c=><th key={c.name}>{c.name}</th>)}</tr></thead><tbody>{table.rows.map((r,i)=><tr key={i}>{r.map((v,j)=><td key={j}><input value={v??''}onChange={e=>edit(i,j,e.target.value)}/></td>)}</tr>)}</tbody></table></div>:<p>No requirements generated.</p>}</article>}{tab==='diagram'&&<Diagram sid={sid} hasTable={!!table}/>}</section></main></div>}
function SettingsPanel({cfg,onSave,onClose,busy}:{cfg:LlmConfig;onSave:(k:string,u:string,m:string)=>void;onClose:()=>void;busy:boolean}){
  const[key,setKey]=useState('');
  const[url,setUrl]=useState(cfg.openai_base_url);
  const[model,setModel]=useState(cfg.openai_model);
  const[show,setShow]=useState(false);
  return <div className="settings-overlay" onClick={e=>{if((e.target as HTMLElement).classList.contains('settings-overlay'))onClose()}}>
    <div className="settings-panel">
      <div className="settings-header"><h2>⚙ LLM Configuration</h2><button onClick={onClose}>✕</button></div>
      <p className="settings-status">Current source: <b>{cfg.source}</b> {cfg.has_key&&<span className="llm-on">● Connected</span>}</p>
      <label>API Key
        <div className="key-row">
          <input type={show?'text':'password'} value={key} onChange={e=>setKey(e.target.value)} placeholder={cfg.has_key?'Enter new key to replace current':'Paste your API key here…'}/>
          <button type="button" onClick={()=>setShow(v=>!v)}>{show?'Hide':'Show'}</button>
        </div>
      </label>
      <label>Base URL
        <input type="text" value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://api.openai.com/v1"/>
      </label>
      <label>Model
        <input type="text" value={model} onChange={e=>setModel(e.target.value)} placeholder="gpt-4.1-mini"/>
      </label>
      <div className="settings-footer">
        <button onClick={onClose}>Cancel</button>
        <button className="primary" disabled={busy||(!key.trim()&&!cfg.has_key)} onClick={()=>onSave(key||'__keep__',url,model)}>Save &amp; Test</button>
      </div>
      <p className="hint">Key is saved to the server's <code>.env</code> file and persists across restarts.</p>
    </div>
  </div>
}

function Diagram({sid,hasTable}:{sid:string;hasTable:boolean}){const[code,setCode]=useState('');const[err,setErr]=useState('');const fetched=useRef(false);
function load(){if(!sid||!hasTable)return;fetched.current=true;setErr('');api(`/api/sessions/${sid}/diagram`).then(r=>setCode(r.data?.mermaid||'')).catch(e=>{setErr(e.message);fetched.current=false})}
useEffect(()=>{if(hasTable&&!fetched.current)load()},[sid,hasTable]);
return <article><h1>Traceability diagram</h1>{!hasTable?<p>Generate requirements first, then view the diagram here.</p>:<><p>Mermaid flowchart source — paste into <a href="https://mermaid.live" target="_blank">mermaid.live</a> to render.</p>{err&&<p style={{color:'var(--error,#c00)'}}>Error: {err}</p>}<pre>{code||'Loading…'}</pre><button onClick={load}>Refresh</button></>}</article>}
