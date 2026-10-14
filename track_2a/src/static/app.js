const $ = id => document.getElementById(id);
let transcript = [], config, busy = false, complete = false, language = 'de', scenario = 'it', canContinue = true, suggestRecap = false;
let canRevise = false, recapRetryable = true;
let locales, sessionId = null, sessionRevision = 0, sessionState = null;
const t = key => locales[language][key];
// Storage is an optional convenience, including when accessing it throws.
function readPreference(key) {
  try { return localStorage.getItem(key); } catch (_) { return null; }
}
function writePreference(key, value) {
  try { localStorage.setItem(key, value); } catch (_) { /* Practice works without storage. */ }
}
// Retry the exact request after a missing/unreadable response. The server replays
// an already committed response instead of advancing or calling the model again.
async function sessionRequest(path, payload) {
  const options = {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)};
  for (let attempt = 0; attempt < 2; attempt++) {
    let response, data;
    try { response = await fetch(path, options); data = await response.json(); }
    catch (error) { if (attempt === 0) continue; throw error; }
    if (!response.ok) throw new Error(data.error);
    return data;
  }
}
// Optional voice adapters listen for these events; text practice needs no adapter.
function cancelVoice() {
  window.dispatchEvent(new CustomEvent('coach:cancel', {detail:{session_id:sessionId}}));
}
function publishVoice(speech) {
  if (speech) window.dispatchEvent(new CustomEvent('coach:output', {detail:speech}));
}
window.addEventListener('pagehide', cancelVoice);
window.addEventListener('coach:transcription', event => {
  const input=event.detail;
  if (!input || input.final !== true || input.session_id !== sessionId || input.language !== language || busy || complete || !canContinue) return;
  if (typeof input.text !== 'string' || !input.text.trim() || input.text.length>4000 || $('answer').value.trim()) return;
  // A final ASR transcript becomes an editable draft; submission stays explicit.
  cancelVoice(); $('answer').value=input.text; update(); $('answer').focus();
});
function translate() {
  document.documentElement.lang = language;
  document.title = t('title');
  document.querySelectorAll('[data-i18n]').forEach(element => { element.textContent = t(element.dataset.i18n); });
  $('answer').placeholder = t('placeholder');
  [...$('scenario').options].forEach(option => { option.textContent = config.scenarios[option.value].translations[language].label; });
  document.querySelector('[data-i18n=job]').textContent = config.scenarios[scenario].translations[language].label;
  document.querySelector('.practice').setAttribute('aria-label', t('practice'));
  $('conversation').setAttribute('aria-label', t('conversation'));
  $('mode').textContent = t(config.provider === 'demo' ? 'demoMode' : config.provider === 'apertus' ? 'apertusMode' : 'localMode');
}
$('language').addEventListener('change', () => {
  const selected = $('language').value;
  if ((transcript.length > 1 || $('answer').value.trim()) && !confirm(t('switchConfirm'))) {
    $('language').value = language; return;
  }
  language = selected;
  writePreference('interview-language', language);
  translate(); reset();
});
$('scenario').addEventListener('change', () => {
  const selected = $('scenario').value;
  if ((transcript.length > 1 || $('answer').value.trim()) && !confirm(t('scenarioConfirm'))) {
    $('scenario').value = scenario; return;
  }
  scenario = selected; translate(); reset();
});
function bubble(role, content) {
  const card = document.createElement('article'); card.className = `message ${role}`;
  const label = document.createElement('span'); label.className = 'speaker'; label.textContent = role === 'assistant' ? t('coach') : t('you');
  const text = document.createElement('p'); text.textContent = content;
  card.append(label, text); $('conversation').append(card);
}
async function reset() {
  cancelVoice();
  $('practice-choice-form').hidden = true; $('practice-choice-status').textContent='';
  recapRetryable = true; canRevise = false; $('revision-form').hidden = true; $('revision-answer').value = '';
  busy = true; sessionId = null; sessionRevision = 0; sessionState = null;
  transcript = [{role: 'assistant', content: config.scenarios[scenario].translations[language].opening}]; complete = false; canContinue = true; suggestRecap = false;
  $('conversation').replaceChildren(); bubble('assistant', transcript[0].content);
  $('answer-form').hidden = false; $('finished').hidden = true; $('answer').value = ''; $('status').textContent = ''; $('answer-help').open = false; $('answer-hint').textContent = t('openingHint'); update();
  try {
    const response = await fetch('/api/session/start', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({language,scenario,previous_session_id:readPreference("practice-last-"+language+"-"+scenario)})});
    const data = await response.json(); if (!response.ok) throw new Error(data.error);
    sessionId = data.session_id; sessionState = data.state;
    config.max_answers = data.max_answers;
    transcript = [{role:'assistant',content:data.opening}]; $('conversation').replaceChildren(); bubble('assistant',data.opening);
    publishVoice(data.speech);
  } catch(error) { $('status').textContent = t('error'); }
  finally { busy = false; update(); }
}
function update() {
  const answers = transcript.filter(x => x.role === 'user').length;
  $('progress').textContent = complete ? t('complete') : !canContinue ? t('recapReady') : t('question').replace('{n}', answers + 1);
  if (sessionState && !complete) $('progress').textContent += ' · ' + t('stage_' + sessionState.current_stage);
  const phase = complete ? 2 : answers > 0 ? 1 : 0;
  [...$('steps').children].forEach((li, i) => {
    li.className = complete || i < phase ? 'done' : i === phase ? 'active' : '';
    if (!complete && i === phase) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
  });
  $('answer-form').hidden = complete || !canContinue;
  $('recap').hidden = complete;
  $('recap').disabled = busy || !sessionId || !recapRetryable || (answers === 0 && !$('answer').value.trim());
  $('recap').textContent = t($('answer').value.trim() ? 'sendRecap' : 'recap');
  $('recap-suggestion').hidden = complete || !suggestRecap;
  $('recap-suggestion').textContent = t(canContinue ? 'recapSuggested' : 'recapReady');
  $('session-limit').hidden = complete;
  $('session-limit').textContent = t('sessionLimit').replace('{n}', config.max_answers);
  $('count').textContent = `${$('answer').value.length.toLocaleString(language)} / ${(4000).toLocaleString(language)} · ${t('time')}`;
  $('answer').placeholder = t('placeholder');
  $('send').textContent = t(busy ? 'sending' : 'send');
  $('download').hidden = answers === 0;
  $('download').disabled = busy;
  $('conversation').setAttribute('aria-busy', String(busy));
  $('send').disabled = busy || !sessionId || !$('answer').value.trim(); $('answer').disabled = busy; $('restart').disabled = busy; $('language').disabled = busy; $('scenario').disabled = busy; $('choose-practice').disabled=busy; $('practice-choice').disabled=busy;
}
$('answer').addEventListener('input', update);
async function submitToCoach(recap = false) {
  if (busy || complete || !sessionId) return;
  const answer = $('answer').value.trim();
  if ((!recap && !answer) || (recap && !answer && !transcript.some(item => item.role === 'user'))) return;
  const pending = answer ? [...transcript, {role: 'user', content: answer}] : [...transcript];
  cancelVoice();
  busy = true; $('status').textContent = t(recap ? 'recapping' : 'thinking'); update();
  try {
    const data = await sessionRequest(recap ? '/api/recap' : '/api/answer', {session_id:sessionId,revision:sessionRevision,answer,language,scenario});
    transcript = [...pending, {role: 'assistant', content: data.reply}]; if (answer) bubble('user', answer); bubble('assistant', data.reply);
    $('answer').value = ''; $('answer-hint').textContent = data.hint || t('genericHint');
    sessionRevision = data.state.revision ?? (data.state.answers + (data.state.practice_answers || 0)); sessionState = data.state;
    canRevise = data.can_revise === true; $('revision-form').hidden = !canRevise;
    const choices=data.optional_practice_choices || []; $('practice-choice').replaceChildren();
    for (const choice of choices) {const option=document.createElement('option');option.value=choice.target_id;option.textContent=choice.label;$('practice-choice').append(option);}
    $('practice-choice-form').hidden = !choices.length;
    if (data.complete) writePreference('practice-last-'+language+'-'+scenario,sessionId);
    recapRetryable = data.recap_retryable !== false;
    complete = data.complete; canContinue = data.can_continue; suggestRecap = data.suggest_recap;
    publishVoice(data.speech);
    $('finished').hidden = !complete; $('status').textContent = '';
  } catch (error) { $('status').textContent = t('error'); }
  finally {
    busy = false; update();
    if (!complete && canContinue) $('answer').focus({preventScroll: true});
    else if (!complete) $('recap').focus({preventScroll: true});
    if (!$('status').textContent) $('conversation').lastElementChild.scrollIntoView({block: 'start', behavior: 'instant'});
  }
}
$('practice-choice-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy || !complete) return;
  cancelVoice(); busy=true; update(); $('choose-practice').disabled=true; $('practice-choice-status').textContent='Deine freiwillige Übung wird vorbereitet …';
  try {
    const data=await sessionRequest('/api/practice/select',{session_id:sessionId,revision:sessionRevision,target_id:$('practice-choice').value,language,scenario});
    sessionState=data.state; sessionRevision=data.state.revision ?? (data.state.answers+data.state.practice_answers);bubble('assistant',data.reply); transcript.push({role:'assistant',content:data.reply});canRevise=data.can_revise===true;$('revision-form').hidden=!canRevise;
    $('practice-choice-status').textContent=canRevise?t('practiceReady'):t('practiceUnavailable');publishVoice(data.speech);
    if (canRevise) { $('revision-answer').focus({preventScroll:true}); $('revision-form').scrollIntoView({block:'nearest',behavior:'instant'}); }
  } catch(error) {$('practice-choice-status').textContent=t('practiceError');}
  finally {busy=false;$('choose-practice').disabled=false;update();}
});
$('revision-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy || !canRevise) return;
  const answer = $('revision-answer').value.trim(); if (!answer) return;
  cancelVoice(); busy=true; update(); $('revision-answer').disabled=true; $('revise').disabled=true; $('revision-status').textContent=t('revisionWorking');
  try {
    const data=await sessionRequest('/api/revise',{session_id:sessionId,revision:sessionRevision,answer,language,scenario});
    bubble('user',answer); bubble('assistant',data.reply); transcript.push({role:'user',content:answer},{role:'assistant',content:data.reply});
    sessionState=data.state; sessionRevision=data.state.revision ?? (data.state.answers+data.state.practice_answers); $('revision-answer').value=''; $('revision-status').textContent=t('revisionSaved'); publishVoice(data.speech);
  } catch(error) { $('revision-status').textContent=t('revisionError'); }
  finally {busy=false; $('revision-answer').disabled=false; $('revise').disabled=false; update();}
});
$('answer-form').addEventListener('submit', event => { event.preventDefault(); submitToCoach(false); });
function bindSendShortcut(inputId, formId) {
  const input = $(inputId), form = $(formId);
  input.addEventListener('keydown', event => {
    if (event.key !== 'Enter' || !(event.ctrlKey || event.metaKey) || event.isComposing) return;
    event.preventDefault();
    if (busy || event.repeat || input.disabled || form.hidden || !input.value.trim()) return;
    form.requestSubmit();
  });
}
bindSendShortcut('answer', 'answer-form');
bindSendShortcut('revision-answer', 'revision-form');

$('recap').addEventListener('click', () => submitToCoach(true));
$('restart').addEventListener('click', () => { if ((transcript.length > 1 || $('answer').value.trim()) && !confirm(t('restartConfirm'))) return; reset(); $('answer').focus(); });
$('download').addEventListener('click', () => {
  const text = `${t('export')} (${config.provider}, ${language}, ${config.scenarios[scenario].translations[language].label})\n\n` + transcript.map(x => `${x.role === 'user' ? t('you') : t('coach')}:\n${x.content}`).join('\n\n');
  const url = URL.createObjectURL(new Blob([text], {type: 'text/plain'})); const link = document.createElement('a'); link.href = url; link.download = `interview-${language}.txt`; link.click(); URL.revokeObjectURL(url);
});
fetch('/api/config').then(r => { if (!r.ok) throw new Error(); return r.json(); }).then(data => {
  config = data; locales = data.locales;
  for (const [id, item] of Object.entries(config.scenarios)) {
    const option = document.createElement('option'); option.value = id; option.textContent = item.translations.en.label; $('scenario').append(option);
  }
  $('scenario').value = scenario;
  const saved = readPreference('interview-language'); if (Object.hasOwn(locales, saved)) language = saved;
  $('language').value = language;
  $('demo-note').hidden = data.provider !== 'demo'; translate(); reset();
}).catch(() => { $('status').textContent = 'Cannot connect / Keine Verbindung / Connexion impossible / Connessione non riuscita. ↻'; $('send').disabled = true; $('restart').disabled = true; });
