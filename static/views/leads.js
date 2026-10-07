import { html } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, Loading, ErrorBox, Empty } from '../ui.js';
import { LeadCard } from './research.js';

export function Leads() {
  const s = useStore();
  const { data, error, loading, reload } = useAsync(() => api.get(`/projects/${s.projectId}/research/review`), [s.projectId]);
  if (loading && !data) return html`<div class="page"><${Loading} /></div>`;
  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /></div>`;
  const groups = [];
  data.forEach((h) => { let g = groups.find((x) => x.id === h.person_id); if (!g) groups.push(g = { id: h.person_id, name: h.person_name, hits: [] }); g.hits.push(h); });
  return html`<div class="page narrow-page">
    <header class="page-head"><div><h1>Leads</h1>
      <p class="lede">Records the research runs found that might be about your family. For each one: is it the right person?</p></div></header>
    ${data.length === 0 ? html`<${Empty} title="No leads waiting">Open a person and choose <strong>Research automatically</strong> — anything promising will appear here.<//>` :
      groups.map((g) => html`<section class="lead-group"><h2>${g.id ? html`<a href=${`#/person/${g.id}`}>${g.name}</a>` : 'Found by searches — not in the tree yet'} <span class="muted small">${g.hits.length} lead${g.hits.length > 1 ? 's' : ''}</span></h2>
        <div class="lead-list">${g.hits.map((h) => html`<${LeadCard} h=${h} onChange=${reload} key=${h.id} />`)}</div></section>`)}
    <p class="small muted">“Yes” saves the record as a source for that person (you can link it to a specific fact later). “Not them” removes it and it won't be suggested again.</p>
  </div>`;
}
