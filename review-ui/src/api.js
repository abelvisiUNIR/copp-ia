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
  // Corregir la fuente a mano. El servidor **revalida** contra el parser real y devuelve el
  // borrador ya con su veredicto nuevo: la pantalla nunca decide si algo compila.
  // Lleva scope `flows:deploy`, no `compose:write` — aprobar despliega esta columna, así que
  // reescribirla es la misma responsabilidad que desplegar.
  editDraftSource: (id, source, actor_id, comment) =>
    request('PATCH', `/drafts/${id}/source`, { source, actor_id, comment }),
  getLatestSource: async (name) => {
    try {
      const flow = await request('GET', `/flows/${name}/latest`)
      return flow.source || ''
    } catch {
      return ''
    }
  },

  // --- Operación -------------------------------------------------------------------
  //
  // Todo esto ya existía en el gateway: el listado filtra por estado y el detalle devuelve
  // las transiciones. La UI operativa no necesitó backend nuevo — necesitaba mirar.
  //
  // Los scopes que exige el gateway acá (`instances:read`, `:signal`, `:retry`) son
  // distintos de los de la revisión (`compose:*`, `flows:deploy`), así que una clave de
  // operador puede firmar expedientes y **no** puede desplegar código. El corte lo hace el
  // gateway, no esta pantalla.
  // El formulario para iniciar un expediente **se genera desde el flow desplegado**: el AST
  // trae los campos que el proceso declara en su bloque `input`, con tipo y si son
  // obligatorios. Es la misma idea del producto aplicada a su propia interfaz — si el proceso
  // cambia sus entradas, el formulario cambia solo, sin tocar la UI.
  listFlows: () => request('GET', '/flows'),
  getFlow: (name) => request('GET', `/flows/${name}/latest`),
  // Las definiciones del dominio **ya mergeadas**, en una sola llamada. Antes cada pantalla
  // juntaba esto pidiendo el AST de cada flow: N+1 requests que crecían con cada deploy y que
  // con once flows ya chocaban contra el rate limit del gateway.
  getDomain: () => request('GET', '/domain'),
  // Ojo con el nombre del campo: `flow_name` es en realidad el **nombre del proceso**. El
  // executor lo resuelve con `find_process()` sobre todo el dominio, así que se puede
  // disparar un proceso que vive dentro de otro flow (`asignacion_dispositivo` en `ceibal`).
  execute: (proceso, payload) =>
    request('POST', '/execute', { flow_name: proceso, payload }),

  // --- Dominio ---------------------------------------------------------------------
  //
  // Las entidades y sus relaciones: el sujeto del negocio, no el trámite. Igual que el
  // formulario de alta, lo que la pantalla sabe hacer sale del flow desplegado — los campos
  // de una entidad y las transiciones de su ciclo de vida están declarados en el `.tflow`.
  listEntities: (tipo, estado, limit = 100) =>
    request('GET', `/entities/${tipo}?limit=${limit}${estado ? `&estado=${estado}` : ''}`),
  getEntity: (tipo, id) => request('GET', `/entities/${tipo}/${id}`),
  createEntity: (tipo, entity_id, fields) =>
    request('POST', `/entities/${tipo}`, { entity_id, fields }),
  transitionEntity: (tipo, id, via, actor_id) =>
    request('POST', `/entities/${tipo}/${id}/transition`, { via, actor_id }),
  vista360: (tipo, id) => request('GET', `/entities/${tipo}/${id}/360`),
  // Una relación no es un join: tiene estado propio y ciclo de vida, igual que una entidad.
  // Por eso se crea y se transiciona, no se "agrega" y ya.
  createRelation: (tipo, from_id, to_id, fields) =>
    request('POST', `/relations/${tipo}`, { from_id, to_id, fields }),
  transitionRelation: (tipo, id, via, actor_id) =>
    request('POST', `/relations/${tipo}/${id}/transition`, { via, actor_id }),

  listInstances: (status, limit = 50) =>
    request('GET', `/instances?limit=${limit}${status ? `&status=${status}` : ''}`),
  getInstance: (id) => request('GET', `/instances/${id}`),
  signal: (id, step_name, signal, actor_id) =>
    request('POST', `/instances/${id}/signal`, { step_name, signal, actor_id }),
  retry: (id) => request('POST', `/instances/${id}/retry`),
}
