// Execute the complete production controller with only DOM/network boundaries stubbed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor() { this.value=''; this.dataset={}; this.children=[]; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children=nodes; }
  setAttribute() {}
  focus() {}
  querySelectorAll() { return []; }
}
async function fixture() {
  const elements = new Map();
  const get = selector => {
    if(!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  };
  let resolvePost, posted;
  const pending = new Promise(resolve => { resolvePost=resolve; });
  const chat = id => ({id,title:id,messages:[],tasks:[],question:null,task:null,revision:0});
  const response = data => ({ok:true,json:async()=>data});
  const document = {querySelector:get,querySelectorAll:()=>[],createElement:()=>new Element(),addEventListener(){}};
  const fetch = async (url, options) => {
    if(url==='/api/chats/a/messages' && options.method==='POST') {
      posted=JSON.parse(options.body);
      return pending;
    }
    const data = {
      '/api/chats': [chat('a'),chat('b')],
      '/api/chats/a':chat('a'), '/api/chats/b':chat('b'),
      '/api/status':{active:0,access:'Fixture'},
      '/api/telemetry':{memory:{used:1,total:2,available:1},swap:{used:0,total:1},processes:[]},
      '/api/quota':{native:{available:false,windows:[]},aperture:{note:'Fixture'}}
    };
    assert.ok(url in data, `Unexpected fixture network request: ${url}`);
    return response(data[url]);
  };
  const source=fs.readFileSync(path.join(__dirname,'../hsuh/static/app.js'),'utf8');
  const context=vm.createContext({document,fetch,navigator:{},window:{addEventListener(){}},setInterval(){},setTimeout(){},console});
  const controller=await new vm.Script('(async()=>{'+source+'\nreturn {selectChat};})()').runInContext(context);
  const input = value => { get('#message').value=value; get('#message').oninput?.({}); };
  const send = () => get('#composer').onsubmit({preventDefault(){}});
  return {get,input,send,controller,posted:()=>posted,resolve:()=>resolvePost(response({}))};
}
async function main() {
  {
    const f=await fixture();
    f.input('Submitted A');
    const sending=f.send();
    assert.equal(f.posted().message,'Submitted A');
    await f.controller.selectChat('b');
    f.input('Unsent draft B');
    f.resolve(); await sending;
    assert.equal(f.get('#message').value,'Unsent draft B', 'A resolving must not erase visible B draft');
    await f.controller.selectChat('a');
    assert.equal(f.get('#message').value,'', 'A submitted draft must be cleared under its own chat ID');
    await f.controller.selectChat('b');
    assert.equal(f.get('#message').value,'Unsent draft B', 'B draft must remain in memory after switching');
  }
  {
    const f=await fixture();
    f.input('Submitted A');
    const sending=f.send();
    f.input('New draft A');
    f.resolve(); await sending;
    assert.equal(f.get('#message').value,'New draft A', 'An edited same-chat draft must survive');
  }
  {
    const f=await fixture();
    f.input('Same text');
    const sending=f.send();
    f.input('Edit'); f.input('Same text');
    f.resolve(); await sending;
    assert.equal(f.get('#message').value,'Same text', 'Draft generation, not just text equality, owns cleanup');
  }
  console.log('Frontend deferred-send races: 3 scenarios passed (full production app.js).');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
