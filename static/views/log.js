import { html, useState, useEffect } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, store, Loading, ErrorBox, Empty, Field, Select, Modal, ExtLink, L, fmtDate, years, toast, errMsg } from '../ui.js';

const OUTCOME_HELP = {
  useful: 'You found a record that helps.',
  possible_match: 'Something that might be your person — identity not yet confirmed.',
  no_result: 'You searched and the index/search returned nothing relevant. This does NOT mean the record does not exist.',
  inaccessible: 'You could not get in (login, paywall, onsite-only, offline).',
  records_unavailable: 'The records themselves do not survive, are restricted, or were never created for this place/time.',
  follow_up: 'Something to come back to.',
};

export function useLookups(projectId) {
  return useAsync(async () => {
    const [persons, questions, dir] = await Promise.all([
      api.get(`/projects/${projectId}/persons`), api.get(`/projects/${projectId}/questions`),
      api.post('/directory/search', { project_id: projectId })]);
    const cols = Object.values(dir.groups).flat().sort((a, b) => (a.provider_name + a.name).localeCompare(b.provider_name + b.name));
    return { persons, questions, collections: cols };
  }, [projectId]);
}

export function Alternatives({ list }) {
  if (!list || !list.length) return null;
  return html`<div class="alternatives">
    <p class="small"><strong>No result in one search doesn't mean the record doesn't exist.</strong> Suggested next steps, and why:</p>
    <ol>${list.map((a) => html`<li><strong>${a.title}</strong>
      <div class="small">${a.reason}</div>
      <div class="small muted">${a.action}${a.collection_id ? html` · <a href=${`#/resource/${a.collection_id}`}>Open resource</a>` : ''}</div></li>`)}</ol></div>`;
}

export function LogEntryForm({ initial = {}, entry, onClose, onSaved }) {
  const s = useStore();
  const look = useLookups(s.projectId);
  const [v, setV] = useState(() => entry ? { ...entry, name_variants: (entry.name_variants || []).join(', ') } : {
    searched_on: new Date().toISOString().slice(0, 10), outcome: '', query_text: '', ...initial,
    name_variants: (initial.name_variants || []).join ? (initial.name_variants || []).join(', ') : initial.name_variants || '' });
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (val) => setV((o) => ({ ...o, [k]: val }));
  const inp = (k) => (e) => set(k)(e.target.value);
  const save = async (e) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    const body = { ...v, name_variants: (v.name_variants || '').split(',').map((x) => x.trim()).filter(Boolean),
      year_from: v.year_from ? +v.year_from : null, year_to: v.year_to ? +v.year_to : null,
      collection_id: v.collection_id || null, person_id: v.person_id || null, question_id: v.question_id || null };
    try {
      const saved = entry ? await api.patch(`/log/${entry.id}`, body) : await api.post(`/projects/${s.projectId}/log`, body);
      toast('Search logged');
      if (!entry && saved.alternatives && saved.alternatives.length) setResult(saved);
      else { onSaved && onSaved(saved); }
    } catch (x) { toast(errMsg(x), 'bad'); }
    setBusy(false);
  };
  if (result) {
    return html`<${Modal} title="Logged — what to try next" onClose=${() => onSaved(result)} wide>
      <p><strong>${L('log_outcomes', result.outcome)}</strong> in ${result.collection_name || result.resource_text}.</p>
      <${Alternatives} list=${result.alternatives} />
      <div class="row end"><button onClick=${() => onSaved(result)}>Done</button></div><//>`;
  }
  const L2 = look.data;
  return html`<${Modal} title=${entry ? 'Edit log entry' : 'Log a search'} onClose=${onClose} wide>
    ${!L2 ? html`<${Loading} />` : html`<form class="stack" onSubmit=${save}>
      <div class="grid-2 tight">
        <${Field} label="Person"><${Select} value=${v.person_id} onChange=${set('person_id')} empty="(none)" options=${L2.persons.map((p) => [p.id, p.display_name])} /><//>
        <${Field} label="Research question"><${Select} value=${v.question_id} onChange=${set('question_id')} empty="(none)"
          options=${L2.questions.filter((q) => !v.person_id || q.person_id === v.person_id).map((q) => [q.id, q.question])} /><//>
        <${Field} label="Resource / collection searched"><${Select} value=${v.collection_id} onChange=${set('collection_id')} empty="(not in directory — describe below)"
          options=${L2.collections.map((c) => [c.id, `${c.provider_name} — ${c.name}`])} /><//>
        ${!v.collection_id && html`<${Field} label="Resource (free text)"><input value=${v.resource_text || ''} onInput=${inp('resource_text')} placeholder="e.g. Town clerk, Fitchburg — letter" /><//>`}
        <${Field} label="Exact query" wide><input value=${v.query_text || ''} onInput=${inp('query_text')} placeholder="What you typed, exactly" /><//>
        <${Field} label="Spelling variants tried" hint="Comma-separated"><input value=${v.name_variants} onInput=${inp('name_variants')} /><//>
        <${Field} label="Filters used"><input value=${v.filters_text || ''} onInput=${inp('filters_text')} placeholder="e.g. birth place = Massachusetts, exact match off" /><//>
        <div class="row tight"><${Field} label="Years from"><input inputmode="numeric" value=${v.year_from || ''} onInput=${inp('year_from')} /><//>
          <${Field} label="to"><input inputmode="numeric" value=${v.year_to || ''} onInput=${inp('year_to')} /><//></div>
        <${Field} label="Place searched"><input value=${v.place_text || ''} onInput=${inp('place_text')} /><//>
        <${Field} label="Date of search"><input type="date" value=${v.searched_on} onInput=${inp('searched_on')} /><//>
      </div>
      <fieldset class="outcomes"><legend>Outcome</legend>
        ${Object.entries(s.meta.vocab.log_outcomes).map(([k, label]) => html`<label class="radio"><input type="radio" name="outcome" value=${k} required checked=${v.outcome === k} onChange=${() => set('outcome')(k)} />
          <span><strong>${label}</strong><br /><span class="small muted">${OUTCOME_HELP[k]}</span></span></label>`)}
      </fieldset>
      <div class="grid-2 tight">
        <${Field} label="Coverage limitations noticed"><textarea rows="2" value=${v.coverage_notes || ''} onInput=${inp('coverage_notes')} placeholder="e.g. index covers only 1850–1852 for this county" /><//>
        <${Field} label="Access limitations"><textarea rows="2" value=${v.access_notes || ''} onInput=${inp('access_notes')} /><//>
        <${Field} label="Link to result / search page"><input type="url" value=${v.result_url || ''} onInput=${inp('result_url')} placeholder="https://" /><//>
        <${Field} label="Citation"><input value=${v.citation_text || ''} onInput=${inp('citation_text')} /><//>
        <${Field} label="Notes" wide><textarea rows="3" value=${v.notes || ''} onInput=${inp('notes')} /><//>
      </div>
      <div class="row end"><button type="button" class="secondary" onClick=${onClose}>Cancel</button><button type="submit" disabled=${busy}>${busy ? 'Saving…' : 'Save log entry'}</button></div>
    </form>`}<//>`;
}

export function ResearchLog({ params }) {
  const s = useStore();
  const [filter, setFilter] = useState({ outcome: params.get('outcome') || '', person_id: params.get('person') || '' });
  const q = new URLSearchParams(Object.entries(filter).filter(([, v]) => v)).toString();
  const { data, error, loading, reload } = useAsync(() => api.get(`/projects/${s.projectId}/log${q ? '?' + q : ''}`), [s.projectId, q]);
  const people = useAsync(() => api.get(`/projects/${s.projectId}/persons`), [s.projectId]);
  const [editing, setEditing] = useState(null);
  const [alts, setAlts] = useState({});
  const showAlts = async (e) => { setAlts({ ...alts, [e.id]: await api.get(`/log/${e.id}/alternatives`) }); };
  const del = async (e) => { if (confirm('Delete this log entry? Negative results are worth keeping.')) { await api.del(`/log/${e.id}`); reload(); } };
  return html`<div class="page">
    <header class="page-head"><div><h1>Research log</h1>
      <p class="lede">Every search — including ones that found nothing. “Searched, no result”, “couldn't access” and “records unavailable” are kept distinct from “not searched yet”.</p></div>
      <div class="row"><button onClick=${() => setEditing({})}>Log a search</button><a class="button secondary" href=${`/api/projects/${s.projectId}/log.csv`} download>Export CSV</a></div></header>
    <div class="row wrap filters-inline">
      <${Field} label="Person"><${Select} value=${filter.person_id} onChange=${(v) => setFilter({ ...filter, person_id: v || '' })} empty="Everyone" options=${(people.data || []).map((p) => [p.id, p.display_name])} /><//>
      <${Field} label="Outcome"><${Select} value=${filter.outcome} onChange=${(v) => setFilter({ ...filter, outcome: v || '' })} empty="Any outcome" options=${s.meta.vocab.log_outcomes} /><//>
    </div>
    <${ErrorBox} error=${error} retry=${reload} />
    ${loading && !data ? html`<${Loading} />` : data && data.length === 0 ? html`<${Empty} title="No searches logged">Log searches as you go — especially the ones with no result, so you don't repeat them and can see what to try next.<//>` :
      data && html`<ul class="log-list">${data.map((e) => html`<li class="log-item">
        <div class="log-head"><span class=${'outcome o-' + e.outcome}>${L('log_outcomes', e.outcome)}</span>
          <strong>${e.collection_name ? html`<a href=${`#/resource/${e.collection_id}`}>${e.collection_name}</a>` : e.resource_text}</strong>
          <span class="muted small">${e.provider_name || ''} · ${fmtDate(e.searched_on)}</span></div>
        <div class="small"><span class="muted">Query:</span> <code>${e.query_text || '—'}</code>
          ${(e.name_variants || []).length ? html` · <span class="muted">variants:</span> ${e.name_variants.join(', ')}` : ''}
          ${e.year_from || e.year_to ? html` · ${years(e.year_from, e.year_to)}` : ''}${e.place_text ? ' · ' + e.place_text : ''}</div>
        ${(e.person_name || e.question_text) && html`<div class="small muted">${[e.person_name, e.question_text].filter(Boolean).join(' — ')}</div>`}
        ${e.filters_text && html`<div class="small"><span class="muted">Filters:</span> ${e.filters_text}</div>`}
        ${e.coverage_notes && html`<div class="small"><span class="muted">Coverage:</span> ${e.coverage_notes}</div>`}
        ${e.access_notes && html`<div class="small"><span class="muted">Access:</span> ${e.access_notes}</div>`}
        ${e.notes && html`<div class="small">${e.notes}</div>`}
        ${e.result_url && html`<${ExtLink} href=${e.result_url} cls="small">Saved link<//>`}
        <div class="row">
          ${['no_result', 'inaccessible', 'records_unavailable'].includes(e.outcome) && html`<button class="small secondary" onClick=${() => showAlts(e)}>What to try next</button>`}
          <button class="small secondary" onClick=${() => setEditing(e)}>Edit</button>
          <button class="small link danger" onClick=${() => del(e)}>Delete</button></div>
        ${alts[e.id] && html`<${Alternatives} list=${alts[e.id]} />`}
      </li>`)}</ul>`}
    ${editing && html`<${LogEntryForm} entry=${editing.id ? editing : null} initial=${{ person_id: filter.person_id || undefined }}
      onClose=${() => setEditing(null)} onSaved=${() => { setEditing(null); reload(); }} />`}
  </div>`;
}
