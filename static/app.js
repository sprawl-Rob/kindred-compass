import { html, render, useState, useEffect } from './vendor/preact-htm.js';
import { api, store, setStore, useStore, Toasts, safeStorage, Modal, Field, toast, errMsg, nav } from './ui.js';
import { Dashboard } from './views/dashboard.js';
import { Explorer, ResourceDetail, Pathways } from './views/explorer.js';
import { People, PersonPage } from './views/people.js';
import { NextSearches } from './views/recommend.js';
import { ResearchLog } from './views/log.js';
import { Evidence, SourcePage } from './views/evidence.js';
import { Maintain, CollectionEditor } from './views/maintain.js';
import { Settings } from './views/settings.js';
import { loadAIConfig } from './views/ai.js';
import { Imports, ImportBatch } from './views/imports.js';
import { ResearchHome, ResearchRun } from './views/research.js';
import { Home } from './views/home.js';
import { Tree } from './views/tree.js';
import { Leads } from './views/leads.js';
import { PersonOverview } from './views/person.js';
import { Combine } from './views/combine.js';

const NAV = [['', 'Home'], ['tree', 'Family tree'], ['people', 'People'], ['leads', 'Leads']];
const MORE = [
  ['research', 'Research runs'], ['log', 'Research log'], ['evidence', 'Sources & evidence'], ['explore', 'Record collections'],
  ['next', 'Suggested searches'], ['dashboard', 'Project overview'], ['directory', 'Directory maintenance'], ['import', 'Import a tree'], ['combine', 'Combine trees'], ['settings', 'Settings'],
];

function MoreMenu({ active }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return undefined;
    const off = (e) => { if (!e.target.closest('.more-menu')) setOpen(false); };
    document.addEventListener('click', off);
    return () => document.removeEventListener('click', off);
  }, [open]);
  const cur = MORE.find(([k]) => k === active);
  return html`<div class="more-menu">
    <button class=${'more-btn' + (cur ? ' active' : '')} aria-expanded=${open} aria-haspopup="true" onClick=${() => setOpen(!open)}>${cur ? cur[1] : 'More'} ▾</button>
    ${open && html`<ul class="more-list" role="menu">${MORE.map(([k, label]) => html`<li role="none"><a role="menuitem" href=${'#/' + k} onClick=${() => setOpen(false)}
      class=${active === k ? 'active' : ''}>${label}</a></li>`)}</ul>`}
  </div>`;
}

function useLeadCount(pid) {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!pid) return undefined;
    const load = () => api.get(`/projects/${pid}/research/review`).then((r) => setN(r.length), () => {});
    load();
    window.addEventListener('hashchange', load);
    return () => window.removeEventListener('hashchange', load);
  }, [pid]);
  return n;
}

function parseHash() {
  const h = location.hash.replace(/^#\/?/, '');
  const [path, query] = h.split('?');
  const parts = path.split('/').filter(Boolean);
  return { parts, params: new URLSearchParams(query || '') };
}

function NewProject({ onClose }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const save = async (e) => {
    e.preventDefault();
    try {
      const p = await api.post('/projects', { name, description });
      await loadProjects(p.id);
      onClose();
      nav('#/people');
    } catch (err) { toast(errMsg(err), 'bad'); }
  };
  return html`<${Modal} title="New research project" onClose=${onClose}>
    <form onSubmit=${save} class="stack">
      <${Field} label="Project name"><input required value=${name} onInput=${(e) => setName(e.target.value)} placeholder="e.g. Whitcomb line, Worcester County" /><//>
      <${Field} label="Description (optional)"><textarea rows="3" value=${description} onInput=${(e) => setDescription(e.target.value)} /><//>
      <div class="row end"><button type="button" class="secondary" onClick=${onClose}>Cancel</button><button type="submit">Create project</button></div>
    </form><//>`;
}

export async function loadProjects(selectId) {
  const projects = await api.get('/projects');
  let id = selectId || store.projectId || safeStorage('kc.project');
  if (!projects.find((p) => p.id === id)) id = (projects.find((p) => !p.is_demo) || projects[0] || {}).id || null;
  safeStorage('kc.project', id);
  setStore({ projects, projectId: id });
}

function ProjectSwitcher() {
  const s = useStore();
  const [creating, setCreating] = useState(false);
  const cur = s.projects.find((p) => p.id === s.projectId);
  return html`<div class="project-switch">
    <label class="sr-only" for="project-select">Active project</label>
    <select id="project-select" value=${s.projectId || ''} onChange=${(e) => { safeStorage('kc.project', e.target.value); setStore({ projectId: e.target.value }); }}>
      ${s.projects.length === 0 && html`<option value="">No projects yet</option>`}
      ${s.projects.map((p) => html`<option value=${p.id} selected=${p.id === s.projectId}>${p.is_demo ? '🧪 ' : ''}${p.name}</option>`)}
    </select>
    <button class="secondary small" onClick=${() => setCreating(true)}>New project</button>
    ${cur && cur.is_demo ? html`<span class="badge tone-warn" title="Everything in this project is invented">Fictional demo</span>` : null}
    ${creating && html`<${NewProject} onClose=${() => setCreating(false)} />`}
  </div>`;
}

function Shell() {
  const s = useStore();
  const [route, setRoute] = useState(parseHash());
  const [menuOpen, setMenuOpen] = useState(false);
  const leadCount = useLeadCount(s.projectId);
  useEffect(() => {
    const on = () => { setRoute(parseHash()); setMenuOpen(false); window.scrollTo(0, 0); const m = document.getElementById('main'); m && m.focus({ preventScroll: true }); };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  if (!s.meta) return html`<p style="padding:2rem">Loading…</p>`;
  const { parts, params } = route;
  const top = parts[0] || '';
  let view;
  const pid = s.projectId;
  const needProject = (v) => (pid ? v : html`<div class="page"><h1>No project selected</h1><p>Create a project to start.</p></div>`);
  switch (top) {
    case '': view = needProject(html`<${Home} key=${pid} />`); break;
    case 'dashboard': view = needProject(html`<${Dashboard} key=${pid} />`); break;
    case 'tree': view = needProject(html`<${Tree} key=${pid + (parts[1] || '')} id=${parts[1]} />`); break;
    case 'leads': view = needProject(html`<${Leads} key=${pid} />`); break;
    case 'combine': view = needProject(html`<${Combine} key=${pid} />`); break;
    case 'explore': view = html`<${Explorer} params=${params} />`; break;
    case 'resource': view = html`<${ResourceDetail} id=${parts[1]} key=${parts[1]} />`; break;
    case 'pathways': view = html`<${Pathways} />`; break;
    case 'people': view = needProject(html`<${People} key=${pid} />`); break;
    case 'person': view = parts[2] === 'edit' ? html`<${PersonPage} id=${parts[1]} key=${parts[1] + 'e'} />` : html`<${PersonOverview} id=${parts[1]} key=${parts[1]} />`; break;
    case 'next': view = needProject(html`<${NextSearches} key=${pid + location.hash} params=${params} />`); break;
    case 'log': view = needProject(html`<${ResearchLog} key=${pid} params=${params} />`); break;
    case 'evidence': view = needProject(html`<${Evidence} key=${pid} params=${params} />`); break;
    case 'source': view = html`<${SourcePage} id=${parts[1]} key=${parts[1]} />`; break;
    case 'directory':
      view = parts[1] === 'edit' || parts[1] === 'new' ? html`<${CollectionEditor} id=${parts[2]} key=${parts[2] || 'new'} />` : html`<${Maintain} />`;
      break;
    case 'settings': view = html`<${Settings} tab=${parts[1] || 'research'} />`; break;
    case 'research': view = parts[1] ? html`<${ResearchRun} id=${parts[1]} key=${parts[1]} />` : needProject(html`<${ResearchHome} key=${pid} />`); break;
    case 'import': view = parts[1] ? html`<${ImportBatch} id=${parts[1]} key=${parts[1]} />` : html`<${Imports} />`; break;
    default: view = html`<div class="page"><h1>Page not found</h1><a href="#/">Go to dashboard</a></div>`;
  }
  const activeKey = { resource: 'explore', person: 'people', source: 'evidence', pathways: 'explore' }[top] ?? top;
  return html`
    <header class="topbar">
      <a class="brand" href="#/"><span class="brand-mark" aria-hidden="true">✦</span> Kindred Compass</a>
      <${ProjectSwitcher} />
      <button class="menu-toggle secondary small" aria-expanded=${menuOpen} aria-controls="mainnav" onClick=${() => setMenuOpen(!menuOpen)}>Menu</button>
    </header>
    <nav id="mainnav" class=${'mainnav' + (menuOpen ? ' open' : '')} aria-label="Main">
      ${NAV.map(([k, label]) => html`<a href=${'#/' + k} class=${activeKey === k ? 'active' : ''} aria-current=${activeKey === k ? 'page' : undefined}>${label}${k === 'leads' && leadCount > 0 ? html` <span class="count-pill">${leadCount}</span>` : ''}</a>`)}
      <${MoreMenu} active=${activeKey} />
    </nav>
    <main id="main" tabindex="-1">${view}</main>
    <footer class="footer">Local-first: your research is stored on this computer. AI is ${s.ai && s.ai.enabled ? 'enabled — nothing is sent without a preview' : 'disabled'} · <a href="#/settings/ai">AI settings</a></footer>
    <${Toasts} />`;
}

async function boot() {
  try {
    const [meta, prefs] = await Promise.all([api.get('/meta'), api.get('/settings/research-prefs')]);
    setStore({ meta, prefs });
    await loadProjects();
    await loadAIConfig();
  } catch (e) {
    document.getElementById('app').textContent = 'Could not start: ' + errMsg(e);
    return;
  }
  const root = document.getElementById('app');
  root.textContent = '';
  render(html`<${Shell} />`, root);
}
boot();
