/* Run with: node track_2a/src/tests/browser_session.test.js
   A small DOM stub exercises the actual app without browser dependencies. */
async function runBrowserSessionTests(source) {
  function assert(value, message) { if (!value) throw new Error(message); }
  async function boot({denyRead=false, denyWrite=false, mode='success', startFails=false}={}) {
    const elements = new Map(), calls = [];
    function element() {
      return {value:'', textContent:'', hidden:false, disabled:false, children:[], options:[],
        addEventListener(){}, setAttribute(){}, removeAttribute(){}, focus(){}, scrollIntoView(){},
        append(...items){this.children.push(...items);this.options.push(...items);this.lastElementChild=items.at(-1);},
        replaceChildren(){this.children=[];this.options=[];}, lastElementChild:{scrollIntoView(){}}};
    }
    const document = {documentElement:{}, querySelectorAll:()=>[], querySelector:()=>element(), createElement:element,
      getElementById(id) {
        assert(!['experience','difficulty','hybrid-config'].includes(id), 'Removed dropdown still referenced: '+id);
        if (!elements.has(id)) elements.set(id,element());
        return elements.get(id);
      }};
    const config = {provider:'apertus', max_answers:26,
      locales:{en:new Proxy({}, {get:(_,key)=>String(key)})},
      scenarios:{it:{translations:{en:{opening:'Opening',label:'IT'}}}}};
    const state = {revision:1, answers:1, current_stage:'feedback', prior_learning_targets:[]};
    const result = {reply:'Recap', complete:true, can_continue:false, state, optional_practice_choices:[]};
    let attempts=0;
    async function fetch(path,options) {
      calls.push({path,body:options?.body});
      if (path==='/api/config') return {ok:true,json:async()=>config};
      if (path==='/api/session/start') {
        if(startFails) throw new Error('offline');
        return {ok:true,json:async()=>({session_id:'a'.repeat(32),opening:'Opening',max_answers:26,state:{...state,answers:0,revision:0}})};
      }
      attempts++;
      if (mode==='lost' && attempts===1) throw new TypeError('Lost response');
      if (mode==='offline') throw new TypeError('Offline');
      if (mode==='invalid-json' && attempts===1) return {ok:true,json:async()=>{throw new SyntaxError('Truncated JSON');}};
      if (mode==='rejected') return {ok:false,json:async()=>({error:'Invalid request'})};
      if (mode==='recap-retry' && attempts===1) return {ok:true,json:async()=>({...result,complete:false,can_continue:false,recap_retryable:true,state:{...state,revision:2}})};
      if (mode==='recap-exhausted') return {ok:true,json:async()=>({...result,complete:false,can_continue:false,recap_retryable:false,state:{...state,revision:2}})};
      return {ok:true,json:async()=>result};
    }
    const storage = {getItem(){if(denyRead) throw new Error('Storage denied');return null;},
      setItem(){if(denyWrite) throw new Error('Quota exceeded');}};
    const api = new Function('document','window','localStorage','fetch','CustomEvent','confirm',source+
      '\nreturn {submitToCoach,sessionRequest,writePreference,state:()=>({sessionId,sessionRevision,complete,busy})};')(
        document,{dispatchEvent(){},addEventListener(){}},storage,fetch,function(){},()=>true);
    for(let i=0;i<12;i++) await Promise.resolve();
    return {api,elements,calls};
  }
  let tests=0;
  {
    const {api,calls}=await boot({denyRead:true});
    assert(api.state().sessionId, 'Denied storage must not block startup');
    assert(calls.some(x=>x.path==='/api/session/start'), 'Start request missing');tests++;
  }
  {
    const {api,elements,calls}=await boot({denyWrite:true});
    api.writePreference('interview-language','en');
    elements.get('answer').value='My answer';await api.submitToCoach();
    assert(api.state().complete && api.state().sessionRevision===1, 'Denied storage must not interrupt completion');
    const start=JSON.parse(calls.find(x=>x.path==='/api/session/start').body);
    assert(!('experience' in start) && !('difficulty' in start), 'Removed settings sent to server');tests++;
  }
  for(const mode of ['lost','invalid-json']) {
    const {api,elements,calls}=await boot({mode});elements.get('answer').value='My answer';await api.submitToCoach();
    const answers=calls.filter(x=>x.path==='/api/answer');
    assert(answers.length===2 && answers[0].body===answers[1].body, 'Retry must preserve exact request');
    assert(api.state().complete && elements.get('answer').value==='', 'Retry did not restore completed state');tests++;
  }
  for(const mode of ['offline','rejected']) {
    const {api,elements,calls}=await boot({mode});elements.get('answer').value='Keep my draft';await api.submitToCoach();
    assert(elements.get('answer').value==='Keep my draft' && api.state().sessionRevision===0, 'Failed submission changed draft/revision');
    assert(calls.filter(x=>x.path==='/api/answer').length===(mode==='offline'?2:1), 'Incorrect retry count');tests++;
  }
  {
    const {api,elements}=await boot({startFails:true});
    assert(!api.state().sessionId && elements.get('send').disabled && elements.get('recap').disabled, 'Failed startup must disable submission');tests++;
  }
  {
    const {api,elements,calls}=await boot({mode:'recap-retry'});
    elements.get('answer').value='My final answer';await api.submitToCoach();
    assert(!api.state().complete && api.state().sessionRevision===2, 'Failed recap closed session or lost new revision');
    assert(elements.get('answer-form').hidden && !elements.get('recap').disabled, 'Recap retry should be available without another answer');
    await api.submitToCoach(true);
    const retry=JSON.parse(calls.find(x=>x.path==='/api/recap').body);
    assert(retry.revision===2 && retry.answer==='' && api.state().complete, 'Recap retry resubmitted candidate answer');tests++;
  }
  {
    const {api,elements}=await boot({mode:'recap-exhausted'});
    elements.get('answer').value='My final answer';await api.submitToCoach();
    assert(!api.state().complete && elements.get('recap').disabled && !elements.get('restart').disabled, 'Exhausted recap should offer restart without false completion');tests++;
  }
  return tests;
}
if (typeof require !== 'undefined' && require.main === module) {
  const fs=require('node:fs'),path=require('node:path');
  runBrowserSessionTests(fs.readFileSync(path.join(__dirname,'../static/app.js'),'utf8'))
    .then(n=>console.log(`${n} browser regression tests passed`)).catch(error=>{console.error(error);process.exitCode=1;});
}
