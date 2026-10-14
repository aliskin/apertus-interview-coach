'use strict';
const $ = id => document.getElementById(id);
const languages = {de: 'German', gsw: 'Swiss German', fr: 'French', it: 'Italian', en: 'English'};
const choices = [['meets', 'Meets'], ['violates', 'Violates'], ['not_applicable', 'Not applicable'], ['not_sure', 'Not sure']];
let data, catalog, version, index = 0, draft, dirty = false, saving = false, loading = false;
function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function message(text, kind = '') {
  $('save-message').textContent = text;
  $('save-message').className = kind;
}
function changed() {
  dirty = true;
  $('case-state').textContent = 'Unsaved changes';
  $('case-state').className = 'save-badge';
  message('Unsaved changes. Click Save to keep these labels.');
  updateCounts();
  renderCaseSummary();
}
function updateCounts() {
  const total = data.groups.reduce((n, group) => n + group.rules.length, 0);
  const labeled = Object.values(draft.rules).filter(rule => rule.status).length;
  $('label-progress').textContent = `${labeled} of ${total} guidelines labelled`;
  $('remaining').textContent = labeled === total ? 'Ready to save. Evidence and notes are optional.' : `${total - labeled} remaining · “Not sure for remaining” fills unanswered guidelines.`;
  for (const group of data.groups) {
    const count = group.rules.filter(rule => draft.rules[rule.id].status).length;
    $(`count-${group.rules[0].id}`).textContent = `${count}/${group.rules.length}`;
  }
}
function renderVersions() {
  $('versions').replaceChildren();
  if (!catalog) return;
  const grouped = new Map();
  for (const v of catalog.versions) { if (!grouped.has(v.group)) grouped.set(v.group, []); grouped.get(v.group).push(v); }
  for (const [title, versions] of grouped) {
    const folder = node('details', undefined, 'version-folder'); folder.open = !title.startsWith('Archive') || versions.some(v => v.id === version);
    folder.append(node('summary', title));
    for (const v of versions) {
      const button = node('button', undefined, `version-button${v.id === version ? ' active' : ''}`); button.type = 'button';
      if (v.id === version) button.setAttribute('aria-current', 'page');
      button.append(node('strong', v.title), node('small', v.description), node('small', `${v.summary.saved}/${v.summary.total} reviewed · ${v.summary.validated} validated`));
      button.addEventListener('click', () => loadVersion(v.id)); folder.append(button);
    }
    $('versions').append(folder);
  }
}
function renderVersionSummary() {
  if (!data.summary) return;
  const s = data.summary; $('version-title').textContent = data.version?.title || 'Review summary';
  $('summary-stats').replaceChildren();
  for (const [value,title] of [[`${s.saved}/${s.total}`, 'Reviewed'], [s.counts.violates, 'Guideline violations'], [s.drafts, 'Drafts'], [s.validated, 'Validated'], [s.counts.not_sure, 'Not sure']]) {
    const stat = node('div', undefined, 'summary-stat'); stat.append(node('strong', String(value)), node('span', title)); $('summary-stats').append(stat);
  }
  $('summary-categories').replaceChildren();
  for (const group of s.categories) {
    const chip = node('button', `${group.title}: ${group.violations}`, `summary-chip${group.violations ? ' has-violations' : ''}`); chip.type = 'button';
    chip.title = `${group.violations} guideline violations in ${group.cases} examples`; chip.addEventListener('click', () => jumpReview(group.rule_ids[0])); $('summary-categories').append(chip);
  }
}
function renderCaseSummary() {
  if (!draft) return;
  $('case-findings').replaceChildren();
  const violations = Object.entries(draft.rules).filter(([,r]) => r.status === 'violates');
  const uncertain = Object.values(draft.rules).filter(r => r.status === 'not_sure').length;
  $('case-findings').append(node('p', `${violations.length} guideline violations · ${uncertain} not sure${dirty ? ' · unsaved edits' : ''}`, 'small'));
  for (const [id] of violations) {
    const chip = node('button', id, 'rule-chip'); chip.type = 'button'; chip.addEventListener('click', () => jumpReview(id)); $('case-findings').append(chip);
  }
  $('case-review-notes').textContent = (data.cases[index].selection_reason ? '★ Validation selection: ' + data.cases[index].selection_reason + '\n\n' : '') + (draft.notes || 'No review notes saved yet.');
}
function jumpReview(id) {
  const rule = $(`rule-${id}`); if (!rule) return;
  rule.closest('.guideline-group').open = true;
  rule.querySelector('.rule-details').open = true;
  rule.scrollIntoView({behavior: 'smooth', block: 'start'});
  rule.classList.add('evidence-target'); setTimeout(() => rule.classList.remove('evidence-target'), 1800);
}
function highlight(text) {
  const fragment = document.createDocumentFragment(); const matches = [];
  for (const [id,r] of Object.entries(draft.rules)) {
    if (!r.evidence) continue;
    let pos = 0;
    while ((pos = text.indexOf(r.evidence, pos)) !== -1) { matches.push({start:pos, end:pos+r.evidence.length, id}); pos += r.evidence.length; }
  }
  const points = [...new Set([0,text.length,...matches.flatMap(m => [m.start,m.end])])].sort((a,b) => a-b);
  for (let i=0; i<points.length-1; i++) {
    const start=points[i], end=points[i+1], ids=matches.filter(m => m.start<=start && m.end>=end).map(m => m.id);
    if (!ids.length) fragment.append(document.createTextNode(text.slice(start,end)));
    else {
      const mark=node('mark', text.slice(start,end), 'evidence-mark'); mark.dataset.rules=ids.join(' '); mark.tabIndex=0; mark.setAttribute('role','button'); mark.title=`Evidence for ${ids.join(', ')} · select to see review`;
      mark.addEventListener('click', () => jumpReview(ids[0])); mark.addEventListener('keydown', e => { if (e.key==='Enter' || e.key===' ') { e.preventDefault(); jumpReview(ids[0]); }}); fragment.append(mark);
    }
  }
  return fragment;
}
function showEvidence(id) {
  const mark = [...$('exchange').querySelectorAll('mark')].find(m => m.dataset.rules.split(' ').includes(id));
  if (!mark) { message('No visible passage matches this quote. Missing elements are explained in the review note.'); return; }
  mark.closest('details').open=true; mark.scrollIntoView({behavior:'smooth',block:'center'}); mark.focus({preventScroll:true});
}
function toggleFolds(className,buttonId,label) {
  const folds=[...$('exchange').querySelectorAll(`.${className}`)]; const expand=folds.some(d => !d.open);
  folds.forEach(d => d.open=expand); $(buttonId).textContent=`${expand ? 'Collapse' : 'Expand'} ${label}`;
}
function updateFoldButtons() {
  for (const [className,buttonId,label] of [['original-fold','toggle-originals','originals'],['translation-fold','toggle-translations','translations']]) {
    const folds=[...$('exchange').querySelectorAll(`.${className}`)];
    $(buttonId).textContent=`${folds.some(d => !d.open) ? 'Expand' : 'Collapse'} ${label}`;
  }
}
function renderExchange(preserve = false) {
  const example=data.cases[index]; const states = new Map();
  if (preserve) for (const fold of $('exchange').querySelectorAll('details[data-fold]')) states.set(fold.dataset.fold, fold.open);
  $('exchange').replaceChildren();
  $('original-language').textContent=`Original · ${languages[example.input.language] || example.input.language}`;
  const originalOnly = ['de', 'en'].includes(example.input.language);
  $('toggle-translations').hidden = originalOnly;
  $('translation-issue').closest('label').hidden = originalOnly;
  document.querySelector('.translation-notice').textContent=originalOnly ? 'Original text only; no English reading aid is needed for this language. Use original wording to judge evidence and tone.' : data.translation_notice + ' Use originals to judge wording and evidence; translations are a reading aid.';
  function row(title,original,english,coach,key) {
    const article=node('article',undefined,`exchange-row${coach ? ' coach' : ''}`); article.append(node('h4',title));
    for (const [text,translated] of [[original,false],[english,true]]) {
      if (translated && ['de', 'en'].includes(example.input.language)) continue;
      const fold=node('details',undefined,translated ? 'translation-fold' : 'original-fold'); fold.dataset.fold=key+(translated ? '-en' : '-original');
      fold.open=states.has(fold.dataset.fold) ? states.get(fold.dataset.fold) : !translated;
      fold.addEventListener('toggle', updateFoldButtons);
      fold.append(node('summary',translated ? 'English translation · reading aid' : `Original · ${languages[example.input.language] || example.input.language}`));
      const paragraph=node('p');
      if (coach && !translated) paragraph.append(highlight(text || '(No text)')); else paragraph.textContent=text || (translated ? 'Translation is being prepared. Reload after generation completes.' : '(No text)');
      fold.append(paragraph); article.append(fold);
    }
    $('exchange').append(article);
  }
  if (example.transcript) {
    example.transcript.forEach((turn,i) => row(`${i+1}. ${turn.role==='assistant' ? 'Coach' : 'Candidate'} · ${(turn.stage || '').replaceAll('_',' ')} · ${turn.question_id || ''}`,turn.content,example.translation.transcript?.[i],turn.role==='assistant',`turn-${i}`));
    for (const [title,value] of [['Company facts supplied to the coach',example.posting],['Analysis and code decisions · internal, not delivered feedback',example.analysis_trace],['Structured feedback and verification · internal fields',example.structured_feedback],['Previous recap · comparison only, not the current response',example.previous_recap]]) {
      if (value) { const detail=node('details',undefined,'context-fold'); detail.append(node('summary',title),node('pre',JSON.stringify(value,null,2))); $('exchange').append(detail); }
    }
  } else {
    for (const [key,title,text] of [['question','Interview question',example.input.question],['answer','Candidate answer',example.input.answer],['reply','Coach feedback + follow-up',example.generated.reply],['hint','Coach hint',example.generated.hint]]) {
      if (text) row(title,text,example.translation[key],key==='reply'||key==='hint',key);
    }
  }
  updateFoldButtons();
}
function renderNav() {
  const saved = Object.keys(data.reviews).length;
  $('progress').textContent = `${saved}/${data.cases.length} saved`;
  $('progress-bar').max = data.cases.length;
  $('progress-bar').value = saved;
  $('examples').replaceChildren();
  data.cases.forEach((example, i) => {
    const button = node('button', undefined, `example${i === index ? ' active' : ''}`);
    button.type = 'button';
    if (i === index) button.setAttribute('aria-current', 'step');
    button.append(node('span', data.reviews[example.case_id] ? '●' : '○', 'dot'));
    const text = node('span');
    text.append(node('strong', `${example.validation_priority ? '★ ' : ''}${example.case_id}`), node('small', `${i + 1}. ${languages[example.input.language] || example.input.language}`));
    if (example.validation_priority) { text.append(node('small','Recommended for validation')); button.title=example.selection_reason; }
    button.append(text);
    button.addEventListener('click', () => navigate(i));
    $('examples').append(button);
  });
}
function navigate(next) {
  if (saving || next === index) return;
  if (dirty && !window.confirm('Leave this example and discard its unsaved changes? Click Cancel to save first.')) return;
  index = next;
  render();
  window.scrollTo({top: 0, behavior: 'smooth'});
}
function render() {
  const example = data.cases[index];
  const previous = data.reviews[example.case_id];
  draft = previous ? structuredClone(previous) : {case_id: example.case_id, revision: 0, rules: {}, notes: '', translation_issue: false};
  draft.stage ||= example.suggested_stage;
  draft.stage_reason ||= '';
  draft.review_status ||= 'draft';
  $('interview-stage').replaceChildren();
  for (const [value, title] of Object.entries(data.stages)) {
    const option = node('option', title); option.value = value;
    $('interview-stage').append(option);
  }
  $('interview-stage').value = draft.stage;
  $('stage-reason').value = draft.stage_reason;
  $('validated').checked = draft.review_status === 'validated';
  for (const group of data.groups) for (const rule of group.rules) {
    draft.rules[rule.id] ||= {status: '', evidence: '', note: ''};
  }
  dirty = false;
  $('case-number').textContent = `EXAMPLE ${index + 1} OF ${data.cases.length}`;
  $('case-id').textContent = example.case_id;
  const occupation = example.input.occupation;
  const originalOccupation = typeof occupation === 'object' && occupation ? occupation.name_de : occupation;
  $('case-meta').textContent = `${languages[example.input.language] || example.input.language} · ${example.translation.occupation} · ${example.input.phase_key.replaceAll('_', ' ')}`;
  $('case-state').textContent = previous ? (draft.review_status === 'validated' ? 'Validated' : 'Saved draft') : 'Not saved';
  $('case-state').className = `save-badge${previous ? ' saved' : ''}`;
  $('original-language').textContent = `Original · ${languages[example.input.language] || example.input.language}`;
  renderExchange();
  $('guidelines').replaceChildren();
  for (const group of data.groups) {
    const section = node('details', undefined, 'guideline-group');
    section.open = true;
    const heading = node('summary', group.title);
    const counter = node('span', '', 'group-count');
    counter.id = `count-${group.rules[0].id}`;
    heading.append(counter);
    section.append(heading);
    for (const rule of group.rules) {
      const fieldset = node('fieldset', undefined, 'rule');
      fieldset.id = `rule-${rule.id}`;
      const legend = node('legend');
      legend.append(node('span', rule.id, 'rule-id'), document.createTextNode(rule.text));
      fieldset.append(legend);
      const buttons = node('div', undefined, 'choices');
      for (const [status, title] of choices) {
        const label = node('label', undefined, `choice${status === 'violates' ? ' violation' : ''}${status === 'not_sure' ? ' unsure' : ''}`);
        const input = node('input');
        input.type = 'radio'; input.name = `label-${rule.id}`; input.value = status;
        input.checked = draft.rules[rule.id].status === status;
        input.addEventListener('change', () => {
          draft.rules[rule.id].status = status;
          fieldset.classList.remove('invalid');
          changed();
        });
        label.append(input, node('span', title));
        buttons.append(label);
      }
      fieldset.append(buttons);
      const extra = node('details', undefined, 'rule-details');
      extra.open = Boolean(draft.rules[rule.id].evidence || draft.rules[rule.id].note);
      extra.append(node('summary', 'Add evidence or a note (optional)'));
      for (const [key, title, tag] of [['evidence', 'Exact quote from the original coach reply or hint', 'input'], ['note', 'Your explanation, including anything missing', 'textarea']]) {
        const label = node('label', title);
        const input = node(tag);
        if (tag === 'input') input.type = 'text'; else input.rows = 2;
        input.value = draft.rules[rule.id][key];
        input.maxLength = 4000;
        input.addEventListener('input', () => { draft.rules[rule.id][key] = input.value; changed(); });
        if (key === 'evidence') {
          input.addEventListener('change', () => renderExchange(true));
          input.addEventListener('input', () => { extra.querySelector('.evidence-link').hidden=!input.value.trim(); });
        }
        label.append(input); extra.append(label);
      }
      {
        const evidenceLink = node('button', 'Show evidence in interview', 'evidence-link'); evidenceLink.type = 'button';
        evidenceLink.hidden=!draft.rules[rule.id].evidence;
        evidenceLink.addEventListener('click', () => showEvidence(rule.id)); extra.append(evidenceLink);
      }
      fieldset.append(extra); section.append(fieldset);
    }
    $('guidelines').append(section);
  }
  $('overall-notes').value = draft.notes;
  $('translation-issue').checked = draft.translation_issue;
  $('previous').disabled = index === 0;
  $('save-next').textContent = index === data.cases.length - 1 ? 'Save & finish' : 'Save & next';
  message(previous ? `Saved ${new Date(previous.saved_at).toLocaleString()}. You can update this example.` : 'Labels are saved only when you click Save.', previous ? 'success' : '');
  renderVersions(); renderVersionSummary(); renderCaseSummary(); renderNav(); updateCounts();
  $('export-labels').href = `/api/export?version=${encodeURIComponent(version)}`;
  history.replaceState(null, '', `/?version=${encodeURIComponent(version)}&case=${encodeURIComponent(example.case_id)}`);
}
async function save(next = false) {
  if (saving) return;
  if (!draft.stage_reason.trim()) {
    message('Explain why the question belongs to this interview stage.', 'error');
    $('stage-reason').focus(); return;
  }
  const missing = Object.entries(draft.rules).filter(([, rule]) => !rule.status);
  if (missing.length) {
    message(`Choose a label for ${missing.length} remaining guidelines, or use “Not sure for remaining”.`, 'error');
    for (const [id] of missing) $(`rule-${id}`).classList.add('invalid');
    const first = $(`rule-${missing[0][0]}`);
    first.closest('.guideline-group').open = true;
    first.querySelector('input').focus();
    return;
  }
  saving = true;
  $('workspace').inert = true;
  $('save').disabled = $('save-next').disabled = true;
  message('Saving to this computer…');
  const payload = {case_id: draft.case_id, revision: draft.revision, rules: draft.rules, notes: draft.notes, translation_issue: draft.translation_issue,
    stage: draft.stage, stage_reason: draft.stage_reason, review_status: draft.review_status};
  try {
    const response = await fetch(`/api/review?version=${encodeURIComponent(version)}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Save failed. Please try again.');
    data.reviews[draft.case_id] = result.review;
    data.summary = result.summary || data.summary;
    const entry = catalog?.versions.find(v => v.id === version); if (entry) entry.summary = data.summary;
    renderVersions(); renderVersionSummary(); renderCaseSummary();
    draft.revision = result.review.revision;
    dirty = false; renderCaseSummary();
    $('case-state').textContent = draft.review_status === 'validated' ? 'Validated' : 'Saved draft'; $('case-state').className = 'save-badge saved';
    message('Saved to this computer.', 'success');
    renderNav();
    if (next && index < data.cases.length - 1) {
      index += 1; render(); window.scrollTo({top: 0, behavior: 'smooth'});
    } else if (next) {
      const count = Object.keys(data.reviews).length;
      message(count === data.cases.length ? `All ${data.cases.length} examples saved. You can export your labels or revisit any example.` : `Saved. ${data.cases.length - count} examples still need review.`, 'success');
    }
  } catch (error) {
    message(error.message, 'error');
  } finally {
    saving = false; $('workspace').inert = false; $('save').disabled = $('save-next').disabled = false;
  }
}
$('toggle-originals').addEventListener('click', () => toggleFolds('original-fold', 'toggle-originals', 'originals'));
$('toggle-translations').addEventListener('click', () => toggleFolds('translation-fold', 'toggle-translations', 'translations'));
$('overall-notes').addEventListener('input', event => { draft.notes = event.target.value; changed(); });
$('translation-issue').addEventListener('change', event => { draft.translation_issue = event.target.checked; changed(); });
$('interview-stage').addEventListener('change', event => { draft.stage = event.target.value; changed(); });
$('stage-reason').addEventListener('input', event => { draft.stage_reason = event.target.value; changed(); });
$('validated').addEventListener('change', event => { draft.review_status = event.target.checked ? 'validated' : 'draft'; changed(); });
$('unsure-rest').addEventListener('click', () => {
  for (const [id, rule] of Object.entries(draft.rules)) if (!rule.status) {
    rule.status = 'not_sure';
    const fieldset = $(`rule-${id}`);
    fieldset.querySelector('input[value="not_sure"]').checked = true;
    fieldset.classList.remove('invalid');
  }
  changed();
});
$('previous').addEventListener('click', () => navigate(index - 1));
$('save').addEventListener('click', () => save(false));
$('save-next').addEventListener('click', () => save(true));
window.addEventListener('beforeunload', event => { if (dirty || saving) { event.preventDefault(); event.returnValue = ''; } });
async function loadVersion(id, initial = false) {
  if (saving || loading || (!initial && dirty && !window.confirm('Switch versions and discard unsaved changes? Cancel to save first.'))) return;
  $('load-error').textContent = '';
  loading = true; $('workspace').inert = true;
  try {
    const response = await fetch(`/api/review?version=${encodeURIComponent(id)}`);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Cannot load this version.');
    data = result; version = id;
    const requested = initial && new URLSearchParams(location.search).get('case');
    index = requested ? data.cases.findIndex(c => c.case_id === requested) : -1;
    if (index < 0) index = 0;
    $('sample-info').textContent = `${data.cases.length} reviews · ${data.sample.sampling} · ${data.sample.excluded_generation_failures} generation failures excluded.`;
    $('workspace').hidden = false; render();
    if (!initial) window.scrollTo({top: 0, behavior: 'smooth'});
  } catch (error) { $('load-error').textContent = error.message; }
  finally { loading = false; $('workspace').inert = false; }
}
async function start() {
  try {
    const response = await fetch('/api/versions');
    if (!response.ok) throw new Error('Cannot load coach versions. Check the local server.');
    catalog = await response.json();
    const requested = new URLSearchParams(location.search).get('version');
    await loadVersion(catalog.versions.some(v => v.id === requested) ? requested : catalog.default, true);
  } catch (error) { $('load-error').textContent = error.message; }
}
start();
