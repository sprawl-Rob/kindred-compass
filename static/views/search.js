import { html, useState, useEffect, useRef } from '../vendor/preact-htm.js';
import { api, useStore, setStore, Loading, ErrorBox, Field, CopyButton, toast, errMsg } from '../ui.js';
import { LeadCard } from './research.js';

const ACCESS = { free: 'Free', free_account: 'Free account', subscription: 'Membership / subscription', library: 'Library', onsite: 'In person',
  paid_retrieval: 'Paid research', unknown: 'Access unknown' };

function readParams() {
  const h = location.hash.split('?')[1] || '';
  const p = new URLSearchParams(h);
  return { given: p.get('given') || '', surname: p.get('surname') || '', year_from: p.get('year_from') || '', year_to: p.get('year_to') || '',
    place: p.get('place') || '', keywords: p.get('keywords') || '' };
}

function SourceRow({ l, onMember }) {
  return html`<li class=${'src-row' + (l.mine ? ' mine' : '')}>
    <div class="src-main">
      <a class=${'button small ' + (l.mine ? 'member' : l.free ? '' : 'secondary')} href=${l.url} target="_blank" rel="noopener noreferrer"
        title=${l.note || ''}>${l.prefilled ? 'Search' : 'Open'} ↗</a>
      <div class="src-text"><strong>${l.name}</strong> <span class="muted small">${l.provider && l.provider !== l.name ? l.provider : ''}</span>
        <div class="small muted">${(l.access || []).map((a) => ACCESS[a] || a).join(' · ')}${l.coverage === 'match' ? ' · covers this place and these years' :
          l.coverage === 'partial' ? ' · partly covers this place/years' : ''}${l.prefilled ? ' · opens with your search filled in' : ''}</div>
        ${l.note && !l.prefilled && html`<div class="small">${l.note}</div>`}</div>
    </div>
    <div class="src-actions">
      ${l.copy && html`<${CopyButton} text=${l.copy} small label="Copy search" />`}
      ${l.provider_id && l.membership && html`<label class="check small" title="Tick if you have a membership or subscription here">
        <input type="checkbox" checked=${l.mine} onChange=${(e) => onMember(l.provider_id, e.target.checked)} /> I'm a member</label>`}
    </div>
  </li>`;
}

function useRun(id) {
  const [run, setRun] = useState(null);
  const t = useRef(null);
  useEffect(() => {
    if (!id) { setRun(null); return undefined; }
    let alive = true;
    const load = async () => {
      try {
        const r = await api.get(`/research/runs/${id}`);
        if (!alive) return;
        setRun(r);
        if (r.status === 'running') t.current = setTimeout(load, 1500);
      } catch (e) { /* keep last */ }
    };
    load();
    return () => { alive = false; clearTimeout(t.current); };
  }, [id]);
  return [run, () => setRun({ ...run })];
}

export function Search() {
  const s = useStore();
  const [q, setQ] = useState(readParams);
  const [links, setLinks] = useState(null);
  const [plan, setPlan] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState(null);
  const [run, refreshRun] = useRun(runId);
  const [show, setShow] = useState('good');
  const set = (k) => (e) => setQ({ ...q, [k]: e.target.value });
  const params = () => new URLSearchParams(Object.entries(q).filter(([, v]) => v)).toString();

  const go = async (e) => {
    e && e.preventDefault();
    if (!q.surname.trim()) { toast('Enter at least a surname', 'bad'); return; }
    setBusy(true); setErr(null); setRunId(null);
    history.replaceState(null, '', '#/search?' + params());
    try {
      const [l, p] = await Promise.all([api.get(`/projects/${s.projectId}/discover/links?${params()}`),
        api.post(`/projects/${s.projectId}/discover/plan`, { query: q })]);
      setLinks(l); setPlan(p);
    } catch (x) { setErr(x); }
    setBusy(false);
  };
  useEffect(() => { if (q.surname) go(); }, []);
  const startRun = async () => {
    try { const r = await api.post(`/projects/${s.projectId}/discover/runs`, { query: q }); setRunId(r.id); }
    catch (x) { toast(errMsg(x), 'bad'); }
  };
  const setMember = async (providerId, on) => {
    const subs = new Set((s.prefs && s.prefs.subscriptions) || []);
    on ? subs.add(providerId) : subs.delete(providerId);
    try {
      setStore({ prefs: await api.put('/settings/research-prefs', { subscriptions: [...subs] }) });
      setLinks({ ...links, links: links.links.map((l) => (l.provider_id === providerId ? { ...l, mine: on } : l))
        .sort((a, b) => (b.mine - a.mine)) });
    } catch (x) { toast(errMsg(x), 'bad'); }
  };
  const mine = links ? links.links.filter((l) => l.mine) : [];
  const free = links ? links.links.filter((l) => !l.mine && l.free) : [];
  const other = links ? links.links.filter((l) => !l.mine && !l.free) : [];
  const hits = run ? (run.hits || []).filter((h) => show === 'all' || h.strength !== 'weak') : [];
  const st = run && run.summary && run.summary.stats;
  return html`<div class="page narrow-page">
    <header class="page-head"><div><h1>Search</h1>
      <p class="lede">Search every source for a name — including people who aren't in your tree yet. Anything you find can be added to the tree.</p></div></header>

    <form class="panel search-form" onSubmit=${go}>
      <div class="row wrap">
        <${Field} label="Given name"><input value=${q.given} onInput=${set('given')} placeholder="e.g. John" /><//>
        <${Field} label="Surname"><input required value=${q.surname} onInput=${set('surname')} placeholder="e.g. Petrie" /><//>
        <${Field} label="Years from"><input inputmode="numeric" size="5" value=${q.year_from} onInput=${set('year_from')} /><//>
        <${Field} label="to"><input inputmode="numeric" size="5" value=${q.year_to} onInput=${set('year_to')} /><//>
      </div>
      <div class="row wrap">
        <${Field} label="Place" hint="Town, county, state or country — e.g. Frankfort, Herkimer, New York"><input value=${q.place} onInput=${set('place')} /><//>
        <${Field} label="Keywords (optional)"><input value=${q.keywords} onInput=${set('keywords')} placeholder="e.g. obituary, Ilion" /><//>
      </div>
      <div class="row end"><button type="submit" disabled=${busy}>${busy ? 'Finding sources…' : 'Find sources'}</button></div>
    </form>
    <${ErrorBox} error=${err} />

    ${plan && html`<section class="panel">
      <div class="panel-head"><h2>Let the app search</h2>
        ${!runId ? html`<button disabled=${!plan.queries.length} onClick=${startRun}>Search ${new Set(plan.queries.map((x) => x.adapter)).size} archives now</button>` :
          run && run.status === 'running' ? html`<button class="secondary" onClick=${async () => { await api.post(`/research/runs/${runId}/cancel`); refreshRun(); }}>Stop</button>` : null}</div>
      ${!runId && html`<p class="small">${plan.queries.length ? html`Searches ${[...new Set(plan.queries.map((x) => x.label))].join(', ')} for${' '}${plan.names.map((n, i) => html`${i ? ', ' : ''}<strong>${n}</strong>`)}. Every result is checked against your search and every search is logged.` :
        'None of the archives the app can search covers this place and these years — use the sources below.'}
        ${plan.skipped_archives.length > 0 && html` <span class="muted">Not searched: ${plan.skipped_archives.map((x) => `${x.label} (${x.reason})`).join('; ')}.</span>`}</p>`}
      ${run && html`<div>
        ${run.status === 'running' ? html`<p class="callout tone-info small" role="status">Searching… ${(run.progress || {}).done || 0} of ${(run.progress || {}).total || '?'}
          ${(run.progress || {}).current ? ` — ${run.progress.current}` : ''}. Archives are searched within their rate limits, so this can take a few minutes.</p>` :
          html`<p class="small">${st ? `${st.queries_run} searches, ${st.results_returned} results checked: ${st.strong} strong, ${st.possible} possible.` : run.status}
            ${run.error ? html` <span class="danger">${run.error}</span>` : ''}</p>`}
        ${(run.hits || []).length > 0 && html`<div class="row"><label class="check small"><input type="checkbox" checked=${show === 'all'}
          onChange=${(e) => setShow(e.target.checked ? 'all' : 'good')} /> Show weak results too</label></div>`}
        <div class="lead-list">${hits.map((h) => html`<${LeadCard} h=${h} key=${h.id} onChange=${() => setRunId(runId)} />`)}</div>
        ${run.status !== 'running' && hits.length === 0 && html`<p class="muted small">Nothing promising found by the automatic searches. That doesn't mean no record exists — try the sources below.</p>`}
      </div>`}
    </section>`}

    ${links && html`<section class="panel"><h2>Search these sources</h2>
      <p class="small muted">${links.links.length} sources cover ${links.query.place.short || 'this search'}${links.query.year_from ? ` (${links.query.year_from}–${links.query.year_to || ''})` : ''}.
        Where possible the search opens already filled in; otherwise copy the search and paste it. The app never logs in to these sites for you.</p>
      ${mine.length > 0 && html`<h3>Your memberships</h3><ul class="src-list">${mine.map((l) => html`<${SourceRow} l=${l} onMember=${setMember} />`)}</ul>`}
      ${free.length > 0 && html`<h3>Free</h3><ul class="src-list">${free.map((l) => html`<${SourceRow} l=${l} onMember=${setMember} />`)}</ul>`}
      ${other.length > 0 && html`<h3>Subscription, membership or in person</h3><ul class="src-list">${other.map((l) => html`<${SourceRow} l=${l} onMember=${setMember} />`)}</ul>`}
    </section>`}
  </div>`;
}
