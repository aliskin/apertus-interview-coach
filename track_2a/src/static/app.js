const $ = id => document.getElementById(id);
let transcript = [], config, busy = false, complete = false, language = 'en', scenario = 'it';
let locales;
const t = key => locales[language][key];
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
  try { localStorage.setItem('interview-language', language); } catch (_) { /* Preference storage is optional. */ }
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
function reset() {
  transcript = [{role: 'assistant', content: config.scenarios[scenario].translations[language].opening}]; complete = false;
  $('conversation').replaceChildren(); bubble('assistant', transcript[0].content);
  $('answer-form').hidden = false; $('finished').hidden = true; $('answer').value = ''; $('status').textContent = ''; $('answer-help').open = false; $('answer-hint').textContent = t('openingHint'); update();
}
function update() {
  const answers = transcript.filter(x => x.role === 'user').length;
  $('progress').textContent = complete ? t('complete') : t('question').replace('{n}', Math.min(answers + 1, 3));
  [...$('steps').children].forEach((li, i) => { li.className = i < answers ? 'done' : i === answers ? 'active' : ''; if (i === answers && !complete) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current'); });
  $('count').textContent = `${$('answer').value.length.toLocaleString(language)} / ${(4000).toLocaleString(language)} · ${t('time')}`;
  $('answer').placeholder = t('placeholder');
  $('send').textContent = t(busy ? 'sending' : 'send');
  $('download').hidden = answers === 0;
  $('download').disabled = busy;
  $('conversation').setAttribute('aria-busy', String(busy));
  $('send').disabled = busy || !$('answer').value.trim(); $('answer').disabled = busy; $('restart').disabled = busy; $('language').disabled = busy; $('scenario').disabled = busy;
}
$('answer').addEventListener('input', update);
$('answer-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy || !$('answer').value.trim()) return;
  const answer = $('answer').value.trim(); const pending = [...transcript, {role: 'user', content: answer}];
  busy = true; $('status').textContent = t('thinking'); update();
  try {
    const response = await fetch('/api/answer', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({transcript: pending, language, scenario})});
    const data = await response.json(); if (!response.ok) throw new Error(data.error);
    transcript = [...pending, {role: 'assistant', content: data.reply}]; bubble('user', answer); bubble('assistant', data.reply);
    $('answer').value = ''; $('answer-hint').textContent = data.hint || t('genericHint'); complete = data.complete; $('answer-form').hidden = complete; $('finished').hidden = !complete; $('status').textContent = '';
  } catch (error) { $('status').textContent = t('error'); }
  finally { busy = false; update(); if (!complete) $('answer').focus({preventScroll: true}); if (!$('status').textContent) $('conversation').lastElementChild.scrollIntoView({block: 'start', behavior: 'instant'}); }
});
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
  try { const saved = localStorage.getItem('interview-language'); if (Object.hasOwn(locales, saved)) language = saved; } catch (_) { /* Storage may be unavailable. */ }
  $('language').value = language;
  $('demo-note').hidden = data.provider !== 'demo'; translate(); reset();
}).catch(() => { $('status').textContent = 'Cannot connect / Keine Verbindung / Connexion impossible / Connessione non riuscita. ↻'; $('send').disabled = true; $('restart').disabled = true; });
