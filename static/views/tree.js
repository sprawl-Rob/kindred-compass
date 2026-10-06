import { html, useState } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, Loading, ErrorBox, Empty, toast, errMsg, nav } from '../ui.js';
import { PersonLink } from './person.js';

function Box({ n, isRoot }) {
  if (!n) return html`<div class="ped-box empty"><span class="muted small">Unknown</span></div>`;
  return html`<div class=${'ped-box' + (isRoot ? ' root' : '') + ((n.sex || '').startsWith('F') ? ' f' : (n.sex || '').startsWith('M') ? ' m' : '')}>
    <a class="ped-name" href=${`#/person/${n.id}`}>${n.name}</a>
    <span class="ped-life">${n.lifespan || ''}</span>
    ${n.birth_place && html`<span class="ped-place">${n.birth_place}</span>`}
    ${!isRoot && html`<a class="ped-center small" href=${`#/tree/${n.id}`} title=${`Show ${n.name}'s ancestors`} aria-label=${`Centre tree on ${n.name}`}>⤢</a>`}
  </div>`;
}

function Ped({ n, depth, isRoot }) {
  const parents = n ? n.parents : [];
  const showParents = depth > 0;
  return html`<div class="ped">
    <div class="ped-self"><${Box} n=${n} isRoot=${isRoot} />
      ${n && n.has_more && html`<a class="ped-more small" href=${`#/tree/${n.id}`}>more ›</a>`}</div>
    ${showParents && n && (parents.length > 0 || depth > 0) && html`<div class="ped-parents">
      ${parents.length === 0 ? html`<div class="ped"><div class="ped-self"><a class="ped-box empty find" href=${`#/person/${n.id}`}>+ Find parents</a></div></div>` :
        parents.map((p) => html`<${Ped} n=${p} depth=${depth - 1} />`)}
      ${parents.length === 1 && html`<div class="ped"><div class="ped-self"><a class="ped-box empty find" href=${`#/person/${n.id}`}>+ Find other parent</a></div></div>`}
    </div>`}
  </div>`;
}

export function Tree({ id }) {
  const s = useStore();
  const [depth, setDepth] = useState(4);
  const [q, setQ] = useState('');
  const { data: d, error, loading, reload } = useAsync(() => api.get(`/projects/${s.projectId}/tree?depth=${depth}${id ? '&root=' + id : ''}`), [s.projectId, id, depth]);
  if (loading && !d) return html`<div class="page"><${Loading} /></div>`;
  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /></div>`;
  if (!d.pedigree) return html`<div class="page"><${Empty} title="No people yet"><a class="button" href="#/import">Import a family tree</a><//></div>`;
  const root = d.pedigree;
  const matches = q.length > 1 ? d.people.filter((p) => p.name.toLowerCase().includes(q.toLowerCase())).slice(0, 12) : [];
  const makeHome = async () => { try { await api.put(`/projects/${s.projectId}/tree/home`, { person_id: root.id }); toast(`${root.name} is now the home person`); reload(); } catch (x) { toast(errMsg(x), 'bad'); } };
  return html`<div class="page wide-page">
    <header class="page-head"><div><h1>Family tree</h1>
      <p class="lede">${root.name}'s ancestors. Click a name to open their record checklist, or ⤢ to move the tree to them.</p></div>
      <div class="tree-tools">
        <div class="find-person"><label class="sr-only" for="tree-find">Find a person</label>
          <input id="tree-find" type="search" placeholder="Find a person…" value=${q} onInput=${(e) => setQ(e.target.value)} autocomplete="off" />
          ${matches.length > 0 && html`<ul class="find-results">${matches.map((p) => html`<li><a href=${`#/tree/${p.id}`} onClick=${() => setQ('')}>${p.name} <span class="muted small">${p.lifespan}</span></a></li>`)}</ul>`}</div>
        <label class="small">Generations <select value=${depth} onChange=${(e) => setDepth(+e.target.value)}>${[2, 3, 4, 5].map((n) => html`<option value=${n} selected=${n === depth}>${n + 1}</option>`)}</select></label>
        ${d.home !== root.id ? html`<button class="small secondary" onClick=${makeHome}>Make home person</button>` : html`<span class="badge tone-good">Home person</span>`}
      </div></header>
    <div class="ped-scroll"><${Ped} n=${root} depth=${depth} isRoot=${true} /></div>
    <div class="grid-2 tree-family">
      ${d.spouses.length > 0 && html`<section class="panel"><h2>${d.spouses.length > 1 ? 'Spouses' : 'Spouse'}</h2><div class="fam-list">${d.spouses.map((p) => html`<${PersonLink} p=${p} />`)}</div></section>`}
      ${d.children.length > 0 && html`<section class="panel"><h2>Children</h2><div class="fam-list">${d.children.map((p) => html`<${PersonLink} p=${p} />`)}</div></section>`}
      ${d.siblings.length > 0 && html`<section class="panel"><h2>Brothers & sisters</h2><div class="fam-list">${d.siblings.map((p) => html`<${PersonLink} p=${p} />`)}</div></section>`}
    </div>
  </div>`;
}
