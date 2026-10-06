import { html, useState, useEffect, useRef, useCallback } from './vendor/preact-htm.js';
import { api } from './api.js';

// ------------------------------------------------------------------ tiny global store
const listeners = new Set();
export const store = { meta: null, projects: [], projectId: null, prefs: null };
export function setStore(patch) { Object.assign(store, patch); listeners.forEach((l) => l()); }
export function useStore() {
  const [, force] = useState(0);
  useEffect(() => { const l = () => force((n) => n + 1); listeners.add(l); return () => listeners.delete(l); }, []);
  return store;
}
export function safeStorage(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value);
  } catch (e) { return null; }
  return null;
}

// ------------------------------------------------------------------ hooks
export function useAsync(fn, deps = []) {
  const [state, set] = useState({ data: null, error: null, loading: true });
  const seq = useRef(0);
  const run = useCallback(() => {
    const n = ++seq.current;
    set((s) => ({ ...s, loading: true }));
    return Promise.resolve().then(fn).then(
      (data) => { if (n === seq.current) set({ data, error: null, loading: false }); },
      (error) => { if (n === seq.current) set({ data: null, error, loading: false }); },
    );
  }, deps);
  useEffect(() => { run(); }, [run]);
  return { ...state, reload: run };
}

// ------------------------------------------------------------------ labels & formatting
export function L(vocab, key) {
  const v = store.meta && store.meta.vocab[vocab];
  return (v && v[key]) || key || '';
}
export const fmtDate = (s) => (s ? String(s).slice(0, 10) : '');
export function years(a, b) {
  if (a == null && b == null) return '';
  if (a === b) return String(a);
  return `${a ?? '…'}–${b ?? '…'}`;
}

// ------------------------------------------------------------------ toast
let toastSet = null;
export function toast(message, tone = 'info') { if (toastSet) toastSet({ message, tone, id: Date.now() }); }
export function Toasts() {
  const [t, setT] = useState(null);
  toastSet = setT;
  useEffect(() => { if (t) { const h = setTimeout(() => setT(null), 6000); return () => clearTimeout(h); } }, [t]);
  return html`<div class="toast-region" role="status" aria-live="polite">${t && html`<div class=${'toast tone-' + t.tone}>${t.message}
    <button class="link" onClick=${() => setT(null)} aria-label="Dismiss">✕</button></div>`}</div>`;
}
export function errMsg(e) { return (e && e.message) || String(e); }

// ------------------------------------------------------------------ components
export function Badge({ b }) {
  return html`<span class=${'badge tone-' + (b.tone || 'neutral')} title=${b.hint || ''}>${b.label}</span>`;
}
export function Badges({ list }) {
  return html`<span class="badges">${(list || []).map((b) => html`<${Badge} b=${b} />`)}</span>`;
}

export function Field({ label, hint, children, wide }) {
  return html`<label class=${'field' + (wide ? ' wide' : '')}><span class="field-label">${label}</span>${children}
    ${hint && html`<span class="hint">${hint}</span>`}</label>`;
}

export function Select({ value, onChange, options, empty, id, required }) {
  const entries = Array.isArray(options) ? options : Object.entries(options || {});
  return html`<select key=${entries.length} id=${id} value=${value ?? ''} required=${required} onChange=${(e) => onChange(e.target.value || null)}>
    ${empty !== undefined && html`<option value="">${empty}</option>`}
    ${entries.map(([k, v]) => html`<option value=${k} selected=${k === value}>${v}</option>`)}
  </select>`;
}

export function CheckboxGroup({ options, value, onChange, legend }) {
  const set = new Set(value || []);
  return html`<fieldset class="checks"><legend>${legend}</legend>
    ${Object.entries(options).map(([k, v]) => html`<label class="check"><input type="checkbox" checked=${set.has(k)}
      onChange=${(e) => { const n = new Set(set); e.target.checked ? n.add(k) : n.delete(k); onChange([...n]); }} /> ${v}</label>`)}
  </fieldset>`;
}

export function Modal({ title, onClose, children, wide }) {
  const ref = useRef(null);
  useEffect(() => {
    const prev = document.activeElement;
    const el = ref.current;
    const first = el && el.querySelector('input, select, textarea, button:not(.modal-close)');
    (first || el).focus();
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'Tab' && el) {
        const f = [...el.querySelectorAll('a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])')];
        if (!f.length) return;
        if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
        else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); prev && prev.focus && prev.focus(); };
  }, []);
  return html`<div class="modal-backdrop" onMouseDown=${(e) => e.target === e.currentTarget && onClose()}>
    <div class=${'modal' + (wide ? ' wide' : '')} role="dialog" aria-modal="true" aria-label=${title} ref=${ref} tabindex="-1">
      <header class="modal-head"><h2>${title}</h2><button class="icon modal-close" onClick=${onClose} aria-label="Close dialog">✕</button></header>
      <div class="modal-body">${children}</div>
    </div></div>`;
}

export function Empty({ title, children }) {
  return html`<div class="empty"><p class="empty-title">${title}</p>${children && html`<div class="empty-body">${children}</div>`}</div>`;
}

export function CopyButton({ text, label = 'Copy', small }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); }
    catch (e) {
      const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch (_) { /* ignore */ } ta.remove();
    }
    setDone(true); setTimeout(() => setDone(false), 1500);
  };
  return html`<button type="button" class=${'secondary' + (small ? ' small' : '')} onClick=${copy}>${done ? 'Copied ✓' : label}</button>`;
}

// External links always open in a new tab and say so.
export function ExtLink({ href, children, cls }) {
  if (!href) return null;
  return html`<a class=${'ext ' + (cls || '')} href=${href} target="_blank" rel="noopener noreferrer">${children}<span class="sr-only"> (opens external site in a new tab)</span><span aria-hidden="true"> ↗</span></a>`;
}

export function Loading({ what = 'Loading' }) { return html`<p class="muted" role="status">${what}…</p>`; }
export function ErrorBox({ error, retry }) {
  if (!error) return null;
  return html`<div class="callout tone-bad" role="alert">${errMsg(error)} ${retry && html`<button class="link" onClick=${retry}>Try again</button>`}</div>`;
}

export function PlaceFields({ value, onChange, compact }) {
  const v = value || {};
  const set = (k) => (e) => onChange({ ...v, [k]: e.target.value });
  return html`<div class=${'place-fields' + (compact ? ' compact' : '')}>
    <${Field} label="Country"><input value=${v.country || ''} onInput=${set('country')} placeholder="United States" /><//>
    <${Field} label="State / province / region"><input value=${v.region || ''} onInput=${set('region')} placeholder="Massachusetts" /><//>
    <${Field} label="County"><input value=${v.county || ''} onInput=${set('county')} placeholder="Worcester" /><//>
    <${Field} label="Town / city"><input value=${v.municipality || ''} onInput=${set('municipality')} /><//>
    ${!compact && html`<${Field} label="Historical jurisdiction" hint="The jurisdiction at the time, if different (e.g. 'Prussia', 'Virginia before 1863')">
      <input value=${v.historical_jurisdiction || ''} onInput=${set('historical_jurisdiction')} /><//>`}
  </div>`;
}

export function placeLabel(p) {
  if (!p) return '';
  return p.name || [p.municipality, p.county, p.region, p.country].filter(Boolean).join(', ');
}

export function nav(hash) { location.hash = hash; }

export function Tabs({ tabs, active, onChange }) {
  return html`<div class="tabs" role="tablist">${tabs.map(([k, label]) => html`<button role="tab" aria-selected=${active === k}
    class=${'tab' + (active === k ? ' active' : '')} onClick=${() => onChange(k)}>${label}</button>`)}</div>`;
}

export { api };
