// Thin API client. All mutating requests carry X-Kindred (server rejects cross-site posts without it).
export class ApiError extends Error {
  constructor(status, body) {
    super((body && body.detail) || `Request failed (${status})`);
    this.status = status;
    this.body = body || {};
  }
}

async function request(method, path, body, isForm = false) {
  const opts = { method, headers: { 'X-Kindred': '1' } };
  if (body !== undefined) {
    if (isForm) opts.body = body;
    else { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  }
  const res = await fetch('/api' + path, opts);
  const ct = res.headers.get('content-type') || '';
  const data = ct.includes('application/json') ? await res.json() : await res.text();
  if (!res.ok) throw new ApiError(res.status, typeof data === 'object' ? data : { detail: data });
  return data;
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b = {}) => request('POST', p, b),
  put: (p, b = {}) => request('PUT', p, b),
  patch: (p, b = {}) => request('PATCH', p, b),
  del: (p) => request('DELETE', p),
  form: (p, formData) => request('POST', p, formData, true),
};
