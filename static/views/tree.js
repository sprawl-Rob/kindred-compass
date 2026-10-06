import { html, useState, useEffect, useLayoutEffect, useRef } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, Loading, ErrorBox, Empty, toast, errMsg, safeStorage } from '../ui.js';
import { PersonLink } from './person.js';

const GEN_OPTIONS = ['1', '2', '3', '4', '5', '6', 'full'];

function Box({ n, isRoot, compact }) {
  if (!n) return html`<div class="ped-box empty"><span class="muted small">Unknown</span></div>`;
  const sex = (n.sex || '').startsWith('F') ? ' f' : (n.sex || '').startsWith('M') ? ' m' : '';
  return html`<div class=${'ped-box' + (isRoot ? ' root' : '') + sex + (compact ? ' compact' : '') + (n.repeat ? ' repeat' : '')}>
    <a class="ped-name" href=${`#/person/${n.id}`}>${n.name}</a>
    <span class="ped-life">${n.lifespan || ''}</span>
    ${!compact && n.birth_place && html`<span class="ped-place">${n.birth_place}</span>`}
    ${n.repeat && html`<span class="ped-repeat" title="This ancestor appears more than once in the tree; their ancestors are shown at their first appearance">↻ appears more than once</span>`}
    ${!isRoot && html`<a class="ped-center small" href=${`#/tree/${n.id}`} title=${`Show ${n.name}'s ancestors`} aria-label=${`Centre tree on ${n.name}`}>⤢</a>`}
  </div>`;
}

function Ped({ n, depth, isRoot, compact, full }) {
  const parents = n ? n.parents : [];
  const expanded = parents.length > 0;
  const placeholders = !full && depth > 0 && !n.repeat && !n.has_more;
  return html`<div class="ped">
    <div class="ped-self"><${Box} n=${n} isRoot=${isRoot} compact=${compact} />
      ${n.has_more && !n.repeat && html`<a class="ped-more small" href=${`#/tree/${n.id}`} title="Show more generations from here">more ›</a>`}</div>
    ${(expanded || placeholders) && html`<div class="ped-parents">
      ${!expanded ? html`<div class="ped"><div class="ped-self"><a class=${'ped-box empty find' + (compact ? ' compact' : '')} href=${`#/person/${n.id}`}>+ Find parents</a></div></div>` :
        parents.map((p) => html`<${Ped} n=${p} depth=${depth - 1} compact=${compact} full=${full} />`)}
      ${parents.length === 1 && !full && html`<div class="ped"><div class="ped-self"><a class=${'ped-box empty find' + (compact ? ' compact' : '')} href=${`#/person/${n.id}`}>+ Find other parent</a></div></div>`}
    </div>`}
  </div>`;
}

// A view that scales its content to fit, with zoom buttons, Ctrl/⌘ + scroll to zoom, and drag to pan.
function ZoomView({ children, contentKey }) {
  const outer = useRef(null);
  const inner = useRef(null);
  const [nat, setNat] = useState({ w: 0, h: 0 });
  const [z, setZ] = useState(1);
  const [fitMode, setFitMode] = useState('auto');   // 'auto' | 'all' | 'width' | null (manual zoom)
  const [height, setHeight] = useState(560);
  const drag = useRef(null);

  const viewportHeight = () => {
    const el = outer.current;
    if (!el) return 560;
    return Math.max(320, Math.round(window.innerHeight - el.getBoundingClientRect().top - 24));
  };
  const fitZoom = (mode = fitMode, n = nat) => {
    const el = outer.current;
    if (!el || !n.w) return 1;
    const width = Math.min(1, (el.clientWidth - 14) / n.w);
    const all = Math.min(width, (viewportHeight() - 14) / n.h);
    // 'auto': show everything if it stays readable, otherwise fill the width and scroll down
    // 'auto': the whole tree if it stays readable; else fill the width; on small screens start readable and drag around
    const z = mode === 'width' ? width : mode === 'all' ? all : (all >= 0.4 ? all : width >= 0.4 ? width : Math.min(1, 0.55));
    return Math.max(0.08, z);
  };
  useLayoutEffect(() => {
    const el = inner.current;
    if (!el) return undefined;
    const measure = () => setNat({ w: el.offsetWidth, h: el.offsetHeight });
    measure();
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    if (ro) ro.observe(el);
    return () => ro && ro.disconnect();
  }, [contentKey]);
  useEffect(() => { setFitMode('auto'); centred.current = false; }, [contentKey]);
  // When a tree first appears, bring the starting person into view (in a tall tree they sit halfway down).
  const centred = useRef(false);
  useEffect(() => {
    const el = outer.current;
    if (!el || !nat.w || centred.current) return;
    const rootBox = el.querySelector('.ped-box.root');
    if (!rootBox) return;
    requestAnimationFrame(() => {
      const vr = el.getBoundingClientRect();
      const br = rootBox.getBoundingClientRect();
      el.scrollTop += (br.top + br.height / 2) - (vr.top + el.clientHeight / 2);
      el.scrollLeft = 0;
      centred.current = true;
    });
  }, [z, nat.w, nat.h, contentKey]);
  useEffect(() => {
    const onResize = () => { setHeight(viewportHeight()); if (fitMode) setZ(fitZoom()); };
    onResize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [nat.w, nat.h, fitMode]);

  const zoomTo = (nz, cx, cy) => {
    const el = outer.current;
    nz = Math.max(0.08, Math.min(2, nz));
    if (el) {
      // keep the point under the cursor (or the centre) in place
      const px = cx ?? el.clientWidth / 2;
      const py = cy ?? el.clientHeight / 2;
      const ux = (el.scrollLeft + px) / z;
      const uy = (el.scrollTop + py) / z;
      requestAnimationFrame(() => { el.scrollLeft = ux * nz - px; el.scrollTop = uy * nz - py; });
    }
    setFitMode(null);
    setZ(nz);
  };
  const onWheel = (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    const r = outer.current.getBoundingClientRect();
    zoomTo(z * (e.deltaY < 0 ? 1.12 : 1 / 1.12), e.clientX - r.left, e.clientY - r.top);
  };
  const onDown = (e) => {
    if (e.button !== 0 || e.target.closest('a, button, input, select')) return;
    const el = outer.current;
    drag.current = { x: e.clientX, y: e.clientY, l: el.scrollLeft, t: el.scrollTop };
    el.setPointerCapture && el.setPointerCapture(e.pointerId);
    el.classList.add('dragging');
  };
  const onMove = (e) => {
    const d = drag.current;
    if (!d) return;
    const el = outer.current;
    el.scrollLeft = d.l - (e.clientX - d.x);
    el.scrollTop = d.t - (e.clientY - d.y);
  };
  const onUp = () => { drag.current = null; outer.current && outer.current.classList.remove('dragging'); };
  useEffect(() => {
    const el = outer.current;
    if (!el) return undefined;
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  });

  return html`<div class="zoom-wrap">
    <div class="zoom-bar" role="toolbar" aria-label="Zoom">
      <button class="small secondary" onClick=${() => zoomTo(z / 1.25)} aria-label="Zoom out">−</button>
      <span class="zoom-level small" aria-live="polite">${Math.round(z * 100)}%</span>
      <button class="small secondary" onClick=${() => zoomTo(z * 1.25)} aria-label="Zoom in">+</button>
      <button class=${'small ' + (fitMode === 'all' ? '' : 'secondary')} onClick=${() => { setFitMode('all'); setZ(fitZoom('all')); }} title="Shrink to show the whole tree">Fit all</button>
      <button class=${'small ' + (fitMode === 'width' ? '' : 'secondary')} onClick=${() => { setFitMode('width'); setZ(fitZoom('width')); }} title="Fill the width; scroll down for the rest">Fit width</button>
      <button class="small secondary" onClick=${() => zoomTo(1)}>100%</button>
      <span class="muted small zoom-hint">Drag to move · ${navigator.platform && navigator.platform.includes('Mac') ? '⌘' : 'Ctrl'} + scroll to zoom</span>
    </div>
    <div class="ped-viewport" ref=${outer} style=${`height:${Math.min(height, Math.ceil(nat.h * z) + 24 || height)}px`}
      onPointerDown=${onDown} onPointerMove=${onMove} onPointerUp=${onUp} onPointerCancel=${onUp}>
      <div class="zoom-sizer" style=${`width:${Math.ceil(nat.w * z)}px;height:${Math.ceil(nat.h * z)}px`}>
        <div class="zoom-content" ref=${inner} style=${`transform:scale(${z})`}>${children}</div>
      </div>
    </div>
  </div>`;
}

export function Tree({ id }) {
  const s = useStore();
  const [gens, setGens] = useState(() => { const v = safeStorage('kc.treeGens'); return GEN_OPTIONS.includes(v) ? v : '4'; });
  const [q, setQ] = useState('');
  const depthParam = gens === 'full' ? 'full' : String(+gens - 1);
  const { data: d, error, loading, reload } = useAsync(() => api.get(`/projects/${s.projectId}/tree?depth=${depthParam}${id ? '&root=' + id : ''}`),
    [s.projectId, id, depthParam]);
  const choose = (v) => { setGens(v); safeStorage('kc.treeGens', v); };
  if (loading && !d) return html`<div class="page"><${Loading} /></div>`;
  if (error) return html`<div class="page"><${ErrorBox} error=${error} retry=${reload} /></div>`;
  if (!d.pedigree) return html`<div class="page"><${Empty} title="No people yet"><a class="button" href="#/import">Import a family tree</a><//></div>`;
  const root = d.pedigree;
  const full = gens === 'full';
  const shownGens = full ? d.generations : Math.min(+gens, d.generations);
  const compact = full ? d.generations > 5 : +gens > 5;
  const dense = full && d.generations > 8;
  const matches = q.length > 1 ? d.people.filter((p) => p.name.toLowerCase().includes(q.toLowerCase())).slice(0, 12) : [];
  const makeHome = async () => { try { await api.put(`/projects/${s.projectId}/tree/home`, { person_id: root.id }); toast(`${root.name} is now the home person`); reload(); } catch (x) { toast(errMsg(x), 'bad'); } };
  return html`<div class="page wide-page">
    <header class="page-head"><div><h1>Family tree</h1>
      <p class="lede">${root.name}'s ancestors — ${shownGens} of ${d.generations} generation${d.generations > 1 ? 's' : ''} shown. Click a name to open their record checklist, or ⤢ to move the tree to them.</p></div>
      <div class="tree-tools">
        <div class="find-person"><label class="sr-only" for="tree-find">Find a person</label>
          <input id="tree-find" type="search" placeholder="Find a person…" value=${q} onInput=${(e) => setQ(e.target.value)} autocomplete="off" />
          ${matches.length > 0 && html`<ul class="find-results">${matches.map((p) => html`<li><a href=${`#/tree/${p.id}`} onClick=${() => setQ('')}>${p.name} <span class="muted small">${p.lifespan}</span></a></li>`)}</ul>`}</div>
        <div class="seg gen-seg" role="group" aria-label="Generations to show">
          <span class="seg-label small">Generations</span>
          ${GEN_OPTIONS.map((v) => html`<button class=${gens === v ? 'on' : ''} aria-pressed=${gens === v} onClick=${() => choose(v)}
            title=${v === 'full' ? `All ${d.generations} recorded generations` : `${v} generation${v === '1' ? '' : 's'}`}>${v === 'full' ? 'Full' : v}</button>`)}
        </div>
        ${d.home !== root.id ? html`<button class="small secondary" onClick=${makeHome}>Make home person</button>` : html`<span class="badge tone-good">Home person</span>`}
        <a class="button small secondary" href="#/combine" title="Bring another tree (e.g. the other side of the family) into this one">Combine with another tree</a>
      </div></header>
    ${loading && html`<p class="muted small" role="status">Updating…</p>`}
    <${ZoomView} contentKey=${`${root.id}:${depthParam}:${loading}`}>
      <div class=${dense ? 'ped-dense' : ''}><${Ped} n=${root} depth=${full ? 999 : +gens - 1} isRoot=${true} compact=${compact} full=${full} /></div>
    <//>
    <div class="grid-2 tree-family">
      ${d.spouses.length > 0 && html`<section class="panel"><h2>${d.spouses.length > 1 ? 'Spouses' : 'Spouse'}</h2><div class="fam-list">${d.spouses.map((p) => html`<${PersonLink} p=${p} />`)}</div></section>`}
      ${d.children.length > 0 && html`<section class="panel"><h2>Children</h2><div class="fam-list">${d.children.map((p) => html`<${PersonLink} p=${p} />`)}</div></section>`}
      ${d.siblings.length > 0 && html`<section class="panel"><h2>Brothers & sisters</h2><div class="fam-list">${d.siblings.map((p) => html`<${PersonLink} p=${p} />`)}</div></section>`}
    </div>
  </div>`;
}
