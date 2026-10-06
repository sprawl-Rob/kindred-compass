import { html } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, Loading, ErrorBox, Empty } from '../ui.js';
import { PersonLink, AutoSearch } from './person.js';

function Step({ o }) {
  const it = o.item;
  const e = it.expect || {};
  const main = (it.searches || []).filter((l) => !l.alt);
  return html`<li class="step">
    <div class="step-main">
      <div><${PersonLink} p=${o.person} /> <span class="step-rel muted small">${o.generation === 0 ? 'home person' : o.generation === 1 ? 'parent' : o.generation === 2 ? 'grandparent' : o.generation ? `${'great-'.repeat(o.generation - 2)}grandparent` : 'relative'}</span></div>
      <div class="step-title"><strong>${it.title}</strong> <span class="muted small">— ${it.why}</span></div>
      ${(e.place || e.age) && html`<div class="small">Look in ${e.place ? html`<strong>${e.place}</strong>` : 'an unknown place'}${e.age ? `, age about ${e.age}` : ''}
        ${(e.household || []).length > 0 && html` · with ${e.household.slice(0, 3).map((h) => h.name).join(', ')}`}</div>`}
    </div>
    <div class="step-actions">
      ${it.auto && html`<${AutoSearch} auto=${it.auto} personId=${o.person.id} label="Search now (free)" />`}
      ${main.slice(0, 2).map((l) => html`<a class=${'button small ' + (l.free ? '' : 'secondary')} href=${l.url} target="_blank" rel="noopener noreferrer">${l.site} ↗</a>`)}
      <a class="button small secondary" href=${`#/person/${o.person.id}`}>Checklist</a>
    </div></li>`;
}

function BrickWall({ o }) {
  const paths = (o.item.paths || []).filter((p) => p.status !== 'found').slice(0, 3);
  return html`<a class="card brick-card" href=${`#/person/${o.person.id}`}>
    <strong>${o.person.name}</strong><span class="muted small">${[o.person.lifespan, o.person.birth_place].filter(Boolean).join(' · ')}</span>
    <span class="small">${paths.length ? 'Try: ' + paths.map((p) => p.title.replace(/ — .*/, '')).join(' · ') : 'Reread the records you have for parents’ names'}</span></a>`;
}

export function Home() {
  const s = useStore();
  const { data: d, error, loading, reload } = useAsync(() => api.get(`/projects/${s.projectId}/home`), [s.projectId]);
  if (loading && !d) return html`<div class="page"><${Loading} what="Looking through your tree" /></div>`;
  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /></div>`;
  const proj = s.projects.find((p) => p.id === s.projectId) || {};
  if (!d.people) return html`<div class="page"><h1>${proj.name}</h1><${Empty} title="No people yet">
    <p>Bring in your family tree from Ancestry (or any GEDCOM file), or add a person by hand.</p>
    <p class="row"><a class="button" href="#/import">Import a family tree</a><a class="button secondary" href="#/people">Add a person</a></p><//></div>`;
  return html`<div class="page home">
    <header class="page-head"><div><h1>What to research next</h1>
      <p class="lede">${d.people} people in ${proj.name}. Suggestions start from ${d.root ? html`<${PersonLink} p=${d.root} />` : 'your tree'} and work back through their ancestors —
        <a href="#/tree">change the home person</a>.</p></div></header>

    ${d.leads_waiting > 0 && html`<a class="callout tone-info leads-banner" href="#/leads"><strong>${d.leads_waiting} possible record${d.leads_waiting > 1 ? 's' : ''} found</strong>
      for your family — decide whether each is the right person →</a>`}

    ${d.brick_walls.length > 0 && html`<section class="panel"><h2>Brick walls: ancestors with no parents yet</h2>
      <p class="small muted">The furthest-back people on your direct line. Each one's page lists the records most likely to name their parents.</p>
      <div class="cards">${d.brick_walls.map((o) => html`<${BrickWall} o=${o} />`)}</div></section>`}

    <section class="panel"><h2>Records to find</h2>
      <p class="small muted">Records your tree doesn't have yet, closest relatives first. Each search opens with the name, birth years and place filled in.
        FamilySearch is free with an account; Ancestry needs a subscription.</p>
      ${d.next_steps.length === 0 ? html`<p class="muted">Nothing obvious is missing.</p>` : html`<ul class="steps-list">${d.next_steps.map((o) => html`<${Step} o=${o} />`)}</ul>`}
    </section>

    ${d.runs.length > 0 && html`<section class="panel"><h2>Recent research runs</h2><ul class="list">${d.runs.map((r) => {
      const st = (r.summary || {}).stats || {};
      return html`<li><div class="list-main"><a href=${`#/research/${r.id}`}>${r.person_name || 'Run'}</a> <span class="muted small">${r.mode === 'ai' ? 'AI assistant' : 'automatic'} · ${r.status} · ${new Date(r.started_at).toLocaleDateString()}</span></div>
        <span class="small">${r.mode === 'ai' ? `${st.findings || 0} findings` : `${st.strong || 0} strong, ${st.possible || 0} possible`}</span></li>`; })}</ul></section>`}
  </div>`;
}
