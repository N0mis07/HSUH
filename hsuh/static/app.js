const $ = s => document.querySelector(s);
const busyStates = new Set(['queued','running','pending_input']);
let current = null, chats = [], shownRevision = null, shownQuestion = null, pollBusy = false;
const drafts = new Map(); // Memory only. Never localStorage, sessionStorage or IndexedDB.
function el(tag, text, cls) { const n = document.createElement(tag); if(text !== undefined) n.textContent = text; if(cls) n.className = cls; return n; }
function notice(text) { $('#notice').textContent = text; $('#notice').hidden = false; setTimeout(() => $('#notice').hidden = true, 7000); }
async function api(path, method='GET', body) {
  const options = {method, credentials:'same-origin', headers:{'X-HSUH-Request':'1'}};
  if(body !== undefined) { options.headers['Content-Type']='application/json'; options.body=JSON.stringify(body); }
  const r = await fetch('/api/'+path, options);
  if(!r.ok) { let d; try {d=await r.json();} catch {} throw new Error(typeof d?.detail === 'string' ? d.detail : `Request failed (${r.status}). Refresh to renew sign-in if needed.`); }
  return r.json();
}
function panel(name) { $('.workspace').dataset.panel=name; document.querySelectorAll('[data-panel].mobile-nav button, .mobile-nav button').forEach(n => n.setAttribute('aria-pressed',String(n.dataset.panel===name))); }
document.querySelectorAll('.mobile-nav button').forEach(n=>n.onclick=()=>{const next=n.dataset.panel==='inspector' && $('.workspace').dataset.panel==='inspector' ? 'chat' : n.dataset.panel; panel(next);});
function time(ts) { return ts ? new Date(ts*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : 'Not started'; }
function elapsed(t) { const s=Math.max(0,Math.floor(((t.ended_at || Date.now()/1000)-(t.started_at || t.created_at)))); return s<60 ? `${s}s` : `${Math.floor(s/60)}m ${s%60}s`; }
function stateLabel(state) {return ({pending_input:'Needs your answer', queued:'Queued', running:'Running', completed:'Completed', failed:'Failed', cancelled:'Stopped'})[state] || state;}
function renderList() {
  $('#chat-count').textContent=chats.length;
  $('#chat-list').replaceChildren(...chats.map(c=>{
    const b=el('button',undefined,'chat-item'+(c.id===current?' selected':'')); b.dataset.chatId=c.id; b.setAttribute('aria-current',String(c.id===current));
    const dot=el('span',undefined,'state-dot '+(c.task?.state || '')); dot.setAttribute('aria-hidden','true');
    const copy=el('span'); copy.append(el('strong',c.title),el('small',c.task?`${stateLabel(c.task.state)} · ${elapsed(c.task)}`:'Ready when you are'));
    b.append(dot,copy); b.onclick=()=>selectChat(c.id); return b;
  }));
}
async function selectChat(id) {
  if(current) drafts.set(current,$('#message').value);
  current=id; shownRevision=null; shownQuestion=null; $('#message').value=drafts.get(id)||''; renderList(); panel('chat');
  await updateChat();
}
async function newChat() {const c=await api('chats','POST',{}); chats=await api('chats'); await selectChat(c.id); $('#message').focus();}
$('#new-chat').onclick=()=>newChat().catch(e=>notice(e.message));
$('#delete-chat').onclick=async()=>{if(!current || !confirm('Delete this HSUH conversation and stop its active turn?'))return; try {await api('chats/'+current,'DELETE'); drafts.delete(current); current=null; shownRevision=null; chats=await api('chats'); if(chats.length)await selectChat(chats[0].id); else await newChat();}catch(e){notice(e.message);}};
function messageNode(m) {
  const a=el('article',undefined,'message '+m.role); a.id='message-'+m.id;
  const meta=el('div',undefined,'message-meta'); meta.append(el('strong',m.role==='assistant'?'Hermes':'You'),el('span',time(m.at)));
  const content=el('div',undefined,'message-body');
  // Plain text and fenced code only; untrusted model HTML is never interpreted.
  m.content.split(/```[^\n]*\n([\s\S]*?)```/g).forEach((text,index)=>content.append(el(index%2?'pre':'span',text)));
  a.append(meta,content); return a;
}
function taskNode(t) {
  const details=el('details',undefined,'task-card'); details.dataset.state=t.state; details.open=busyStates.has(t.state)||t.state==='failed';
  const summary=el('summary'); summary.append(el('span',t.label),el('span',stateLabel(t.state),'task-state'));
  details.append(summary,el('p',t.summary),el('p',`Started ${time(t.started_at)} · ${elapsed(t)} elapsed`,'task-time'));
  if(t.result_message_id){const a=el('a','View response ↑'); a.href='#message-'+t.result_message_id; details.append(a);}
  return details;
}
function questionNode(question) {
  const f=el('form',undefined,'question-card'); f.append(el('h3','Hermes needs your input'),el('p','Answers are sent to the model. Never enter passwords, login codes or payment information here.','fine'));
  for(const q of question.questions){
    const fieldset=el('fieldset'), legend=el('legend',q.question); fieldset.append(legend);
    for(const choice of q.choices||[]){const label=el('label',undefined,'choice');const input=el('input'); input.type=q.multi_select?'checkbox':'radio';input.name=q.qid; input.value=choice;label.append(input,el('span',choice));fieldset.append(label);}
    const other=el('label',q.choices?.length?'Other / your own answer':'Your answer','fine');const input=el('input');input.type='text';input.name=q.qid+'-other';input.maxLength=2000;input.autocomplete='off';input.placeholder='Type a non-sensitive answer';other.append(input);fieldset.append(other);f.append(fieldset);
  }
  const send=el('button','Send answers','primary');send.type='submit';f.append(send);
  f.onsubmit=async e=>{e.preventDefault();const answers={}; for(const q of question.questions){const other=f.elements.namedItem(q.qid+'-other').value.trim();const selected=[...f.querySelectorAll('input')].filter(n=>n.name===q.qid && n.checked).map(n=>n.value);answers[q.qid]=other || (q.multi_select?selected:selected[0]) || null;if(!answers[q.qid] || Array.isArray(answers[q.qid])&&!answers[q.qid].length){notice('Answer each question before submitting.');return;}}send.disabled=true;try{await api('chats/'+current+'/answers','POST',{question_id:question.id,answers});await updateChat();}catch(e){notice(e.message);send.disabled=false;}};
  return f;
}
async function updateChat() {
  if(!current)return;
  const selected=current;
  const c=await api('chats/'+selected);if(current!==selected)return;
  $('#chat-title').textContent=c.title;
  const busy=c.task && busyStates.has(c.task.state);
  $('#send').disabled=!!busy; $('#stop').hidden=!busy;
  $('#message').disabled=!!busy;
  $('#composer-hint').textContent=c.task?.state==='pending_input'?'Answer the question card above':busy?'This turn continues when you switch chats':'Enter to send · Shift + Enter for a new line';
  $('#welcome').hidden=c.messages.length>0;
  if(shownRevision!==c.revision){
    const scroller=$('#chat-scroll');const nearEnd=scroller.scrollHeight-scroller.scrollTop-scroller.clientHeight<130;
    $('#messages').replaceChildren(...c.messages.map(messageNode));
    $('#task-feed').replaceChildren(...[...c.tasks].reverse().map(taskNode));
    if(c.question?.id!==shownQuestion){$('#questions').replaceChildren(...(c.question?[questionNode(c.question)]:[]));shownQuestion=c.question?.id;}
    if(nearEnd)scroller.scrollTop=scroller.scrollHeight;
    shownRevision=c.revision;
  } else {document.querySelectorAll('.task-card .task-time').forEach((n,i)=>{const t=[...c.tasks].reverse()[i];if(t)n.textContent=`Started ${time(t.started_at)} · ${elapsed(t)} elapsed`;});}
}
const draftVersions = new Map();
$('#message').oninput=()=>{if(current){drafts.set(current,$('#message').value);draftVersions.set(current,(draftVersions.get(current)||0)+1);}};
$('#composer').onsubmit=async e=>{
  e.preventDefault();
  const raw=$('#message').value, text=raw.trim();
  if(!text)return;
  $('#send').disabled=true;
  let submitted=current;
  try{
    if(!submitted){await newChat();submitted=current;}
    const version=draftVersions.get(submitted)||0;
    drafts.set(submitted,raw);
    await api('chats/'+submitted+'/messages','POST',{message:text});
    // A late response owns only the unchanged draft it actually submitted.
    if((draftVersions.get(submitted)||0)===version && drafts.get(submitted)===raw){
      drafts.delete(submitted);
      if(current===submitted && $('#message').value===raw)$('#message').value='';
    }
    await updateChat();
  }catch(e){notice(e.message);if(current===submitted)$('#send').disabled=false;}
};
$('#message').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(!$('#send').disabled)$('#composer').requestSubmit();}};
$('#stop').onclick=async()=>{try{await api('chats/'+current+'/stop','POST',{});await updateChat();}catch(e){notice(e.message);}};
const gib=n=>(n/1024**3).toFixed(2)+' GiB';
async function telemetry(){
  try{const d=await api('telemetry'),m=d.memory,p=m.used/m.total*100;$('#ram-percent').textContent=p.toFixed(1)+'%';$('#ram-number').textContent=gib(m.used)+' / '+gib(m.total);$('#ram-meter').value=p;$('#ram-available').textContent=gib(m.available);$('#swap').textContent=gib(d.swap.used)+' / '+gib(d.swap.total);
  $('#processes').replaceChildren(...d.processes.map(p=>{const row=el('div',undefined,'process-row');const name=el('span',p.name);name.append(el('small',String(p.pid)));row.append(name,el('span',(p.rss/1024**2).toFixed(0)+' MiB'));return row;}));$('#sample-time').textContent=`Sample ${time(d.sampled_at)} · ${d.scope}`;
  }catch{ $('#sample-time').textContent='Live telemetry unavailable · values above may be stale'; }
}
async function quota(){
  $('#refresh-quota').disabled=true;
  try{const d=await api('quota'),n=d.native,box=$('#quota');box.replaceChildren(el('p',n.available?`${n.provider} · ${n.plan}`:'Provider quota unavailable','fine'));
    for(const w of n.windows||[]){const row=el('div',undefined,'quota-window'),pair=el('div',undefined,'metric-pair');pair.append(el('span',w.label),el('strong',`${w.used_percent}% used`));const bar=el('progress');bar.max=100;bar.value=w.used_percent;bar.setAttribute('aria-label',w.label+' quota used');row.append(pair,bar);if(w.resets_at)row.append(el('p','Resets '+new Date(w.resets_at).toLocaleString(),'fine'));box.append(row);}
    if(n.note)box.append(el('p',n.note,'fine'));
    box.append(el('p',`Source: Hermes ${n.source}. Updated ${n.fetched_at?new Date(n.fetched_at).toLocaleString():'unavailable'}.`,'quota-caption'));
    box.append(el('h3','Aperture budgets'),el('p',d.aperture.note,'fine'));
    if(d.aperture.dashboard){const a=el('a','Open authoritative Aperture quotas ↗','quota-link');a.href=d.aperture.dashboard;a.target='_blank';a.rel='noopener noreferrer';box.append(a);}
    box.append(el('p',`${d.note} Checked ${new Date(d.checked_at).toLocaleString()}. Refreshes at most once a minute.`,'quota-caption'));
  }catch{$('#quota').replaceChildren(el('p','Quota sources unavailable. No balance estimated.','fine'));}finally{$('#refresh-quota').disabled=false;}
}
$('#refresh-quota').onclick=quota;
async function tick(){if(pollBusy||document.hidden)return;pollBusy=true;try{chats=await api('chats');renderList();await updateChat();const s=await api('status');$('#connection').textContent=`Connected · ${s.active} active`;$('#runtime').textContent=s.model?`${s.model.model} · ${s.model.provider} · reasoning ${s.model.reasoning_effort}. ${s.access}.`: `Model from native configuration on first turn. ${s.access}.`;}catch(e){$('#connection').textContent='Disconnected · refresh to sign in';}finally{pollBusy=false;}}
let installPrompt;
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e;$('#install').hidden=false;});
$('#install').onclick=async()=>{if(installPrompt){await installPrompt.prompt();installPrompt=null;$('#install').hidden=true;}};
if('serviceWorker'in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
try{chats=await api('chats');if(chats.length)await selectChat(chats[0].id);else await newChat();await tick();telemetry();quota();}catch(e){notice(e.message);}
setInterval(tick,1800);setInterval(telemetry,7000);setInterval(quota,65000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden){tick();telemetry();}});
