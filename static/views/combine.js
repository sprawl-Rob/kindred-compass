import { html, useState, useEffect } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, Loading, ErrorBox, toast, errMsg, nav } from '../ui.js';

const LEVEL = { high: ['Same person', 'tone-good'], possible: ['Probably the same', 'tone-info'], conflict: ['Same family, but a date disagrees', 'tone-warn'] };

function PairRow({ p, checked, onToggle }) {
  const [label, tone] = LEVEL[p.level] || ['Your choice', 'tone-muted'];
  return html`<li class=${'pair' + (checked ? ' on' : '')}>
    <label class="pair-check"><input type="checkbox" checked=${checked} onChange=${onToggle} />
      <span class="sr-only">Same person: ${p.source.name} and ${p.target.name}</span></label>
    <div class="pair-people">
      <div><strong>${p.source.name}</strong> <span class="muted small">${p.source.lifespan || ''}${p.source.birth_place ? ' · ' + p.source.birth_place : ''}</span></div>
      <div class="pair-arrow" aria-hidden="true">=</div>
      <div><strong>${p.target.name}</strong> <span class="muted small">${p.target.lifespan || ''}${p.target.birth_place ? ' · ' + p.target.birth_place : ''}</span></div>
    </div>
    <div class="pair-why small"><span class=${'badge ' + tone}>${label}</span> ${(p.reasons || []).join(' · ')}</div>
  </li>`;
}

export function Combine() {
  const s = useStore();
  const target = s.projects.find((p) => p.id === s.projectId);
  const others = s.projects.filter((p) => p.id !== s.projectId && !p.is_demo);
  const [source, setSource] = useState('');
  const [sel, setSel] = useState({});
  const [manual, setManual] = useState([]);
  const [m, setM] = useState({ s: '', t: '' });
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const sg = useAsync(() => (source ? api.get(`/projects/${s.projectId}/combine/suggest?source=${source}`) : Promise.resolve(null)), [source, s.projectId]);
  const runs = useAsync(() => api.get(`/projects/${s.projectId}/combine/runs`), [s.projectId, done]);
  useEffect(() => {
    if (sg.data) setSel(Object.fromEntries(sg.data.pairs.map((p) => [p.source.id, p.recommended ? p.target.id : null])));
    setManual([]);
  }, [sg.data]);
  if (!target) return html`<div class="page"><p>Choose a project first.</p></div>`;
  const pairs = sg.data ? sg.data.pairs : [];
  const chosen = [...pairs.filter((p) => sel[p.source.id]).map((p) => ({ source: p.source.id, target: p.target.id })), ...manual.map((x) => ({ source: x.s.id, target: x.t.id }))];
  const usedS = new Set(chosen.map((c) => c.source));
  const usedT = new Set(chosen.map((c) => c.target));
  const go = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/projects/${s.projectId}/combine`, { source_project_id: source, pairs: chosen });
      setDone(r); toast('Trees combined');
    } catch (x) { toast(errMsg(x), 'bad'); }
    setBusy(false);
  };
  const undo = async (id) => {
    if (!confirm('Undo this combine? Everything it added to this tree is removed; the other tree is unchanged.')) return;
    try { await api.post(`/combine/${id}/undo`); toast('Combine undone'); setDone(null); runs.reload(); } catch (x) { toast(errMsg(x), 'bad'); }
  };
  const srcName = (others.find((p) => p.id === source) || {}).name;
  return html`<div class="page narrow-page">
    <header class="page-head"><div><h1>Combine trees</h1>
      <p class="lede">Bring another tree into <strong>${target.name}</strong> — for example your mother's side into your father's tree.
        People who appear in both are joined into one person, so the two families connect.</p></div></header>

    ${done ? html`<section class="panel"><h2>Done</h2>
      <p>${done.stats.people_added} people added, ${done.stats.people_merged} joined with people already here,
        ${done.stats.facts_added} facts and ${done.stats.relationships_added} relationships added
        (${done.stats.facts_already_there + done.stats.relationships_already_there} were already here and weren't duplicated), ${done.stats.sources_added} sources.</p>
      <p class="small muted">“${done.source_name}” is unchanged. Once you're happy with the result you can delete it under More → Settings → Data.</p>
      <div class="row wrap"><a class="button" href="#/tree">Open the family tree</a>
        <button class="secondary" onClick=${() => undo(done.id)}>Undo this combine</button></div></section>` : html`

    <section class="panel"><h2>1. Choose the tree to bring in</h2>
      ${others.length === 0 ? html`<p class="muted">There's no other tree yet. Import one first (More → Import a tree), then come back.</p>` :
        html`<select value=${source} onChange=${(e) => { setSource(e.target.value); }} aria-label="Tree to bring in">
          <option value="">Choose a tree…</option>${others.map((p) => html`<option value=${p.id}>${p.name}</option>`)}</select>`}
    </section>

    ${source && html`<section class="panel"><h2>2. Who is the same person in both?</h2>
      ${sg.error ? html`<${ErrorBox} error=${sg.error} />` : !sg.data || sg.loading ? html`<${Loading} what="Comparing the trees" />` : html`
        <p class="small">Compared ${sg.data.source_people} people in “${srcName}” with ${sg.data.target_people} here, using names (including nicknames and spellings),
          dates, birthplaces and whether their relatives match. <strong>Ticked pairs will be joined.</strong> Check the ones that aren't ticked — only you can confirm them.</p>
        ${pairs.length === 0 && html`<p class="callout tone-warn">No one obviously appears in both trees. Pair at least one person below (e.g. a parent who is in both), or the trees will sit side by side unconnected.</p>`}
        <ul class="pair-list">${pairs.map((p) => html`<${PairRow} p=${p} checked=${!!sel[p.source.id]}
          onToggle=${() => setSel({ ...sel, [p.source.id]: sel[p.source.id] ? null : p.target.id })} />`)}
          ${manual.map((x, i) => html`<${PairRow} p=${{ source: x.s, target: x.t, level: 'manual', reasons: ['added by you'] }} checked=${true}
            onToggle=${() => setManual(manual.filter((_, j) => j !== i))} />`)}</ul>
        <details class="manual-pair"><summary>Pair two people yourself</summary>
          <div class="row wrap">
            <select value=${m.s} onChange=${(e) => setM({ ...m, s: e.target.value })} aria-label=${`Person in ${srcName}`}>
              <option value="">In “${srcName}”…</option>${sg.data.source.filter((p) => !usedS.has(p.id)).map((p) => html`<option value=${p.id}>${p.name} ${p.lifespan || ''}</option>`)}</select>
            <span>=</span>
            <select value=${m.t} onChange=${(e) => setM({ ...m, t: e.target.value })} aria-label=${`Person in ${target.name}`}>
              <option value="">In this tree…</option>${sg.data.target.filter((p) => !usedT.has(p.id)).map((p) => html`<option value=${p.id}>${p.name} ${p.lifespan || ''}</option>`)}</select>
            <button class="small" disabled=${!m.s || !m.t} onClick=${() => {
              const sp = sg.data.source.find((p) => p.id === m.s); const tp = sg.data.target.find((p) => p.id === m.t);
              setSel({ ...sel, [m.s]: null }); setManual([...manual, { s: sp, t: tp }]); setM({ s: '', t: '' });
            }}>Add pair</button></div></details>
      `}</section>`}

    ${source && sg.data && !sg.loading && html`<section class="panel"><h2>3. Combine</h2>
      <p>${sg.data.source_people - chosen.length} people will be added and ${chosen.length} joined with people already in this tree.
        Facts that are exactly the same aren't duplicated; facts that differ are kept side by side so you can compare them.</p>
      <p class="small muted">“${srcName}” itself isn't changed, and you can undo this afterwards.</p>
      <button disabled=${busy} onClick=${go}>${busy ? 'Combining…' : `Combine into ${target.name}`}</button></section>`}
    `}

    ${(runs.data || []).length > 0 && html`<section class="panel"><h2>Earlier combines into this tree</h2><ul class="list">${runs.data.map((r) => html`<li>
      <div class="list-main">${r.source_name} <span class="muted small">${new Date(r.created_at).toLocaleString()} · ${(r.stats || {}).people_added || 0} added, ${(r.stats || {}).people_merged || 0} joined
        ${r.undone_at ? ' · undone' : ''}</span></div>
      ${!r.undone_at && html`<button class="small secondary" onClick=${() => undo(r.id)}>Undo</button>`}</li>`)}</ul></section>`}
  </div>`;
}
