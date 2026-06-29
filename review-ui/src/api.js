const BASE = '/api'

function headers() {
  return {
    'Content-Type': 'application/json',
    'X-TeleFlow-API-Key': localStorage.getItem('tflow_api_key') || '',
  }
}

async function request(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: headers(),
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = typeof data.detail === 'string'
      ? data.detail
      : JSON.stringify(data.detail || data)
    throw new Error(`${res.status}: ${detail}`)
  }
  return data
}

export const api = {
  listDrafts: () => request('GET', '/drafts'),
  getDraft: (id) => request('GET', `/drafts/${id}`),
  compose: (name, description, base_source) =>
    request('POST', '/compose', { name, description, base_source }),
  approve: (id, version, actor_id, comment) =>
    request('POST', `/drafts/${id}/approve`, { version, actor_id, comment }),
  reject: (id, actor_id, comment) =>
    request('POST', `/drafts/${id}/reject`, { actor_id, comment }),
  getLatestSource: async (name) => {
    try {
      const flow = await request('GET', `/flows/${name}/latest`)
      return flow.source || ''
    } catch {
      return ''
    }
  },
}
