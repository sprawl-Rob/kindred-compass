import { html, useState } from '../vendor/preact-htm.js';
import { api, useAsync, useStore, setStore, store, Loading, ErrorBox, Field, Select, Tabs, toast, errMsg, nav } from '../ui.js';
import { AISettings } from './ai.js';
import { ArchiveSettings } from './research.js';
import { loadProjects } from '../app.js';

function ResearchPrefs() {
  const s = useStore();
  const providers = useAsync(() => api.get('/directory/providers'), []);
  const [p, setP] = useState(s.prefs);
  const save = async (patch) => {
    const next = { ...p, ...patch }; setP(next);
    try { setStore({ prefs: await api.put('/settings/research-prefs', next) }); toast('Preferences saved'); } catch (x) { toast(errMsg(x), 'bad'); }
  };
  const subs = new Set(p.subscriptions || []);
  return html`<div class="stack">
    <section class="panel"><h2>Access preferences</h2>
      <p class="small">Used as the default for recommendations. Sources outside your preference are still listed in a separate “hidden” section, never silently dropped.</p>
      <${Field} label="Default access filter"><${Select} value=${p.access} onChange=${(v) => save({ access: v })} empty="Show all sources"
        options=${{ free: 'Free only', free_or_account: 'Free or free account', my_access: 'Free + my subscriptions' }} /><//>
      <label class="check"><input type="checkbox" checked=${!!p.remote_only} onChange=${(e) => save({ remote_only: e.target.checked })} /> Prefer sources I can use remotely</label>
    </section>
    <section class="panel"><h2>My subscriptions & library access</h2>
      <p class="small">Tick providers you can access (paid subscription, or through your library). Recommendations rank these higher.</p>
      ${providers.loading ? html`<${Loading} />` : html`<div class="checks-grid">${(providers.data || []).filter((x) => ['commercial_database', 'historical_society', 'government_agency'].includes(x.provider_type)).map((x) => html`
        <label class="check"><input type="checkbox" checked=${subs.has(x.id)} onChange=${(e) => { const n = new Set(subs); e.target.checked ? n.add(x.id) : n.delete(x.id); save({ subscriptions: [...n] }); }} /> ${x.name}</label>`)}</div>`}
    </section>
  </div>`;
}

function DataSettings() {
  const s = useStore();
  const backups = useAsync(() => api.get('/backups'), []);
  const [busy, setBusy] = useState(null);
  const proj = s.projects.find((x) => x.id === s.projectId);
  const doBackup = async () => { setBusy('backup'); try { const b = await api.post('/backups'); toast(`Backup created: ${b.name}`); backups.reload(); } catch (x) { toast(errMsg(x), 'bad'); } setBusy(null); };
  const restore = async (form) => {
    if (prompt('Restoring replaces ALL current data with the backup. A safety backup of the current data is made first. Type RESTORE to continue.') !== 'RESTORE') return;
    setBusy('restore');
    try { const r = await api.form('/backups/restore', form); toast(`Restored. Safety backup: ${r.safety_backup}`); await loadProjects(); nav('#/'); }
    catch (x) { toast(errMsg(x), 'bad'); }
    setBusy(null);
  };
  const restoreNamed = (name) => { const fd = new FormData(); fd.append('name', name); fd.append('confirm', 'RESTORE'); restore(fd); };
  const restoreFile = (e) => { const f = e.target.files[0]; if (!f) return; const fd = new FormData(); fd.append('file', f); fd.append('confirm', 'RESTORE'); restore(fd); e.target.value = ''; };
  const importProject = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    try { const r = await api.form('/import/project', fd); await loadProjects(r.project_id); toast('Project imported as a new project'); nav('#/'); } catch (x) { toast(errMsg(x), 'bad'); }
    e.target.value = '';
  };
  const importFull = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    if (prompt('Full import REPLACES all data in the app with the file\'s contents. A safety backup is made first. Type REPLACE to continue.') !== 'REPLACE') { e.target.value = ''; return; }
    const fd = new FormData(); fd.append('file', f); fd.append('confirm', 'REPLACE');
    try { const r = await api.form('/import/full', fd); toast(`Imported. Safety backup: ${r.safety_backup}`); await loadProjects(); nav('#/'); } catch (x) { toast(errMsg(x), 'bad'); }
    e.target.value = '';
  };
  const resetDemo = async () => { const r = await api.post('/demo/reset'); await loadProjects(r.project_id); toast('Demo project reset'); };
  const delProject = async () => {
    if (!proj || prompt(`Delete project “${proj.name}” and all its people, claims, sources, log entries and attachments? A backup is made first. Type DELETE to confirm.`) !== 'DELETE') return;
    await api.del(`/projects/${proj.id}`); await loadProjects(); toast('Project deleted (a backup was made first)'); nav('#/');
  };
  return html`<div class="stack">
    <section class="panel"><h2>Where your data is stored</h2>
      <table class="kv small"><tbody>
        <tr><th scope="row">Data folder</th><td><code>${s.meta.storage.data_dir}</code></td></tr>
        <tr><th scope="row">Database</th><td><code>${s.meta.storage.database}</code> (SQLite)</td></tr>
        <tr><th scope="row">Attachments</th><td><code>${s.meta.storage.attachments}</code></td></tr>
        <tr><th scope="row">Backups</th><td><code>${s.meta.storage.backups}</code></td></tr></tbody></table>
      <p class="small muted">API keys are not stored here — they live in your system keychain.</p></section>
    <section class="panel"><h2>Backup & restore (includes attachments)</h2>
      <div class="row wrap"><button onClick=${doBackup} disabled=${busy}>${busy === 'backup' ? 'Creating…' : 'Create backup now'}</button>
        <label class="button secondary file-btn">Restore from a backup file…<input type="file" accept=".zip" class="sr-only" onChange=${restoreFile} /></label></div>
      ${backups.data && backups.data.length > 0 && html`<ul class="list small">${backups.data.map((b) => html`<li><div class="list-main"><code>${b.name}</code> <span class="muted">${Math.round(b.size_bytes / 1024)} KB</span></div>
        <a class="button small secondary" href=${`/api/backups/${encodeURIComponent(b.name)}/download`} download>Download</a>
        <button class="small secondary" onClick=${() => restoreNamed(b.name)}>Restore</button></li>`)}</ul>`}</section>
    <section class="panel"><h2>Export & import</h2>
      <div class="row wrap">
        ${proj && html`<a class="button secondary" href=${`/api/projects/${proj.id}/export.json`} download>Export this project (JSON, with attachments)</a>`}
        <label class="button secondary file-btn">Import a project…<input type="file" accept=".json,application/json" class="sr-only" onChange=${importProject} /></label></div>
      <p class="small muted">Project import always creates a new project — it never overwrites existing work.</p>
      <div class="row wrap"><a class="button secondary" href="/api/export/full.json" download>Full export (all data, JSON)</a>
        <label class="button secondary file-btn">Full import (replace all)…<input type="file" accept=".json,application/json" class="sr-only" onChange=${importFull} /></label></div>
      <div class="row wrap">${proj && html`<a class="button secondary" href=${`/api/projects/${proj.id}/log.csv`} download>Research log (CSV)</a>`}
        <a class="button secondary" href="/api/directory/export.csv" download>Resource directory (CSV)</a></div></section>
    <section class="panel"><h2>Projects</h2>
      <div class="row wrap"><button class="secondary" onClick=${resetDemo}>Reset fictional demo project</button>
        ${proj && html`<button class="danger" onClick=${delProject}>Delete current project…</button>`}</div></section>
  </div>`;
}

export function Settings({ tab }) {
  return html`<div class="page">
    <header class="page-head"><h1>Settings</h1></header>
    <${Tabs} tabs=${[['research', 'Research preferences'], ['archives', 'Archives'], ['data', 'Data & backups'], ['ai', 'AI']]} active=${tab} onChange=${(k) => nav('#/settings/' + k)} />
    ${tab === 'research' && html`<${ResearchPrefs} />`}
    ${tab === 'data' && html`<${DataSettings} />`}
    ${tab === 'ai' && html`<${AISettings} />`}
    ${tab === 'archives' && html`<${ArchiveSettings} />`}
  </div>`;
}
