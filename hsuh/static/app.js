const $ = s => document.querySelector(s);
const busyStates = new Set(['queued','running','pending_input','waiting_for_approval','stopping','reconnecting']);
let current = null, chats = [], shownRevision = null, shownQuestion = null, pollBusy = false;
let currentTask=null, currentNative=false, shownApproval=null, controlData=null, controlBusy=false, workTab='tasks';
let creatingChat=false,currentReady=false;
const submissions=new Map();
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
function syncNavigation() { const w=$('.workspace'); document.querySelectorAll('button[data-view], .mobile-nav button[data-panel]').forEach(n=>n.setAttribute('aria-pressed',String(n.dataset.panel?w.dataset.view==='chat'&&w.dataset.panel===n.dataset.panel:n.dataset.view===w.dataset.view&&(w.dataset.view!=='chat'||w.dataset.panel==='chat')))); }
function panel(name) { $('.workspace').dataset.panel=name; syncNavigation(); }
function view(name) { $('.workspace').dataset.view=name; if(name==='chat')panel('chat');if(name==='work')controls(); syncNavigation(); }
document.querySelectorAll('button[data-view]').forEach(n=>n.onclick=()=>view(n.dataset.view));
document.querySelectorAll('.mobile-nav button[data-panel]').forEach(n=>n.onclick=()=>{view('chat');panel(n.dataset.panel);});
document.querySelectorAll('[data-prompt]').forEach(n=>n.onclick=()=>{view('chat');const input=$('#message');if(input.disabled)return;input.value=n.dataset.prompt;input.oninput();input.focus();});
const statsCache=new Map();
const statsEvent=(name,data)=>{statsCache.set(name,data);if(typeof CustomEvent==='function')window.dispatchEvent(new CustomEvent('hsuh:'+name,{detail:data}));};
window.addEventListener('hsuh:ui-ready',()=>{for(const [name,data] of statsCache)statsEvent(name,data);});
function time(ts) { return ts ? new Date(ts*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : 'Not started'; }
function elapsed(t) { const s=t.elapsed_seconds??Math.max(0,Math.floor(((t.ended_at || Date.now()/1000)-(t.started_at || t.created_at)))); return s<60 ? `${s}s` : `${Math.floor(s/60)}m ${s%60}s`; }
function stateLabel(state) {return ({pending_input:'Needs your answer', waiting_for_approval:'Approval needed', stopping:'Stopping',reconnecting:'Reconnecting', interrupted:'Interrupted',queued:'Queued', running:'Running', completed:'Completed', failed:'Failed', cancelled:'Stopped'})[state] || state;}
function renderList() {
  $('#chat-count').textContent=chats.length;
  $('#chat-list').replaceChildren(...chats.map(c=>{
    const b=el('button',undefined,'chat-item'+(c.id===current?' selected':'')); b.dataset.chatId=c.id; b.setAttribute('aria-current',String(c.id===current));
    const dot=el('span',undefined,'state-dot '+(c.task?.state || '')); dot.setAttribute('aria-hidden','true');
    const copy=el('span'); copy.append(el('strong',c.title));if(c.task&&busyStates.has(c.task.state))copy.append(el('small',stateLabel(c.task.state)));
    b.append(dot,copy); b.onclick=()=>selectChat(c.id); return b;
  }));
}
async function selectChat(id,show=true) {
  if(current) drafts.set(current,$('#message').value);
  current=id;currentTask=null;currentNative=false;currentReady=false;$('#send').disabled=true;$('#message').disabled=true;
  shownRevision=null; shownQuestion=null; $('#message').value=drafts.get(id)||''; renderList(); if(show)view('chat');
  await updateChat();
}
async function newChat(show=true) {if(creatingChat)return;creatingChat=true;$('#send').disabled=true;$('#message').disabled=true;try{const c=await api('chats','POST',{}); chats=await api('chats'); await selectChat(c.id,show);}finally{creatingChat=false;await updateChat();}if(show)$('#message').focus();}
$('#new-chat').onclick=()=>newChat().catch(e=>notice(e.message));
$('#delete-chat').onclick=async()=>{if(!current || !confirm(currentNative?'Remove this conversation from HSUH? Its native Hermes transcript is retained. Active tasks must be stopped first.':'Delete this HSUH conversation and stop its active turn?'))return; try {await api('chats/'+current,'DELETE'); drafts.delete(current); current=null; shownRevision=null; chats=await api('chats'); if(chats.length)await selectChat(chats[0].id); else await newChat();}catch(e){notice(e.message);}};
function messageNode(m) {
  const a=el('article',undefined,'message '+m.role); a.id='message-'+m.id;
  const meta=el('div',undefined,'message-meta');
  if(m.role==='assistant'){const avatar=el('img',undefined,'message-avatar');avatar.src='/assets/mascot.svg';avatar.alt='';avatar.width=32;avatar.height=32;meta.append(avatar);}
  meta.append(el('strong',m.role==='assistant'?'Hermes':m.kind==='guidance'?'You · guidance':'You'),el('span',time(m.at)));
  const content=el('div',undefined,'message-body');
  // Model text never becomes HTML. OpenUI uses a fixed, locally bundled component library.
  const pattern=/```([^\n]*)\n([\s\S]*?)```/g;let cursor=0;
  for(const match of m.content.matchAll(pattern)){
    content.append(el('span',m.content.slice(cursor,match.index)));
    if(m.role==='assistant' && match[1].trim().toLowerCase()==='openui' && window.HSUHOpenUI){
      const target=el('div');content.append(target);window.HSUHOpenUI.render(target,match[2]);
    }else content.append(el('pre',match[2]));
    cursor=match.index+match[0].length;
  }
  content.append(el('span',m.content.slice(cursor)));
  a.append(meta,content); return a;
}
function taskNode(t) {
  const details=el('details',undefined,'task-card'); details.dataset.state=t.state; details.open=busyStates.has(t.state)||t.state==='failed';
  const summary=el('summary'); summary.append(el('span',t.label),el('span',stateLabel(t.state),'task-state'));
  details.append(summary,el('p',t.summary),el('p',`Started ${time(t.started_at)} · ${elapsed(t)} elapsed`,'task-time'));
  if(t.result_message_id){const a=el('a','View response ↑'); a.href='#message-'+t.result_message_id; details.append(a);}
  if(t.run_id)details.append(el('p',t.run_id,'fine mono'));
  if(t.usage)details.append(el('p',`${(t.usage.input_tokens||0).toLocaleString()} input · ${(t.usage.output_tokens||0).toLocaleString()} output tokens`,'fine'));
  if(t.events?.length){const feed=el('ol',undefined,'tool-feed');for(const event of t.events){const item=el('li');item.append(el('time',time(event.at)),el('span',event.tool?`${event.tool} · ${event.event==='tool.started'?'started':event.error?'failed':'completed'}${event.duration!=null?' · '+event.duration+'s':''}`:event.text||event.event));feed.append(item);}details.append(feed);}
  return details;
}
function approvalNode(t,chatId){
  const a=t.approval,f=el('section',undefined,'approval-card');f.setAttribute('aria-label','Native approval request');
  f.append(el('h3','Hermes needs your permission'),el('p',a.description||'Hermes paused this task for approval. Review the operation before allowing it.'),el('pre',a.command||'Native operation'),el('p','This decision applies to the exact pending request.','fine'));
  const actions=el('div',undefined,'control-actions');
  for(const choice of a.choices){const button=el('button',({once:'Allow once',session:'Allow for this task',deny:'Deny'})[choice],choice==='deny'?'quiet':'primary');button.type='button';button.onclick=async()=>{for(const n of actions.children)n.disabled=true;try{await api('chats/'+chatId+'/approval','POST',{task_id:t.id,request_id:a.request_id,choice});await tick();await controls();}catch(e){notice(e.message);for(const n of actions.children)n.disabled=false;}};actions.append(button);}
  f.append(actions);return f;
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
  currentTask=c.task;currentNative=!!c.native;currentReady=true;
  $('#chat-title').textContent=c.title;
  const busy=c.task && busyStates.has(c.task.state);
  const steering=busy&&c.native&&c.task.state==='running';
  $('#send').disabled=creatingChat||!!busy&&!steering; $('#stop').hidden=!busy;$('#stop').disabled=c.task?.state==='stopping'||!c.task?.run_id&&c.native;
  $('#send').textContent=steering?'Guide':'Send';
  $('#message').disabled=creatingChat||!!busy&&!steering;
  $('#composer-hint').textContent=c.task?.state==='waiting_for_approval'?'Your permission is needed above':c.task?.state==='pending_input'?'Hermes has a question for you above':steering?'Send a little guidance while Hermes works':busy?'Hermes is working on it…':'Enter to send · Shift + Enter for a new line';
  $('#retention-note').textContent=c.native?'Your tasks keep going when you close this tab.':'Chats are kept until you delete them or the server restarts.';
  $('#delete-chat').textContent=c.native?'Remove chat':'Delete chat';
  const taskState=c.task?.state;
  $('#buddy').dataset.state=taskState==='waiting_for_approval'||taskState==='pending_input'?'waiting':busy?'working':taskState==='failed'||taskState==='interrupted'?'error':'ready';
  $('#buddy-status').textContent=taskState==='waiting_for_approval'?'Needs your permission':taskState==='pending_input'?'Has a question for you':taskState==='stopping'?'Wrapping up…':taskState==='reconnecting'?'Reconnecting…':busy?'Working on it…':taskState==='failed'?'Something needs a look':taskState==='interrupted'?'Task interrupted':'Ready when you are';
  $('#task-history').hidden=!c.tasks.length;
  $('#task-history-label').textContent=busy?'Working · See activity':taskState==='failed'||taskState==='interrupted'?'Task needs attention · See details':'Task activity';
  $('#welcome').hidden=c.messages.length>0;
  if(shownRevision!==c.revision){
    const scroller=$('#chat-scroll');const nearEnd=scroller.scrollHeight-scroller.scrollTop-scroller.clientHeight<130;
    window.HSUHOpenUI?.dispose();
    $('#messages').replaceChildren(...c.messages.map(messageNode));
    $('#task-feed').replaceChildren(...[...c.tasks].reverse().map(taskNode));
    if(c.question?.id!==shownQuestion){$('#questions').replaceChildren(...(c.question?[questionNode(c.question)]:[]));shownQuestion=c.question?.id;}
    const approvalKey=c.task?.approval?c.task.id+':'+c.task.approval.request_id:null;
    if(approvalKey!==shownApproval){$('#approvals').replaceChildren(...(c.task?.approval?[approvalNode(c.task,selected)]:[]));shownApproval=approvalKey;}
    if(nearEnd)scroller.scrollTop=scroller.scrollHeight;
    shownRevision=c.revision;
  } else {document.querySelectorAll('.task-card .task-time').forEach((n,i)=>{const t=[...c.tasks].reverse()[i];if(t)n.textContent=`Started ${time(t.started_at)} · ${elapsed(t)} elapsed`;});}
}
const draftVersions = new Map();
$('#message').oninput=()=>{if(current){drafts.set(current,$('#message').value);draftVersions.set(current,(draftVersions.get(current)||0)+1);}};
$('#composer').onsubmit=async e=>{
  e.preventDefault();
  if(creatingChat||current&&!currentReady)return;
  const raw=$('#message').value, text=raw.trim();
  if(!text)return;
  $('#send').disabled=true;
  let submitted=current;
  try{
    if(!submitted){await newChat();submitted=current;}
    const version=draftVersions.get(submitted)||0;
    drafts.set(submitted,raw);
    const task=current===submitted?currentTask:null;
    if(currentNative&&task&&task.state==='running'){
      await api('chats/'+submitted+'/steer','POST',{task_id:task.id,message:text});
    }else{
      let submission=submissions.get(submitted);
      if(!submission||submission.text!==text||submission.version!==version){submission={text,version,id:typeof crypto!=='undefined'?crypto.randomUUID():Date.now()+'-'+Math.random().toString(36).slice(2)};submissions.set(submitted,submission);}
      await api('chats/'+submitted+'/messages','POST',{message:text,request_id:submission.id});
      submissions.delete(submitted);
    }
    // A late response owns only the unchanged draft it actually submitted.
    if((draftVersions.get(submitted)||0)===version && drafts.get(submitted)===raw){
      drafts.delete(submitted);
      if(current===submitted && $('#message').value===raw)$('#message').value='';
    }
    await updateChat();
  }catch(e){notice(e.message);if(current===submitted)$('#send').disabled=false;}
};
$('#message').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(!$('#send').disabled)$('#composer').requestSubmit();}};
$('#stop').onclick=async()=>{const chatId=current,taskId=currentTask?.id;$('#stop').disabled=true;try{await api('chats/'+chatId+'/stop','POST',{task_id:taskId});await updateChat();}catch(e){notice(e.message);$('#stop').disabled=false;}};
async function openNativeSession(id){try{const c=await api('sessions/open','POST',{session_id:id});chats=await api('chats');await selectChat(c.id);}catch(e){notice(e.message);}}
window.addEventListener('hsuh:open-session',e=>openNativeSession(e.detail));
function actionButton(label,action,cls='quiet'){const b=el('button',label,cls);b.type='button';b.onclick=async()=>{b.disabled=true;try{await action();}catch(e){notice(e.message);}finally{b.disabled=false;}};return b;}
function workTask(t){const card=el('article',undefined,'native-task');const head=el('div',undefined,'panel-heading');head.append(el('h3',t.label),el('span',stateLabel(t.state),'signal '+(t.state==='failed'?'warning':'good')));card.append(head,el('p',t.summary,'fine'));
  const actions=el('div',undefined,'control-actions');actions.append(actionButton('Open conversation',()=>selectChat(t.chat_id)));
  if(busyStates.has(t.state)&&t.run_id)actions.append(actionButton(t.state==='stopping'?'Stopping…':'Stop task',async()=>{await api('chats/'+t.chat_id+'/stop','POST',{task_id:t.id});await tick();await controls();}));
  card.append(actions);if(t.approval)card.append(approvalNode(t,t.chat_id));card.append(taskNode(t));return card;}
function renderControl(){const root=$('#control-content');if(!controlData?.enabled){root.replaceChildren(el('p',controlData?.note||'Connecting to the native gateway…','fine'));return;}
  const nodes=[];
  if(workTab==='tasks'){
    const tasks=[...controlData.tasks].sort((a,b)=>Number(busyStates.has(b.state))-Number(busyStates.has(a.state))||b.created_at-a.created_at);
    nodes.push(el('p','Start a task in any conversation. Watch its tools here, send guidance in chat, or stop that exact run.','fine'));
    nodes.push(...tasks.map(workTask));if(!tasks.length)nodes.push(el('div','No tasks started from this website yet. Open a conversation and ask Hermes to do something.','control-empty'));
  }else if(workTab==='jobs'){
    nodes.push(el('p','Native scheduled jobs. Pause prevents future runs; it does not cancel an execution already in progress. Ask Hermes in chat to create or edit a schedule.','fine'));
    for(const j of controlData.jobs){const card=el('article',undefined,'native-task');const h=el('div',undefined,'panel-heading');h.append(el('h3',j.name||j.id),el('span',j.state|| (j.enabled?'Enabled':'Paused'),'subtle-tag'));card.append(h,el('p',j.schedule_display||'Native schedule'),el('p',`Next: ${j.next_run_at||'—'} · Last result: ${j.last_status||'No run recorded'}`,'fine'));const actions=el('div',undefined,'control-actions');for(const [label,action] of [[j.enabled?'Pause':'Resume',j.enabled?'pause':'resume'],['Run now','run']])actions.append(actionButton(label,async()=>{if(action==='run'&&!confirm('Run this scheduled task now: '+(j.name||j.id)+'?'))return;await api('jobs/'+encodeURIComponent(j.id)+'/'+action,'POST',{});await controls();}));card.append(actions);nodes.push(card);}if(!controlData.jobs.length)nodes.push(el('p','No native scheduled jobs.','control-empty'));
  }else if(workTab==='sessions'){
    nodes.push(el('p','Open an existing Hermes transcript, including Telegram conversations, and continue it here. A task already running on Telegram remains owned by that transport.','fine'));
    for(const s of controlData.sessions){const card=el('article',undefined,'native-session');const copy=el('div');copy.append(el('h3',s.title||'Untitled Hermes conversation'),el('p',`${s.source||'native'} · ${s.message_count||0} messages · ${s.tool_call_count||0} tool calls · ${s.model||'Native model'}`,'fine'));card.append(copy,actionButton('Open',()=>openNativeSession(s.id)));nodes.push(card);}
  }else{
    nodes.push(el('p','Ask Hermes to use these tools in chat. Availability follows the native API platform configuration and installed credentials. Tools execute on the VPS.','fine'));
    const label=el('label','Find a tool','tool-search'),input=el('input');input.type='search';input.placeholder='Search terminal, browser, memory…';label.append(input);const list=el('div',undefined,'tool-catalog');
    const filter=()=>{const q=input.value.toLowerCase();list.replaceChildren(...controlData.tools.filter(t=>`${t.name} ${t.description} ${(t.tools||[]).join(' ')}`.toLowerCase().includes(q)).map(t=>{const row=el('article',undefined,'toolset-row'),h=el('div',undefined,'panel-heading');h.append(el('h3',t.label||t.name),el('span',t.name==='clarify'?'Chat replies':t.enabled?(t.configured?'Available':'Setup needed'):'Disabled','signal '+(t.enabled&&t.configured?'good':'warning')));row.append(h,el('p',t.name==='clarify'?'Reply in the conversation. Native API clarification cards are not available.':t.description||'','fine'),el('p',(t.tools||[]).join(' · '),'fine mono'));return row;}));};input.oninput=filter;filter();nodes.push(label,list);
  }
  root.replaceChildren(...nodes);$('#control-note').textContent=controlData.note;$('#work-running').textContent=controlData.tasks.filter(t=>busyStates.has(t.state)).length+' active';
}
document.querySelectorAll('[data-work-tab]').forEach(b=>b.onclick=()=>{workTab=b.dataset.workTab;document.querySelectorAll('[data-work-tab]').forEach(n=>n.setAttribute('aria-selected',String(n===b)));renderControl();});
async function controls(){if(controlBusy||document.hidden)return;controlBusy=true;try{controlData=await api('control');if(!$('#control-content').contains?.(document.activeElement)||!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName))renderControl();}catch(e){$('#control-note').textContent=e.message;}finally{controlBusy=false;}}
let telemetryBusy=false,activityBusy=false;
async function telemetry(){
  if(telemetryBusy||document.hidden)return;telemetryBusy=true;
  try{const d=await api('telemetry'),m=d.memory,p=m.used/m.total*100;$('#ribbon-ram').textContent=p.toFixed(0)+'%';$('#ribbon-ram').title=`${(m.used/1024**3).toFixed(2)} of ${(m.total/1024**3).toFixed(2)} GiB used. Sampled ${time(d.sampled_at)}.`;statsEvent('telemetry',d);
  }catch{$('#ribbon-ram').textContent='—';$('#ribbon-ram').title='Live RAM reading unavailable';statsEvent('stats-error',{source:'host',message:'Live host telemetry is unavailable.'});}finally{telemetryBusy=false;}
}
async function activity(){if(activityBusy||document.hidden)return;activityBusy=true;try{const d=await api('activity');$('#ribbon-agents').textContent=d.gateway?.stale?'—':d.gateway?.active_agents??'—';$('#ribbon-agents').title='Active Hermes agents across conversations';statsEvent('activity',d);}catch{$('#ribbon-agents').textContent='—';statsEvent('stats-error',{source:'activity',message:'Native activity metadata is unavailable.'});}finally{activityBusy=false;}}
async function quota(){
  try{const d=await api('quota'),n=d.native,w=n.windows?.[0];statsEvent('quota',d);$('#ribbon-quota').textContent=w?`${(100-w.used_percent).toFixed(0)}% left`:'—';$('#ribbon-quota').title=w?`${w.label} limit. Open Stats for all limits and reset times.`:'Provider quota unavailable';
  }catch{$('#ribbon-quota').textContent='—';$('#ribbon-quota').title='Provider quota unavailable';statsEvent('quota',{native:{available:false,windows:[],note:'Quota source unavailable. No balance estimated.'},aperture:{note:'Unavailable.'}});}
}
async function tick(){if(pollBusy||document.hidden)return;pollBusy=true;try{chats=await api('chats');renderList();await updateChat();await api('status');$('#connection').textContent='Connected';$('#connection').dataset.state='connected';}catch(e){$('#connection').textContent='Disconnected · refresh to sign in';$('#connection').dataset.state='disconnected';}finally{pollBusy=false;}}
let installPrompt;
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e;$('#install').hidden=false;});
$('#install').onclick=async()=>{if(installPrompt){await installPrompt.prompt();installPrompt=null;$('#install').hidden=true;}};
if('serviceWorker'in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
try{chats=await api('chats');if(chats.length)await selectChat(chats[0].id,false);else await newChat(false);await tick();telemetry();activity();quota();}catch(e){notice(e.message);}
setInterval(tick,2000);setInterval(telemetry,5000);setInterval(activity,12000);setInterval(()=>{if(!document.hidden)quota();},65000);
setInterval(()=>{if($('.workspace').dataset.view==='work')controls();},4000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden){tick();telemetry();activity();}});
