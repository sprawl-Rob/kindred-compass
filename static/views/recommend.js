import { html, useState } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, Loading, ErrorBox, Empty, Field, Select, Badges, ExtLink, CopyButton, L, toast, errMsg, nav } from '../ui.js';
import { LogEntryForm, Alternatives } from './log.js';
import { ProviderSearchPanel, LiveSearchPanel } from './explorer.js';

function RecCard({ r, onLog, onTask, personQuery }) {
  const [open, setOpen] = useState(null);
  const c = r.collection;
  const sq = r.suggested_query;
  const queryText = [sq.text, sq.variants.length ? `(variants: ${sq.variants.join(', ')})` : ''].filter(Boolean).join(' ');
  return html`<article class="card rec-card">
    <div class="card-top"><div><h3>${r.headline}</h3>
      <div class="muted small"><a href=${`#/resource/${c.id}`}>${c.name}</a> · ${c.provider_name}</div></div>
      <span class="rank" title="Orders suggestions by fit to your question. Not a probability that a record exists.">${r.rank_points} rank pts</span></div>
    <${Badges} list=${c.badges} />
    <p>${r.coverage_sentence}</p>
    <div class="grid-2 tight small">
      <div><h4>Why it's relevant</h4><ul>${r.why.map((w) => html`<li>${w}</li>`)}</ul>
        <h4>Question it may answer</h4><p>${r.question_it_may_answer}</p></div>
      <div><h4>Coverage for your search</h4><p>${r.coverage.window.place || 'Any place'} · ${r.coverage.window.years || 'any years'}<br /><span class="muted">${r.coverage.window.basis}</span></p>
        <h4>Access</h4><p>Search: ${r.access.search}<br />Images: ${r.access.images}<br />Copies: ${r.access.copies}</p>
        <h4>How you can search it</h4><p>${r.search_methods.join(' · ')}</p></div>
    </div>
    ${sq.text && html`<div class="suggested"><span class="small muted">Suggested query</span> <code>${sq.text}</code> <${CopyButton} text=${queryText} small label="Copy query" />
      ${sq.variants.length > 0 && html`<div class="small">Name variants to try: ${sq.variants.join(', ')}</div>`}</div>`}
    ${r.uncertainty.length > 0 && html`<details class="uncertainty"><summary>Uncertainty (${r.uncertainty.length})</summary><ul class="small">${r.uncertainty.map((u) => html`<li>${u}</li>`)}</ul></details>`}
    ${r.history_note && html`<p class="small callout tone-info">${r.history_note}</p>`}
    ${r.overlap_notes.map((o) => html`<p class="small callout tone-info">${o}</p>`)}
    <div class="next-action"><strong>Next action:</strong> ${r.next_action.label}. <span class="small">${r.next_action.detail}</span></div>
    <div class="row wrap">
      ${r.next_action.kind === 'live_search' ? html`<button onClick=${() => setOpen(open === 'live' ? null : 'live')}>Run live search</button>` : null}
      <button class=${r.next_action.kind === 'live_search' ? 'secondary' : ''} onClick=${() => setOpen(open === 'open' ? null : 'open')}>Open provider search…</button>
      <button class="secondary" onClick=${() => onLog(r)}>Log this search</button>
      <button class="secondary" onClick=${() => onTask(r)}>Add to to-do</button>
    </div>
    ${open === 'open' && html`<${ProviderSearchPanel} c=${{ ...c, search_url_template: c.search_url_template }} defaultQuery=${personQuery(r)} />`}
    ${open === 'live' && html`<${LiveSearchPanel} c=${c} defaultQuery=${{ q: (sq.given[0] || '') + ' ' + (sq.surname[0] || ''), year_from: personQuery(r).year_from, year_to: personQuery(r).year_to }} />`}
  </article>`;
}

export function NextSearches({ params }) {
  const s = useStore();
  const [sel, setSel] = useState({ person_id: params.get('person') || '', question_id: params.get('question') || '' });
  const [prefs, setPrefs] = useState({ access: s.prefs && s.prefs.access, remote_only: s.prefs && s.prefs.remote_only });
  const [logFor, setLogFor] = useState(null);
  const [showHidden, setShowHidden] = useState(false);
  const people = useAsync(() => api.get(`/projects/${s.projectId}/persons`), [s.projectId]);
  const questions = useAsync(() => api.get(`/projects/${s.projectId}/questions`), [s.projectId]);
  const ready = sel.person_id || sel.question_id;
  const { data, error, loading, reload } = useAsync(() => ready ? api.post(`/projects/${s.projectId}/recommendations`,
    { ...sel, prefs: { access: prefs.access || null, remote_only: !!prefs.remote_only } }) : Promise.resolve(null),
  [s.projectId, sel.person_id, sel.question_id, prefs.access, prefs.remote_only]);

  if (data && data.person && !sel.person_id) setTimeout(() => setSel((o) => ({ ...o, person_id: data.person.id })), 0);
  const personQuery = (r) => {
    const sq = r.suggested_query; const w = r.coverage.window; const [a, b] = (w.years || '').split('–');
    return { given: sq.given[0] || '', surname: sq.surname[0] || '', year_from: /^\d+$/.test(a) ? a : '', year_to: /^\d+$/.test(b || a) ? (b || a) : '' };
  };
  const addTask = async (r) => {
    try {
      await api.post(`/projects/${s.projectId}/tasks`, { title: r.headline, person_id: data.person && data.person.id, question_id: sel.question_id || null,
        collection_id: r.collection.id, origin: 'recommendation', notes: r.why.join('\n') });
      toast('Added to to-do list');
    } catch (x) { toast(errMsg(x), 'bad'); }
  };
  const qList = (questions.data || []).filter((q) => !sel.person_id || q.person_id === sel.person_id);
  return html`<div class="page">
    <header class="page-head"><div><h1>Next searches</h1>
      <p class="lede">Explainable suggestions from this app's directory, matched to your person, question, places and years. No AI is used here.</p></div></header>
    <div class="row wrap filters-inline">
      <${Field} label="Person"><${Select} value=${sel.person_id} onChange=${(v) => setSel({ person_id: v || '', question_id: '' })} empty="Choose a person"
        options=${(people.data || []).map((p) => [p.id, p.display_name])} /><//>
      <${Field} label="Research question"><${Select} value=${sel.question_id} onChange=${(v) => setSel({ ...sel, question_id: v || '' })} empty="(general)"
        options=${qList.map((q) => [q.id, q.question])} /><//>
      <${Field} label="Access"><${Select} value=${prefs.access} onChange=${(v) => setPrefs({ ...prefs, access: v })} empty="Show all"
        options=${{ free: 'Free only', free_or_account: 'Free or free account', my_access: 'Free + my subscriptions' }} /><//>
      <label class="check"><input type="checkbox" checked=${!!prefs.remote_only} onChange=${(e) => setPrefs({ ...prefs, remote_only: e.target.checked })} /> Remote only</label>
    </div>
    ${!ready && html`<${Empty} title="Choose a person or a question">Suggestions use the person's names, approximate dates and places, your question, and what you've already searched.<//>`}
    <${ErrorBox} error=${error} retry=${reload} />
    ${ready && loading && !data && html`<${Loading} what="Finding relevant collections" />`}
    ${data && html`
      ${data.warnings.map((w) => html`<div class="callout tone-info">${w}</div>`)}
      ${data.person && data.person.living_status !== 'deceased' && html`<div class="callout tone-muted small">This person may be living. Records about living people are often restricted, and many indexes exclude them.</div>`}
      <section class="panel subtle"><h2 class="h3">Based on</h2>
        <ul class="small">${data.windows.map((w) => html`<li><strong>${w.place || 'Place not given'}</strong>, ${w.years} — ${w.basis}</li>`)}</ul>
        <p class="small muted">Record types prioritised for “${data.purpose}”: ${data.record_types_considered.slice(0, 8).map((r) => r.label).join(', ')}.</p>
        <p class="small muted">${data.score_note}</p></section>
      ${data.alternatives.length > 0 && html`<section class="panel"><h2>After your unsuccessful searches</h2>
        ${data.alternatives.map((a) => html`<div class="alt-block"><p><span class=${'outcome o-' + a.outcome}>${a.outcome_label}</span> in <strong>${a.searched}</strong> (${a.searched_on})</p>
          <${Alternatives} list=${a.suggestions} /></div>`)}</section>`}
      <h2>Recommended next searches (${data.recommendations.length}${data.more_available ? '+' : ''})</h2>
      ${data.recommendations.length === 0 && html`<${Empty} title="No matching collections in the directory">The directory is incomplete. Try the FamilySearch Research Wiki for this place, or add a local repository in Directory.<//>`}
      <div class="rec-list">${data.recommendations.map((r) => html`<${RecCard} r=${r} personQuery=${personQuery} onTask=${addTask}
        onLog=${() => setLogFor({ collection_id: r.collection.id, person_id: data.person && data.person.id, question_id: sel.question_id || undefined,
          query_text: r.suggested_query.text, ...((q) => ({ year_from: q.year_from, year_to: q.year_to }))(personQuery(r)), place_text: r.coverage.window.place })} />`)}</div>
      ${data.guidance.length > 0 && html`<section class="panel"><h2>Guidance & catalogs for this place</h2><ul class="list">${data.guidance.map((g) => html`<li>
        <div class="list-main"><a href=${`#/resource/${g.collection.id}`}>${g.collection.name}</a> <span class="muted small">${g.collection.provider_name}</span>
        <div class="small">${g.why.join(' · ')}</div></div><${ExtLink} href=${g.collection.url} cls="small">Open<//></li>`)}</ul></section>`}
      ${data.already_searched.length > 0 && html`<section class="panel"><h2>Already searched</h2><ul class="list">${data.already_searched.map((r) => html`<li>
        <div class="list-main"><a href=${`#/resource/${r.collection.id}`}>${r.collection.name}</a><div class="small">${r.history_note}</div></div></li>`)}</ul></section>`}
      ${data.hidden_by_preferences.length > 0 && html`<section class="panel subtle"><h2>Hidden by your access filters (${data.hidden_by_preferences.length})</h2>
        <p class="small">These may still hold the record. <button class="link" onClick=${() => setShowHidden(!showHidden)}>${showHidden ? 'Hide' : 'Show'} them</button></p>
        ${showHidden && html`<div class="rec-list">${data.hidden_by_preferences.map((r) => html`<div><p class="small"><strong>${r.hidden_reason}</strong></p>
          <${RecCard} r=${r} personQuery=${personQuery} onTask=${addTask} onLog=${() => setLogFor({ collection_id: r.collection.id, person_id: data.person && data.person.id })} /></div>`)}</div>`}</section>`}
    `}
    ${logFor && html`<${LogEntryForm} initial=${logFor} onClose=${() => setLogFor(null)} onSaved=${() => { setLogFor(null); reload(); }} />`}
  </div>`;
}
