import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { lineDiff } from './diff.js'
import Operacion from './ops.jsx'
import Dominio from './dominio.jsx'

// Tres secciones con públicos distintos en la misma app: **operación** (un gerente firma un
// expediente), **dominio** (el sujeto del negocio: personas, cursos, vínculos) y **revisión**
// (un desarrollador aprueba y despliega código). Comparten build porque separarlas costaría
// una imagen, un servicio y un deployment más, sin ganar seguridad: el corte real lo hacen los
// scopes del gateway, que son distintos para cada una y se validan del lado del servidor. Una
// clave de operador recibe 403 en el deploy aunque tenga el botón a la vista.
//
// Lo que sí queda pendiente de decidir el día que el chart la publique: hoy `review-ui` no se
// expone justamente porque desde acá se despliega código, y la sección operativa es la que
// necesitaría ser alcanzable. Esa decisión es de exposición, no de código, y va con su ADR.

export default function App() {
  const [seccion, setSeccion] = useState('revision')
  const [drafts, setDrafts] = useState([])
  const [selected, setSelected] = useState(null)
  const [baseSource, setBaseSource] = useState('')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [apiKey, setApiKey] = useState(localStorage.getItem('tflow_api_key') || '')
  const [showCompose, setShowCompose] = useState(false)

  const refresh = async () => {
    try {
      setDrafts(await api.listDrafts())
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => { refresh() }, [])

  const open = async (id) => {
    try {
      const draft = await api.getDraft(id)
      setSelected(draft)
      setBaseSource(draft.base_source || await api.getLatestSource(draft.name))
      setInfo('')
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }

  const saveKey = (value) => {
    setApiKey(value)
    localStorage.setItem('tflow_api_key', value)
  }

  const approve = async () => {
    // Aprobar un borrador que no compila es un deploy que va a fallar. No se bloquea
    // (puede haberse editado fuera, o el parser puede haber estado caído), pero tiene que
    // ser una decisión consciente y no un click de más.
    if (selected.validation?.parses !== true) {
      const estado = selected.validation?.parses === false
        ? 'NO compila según el parser'
        : 'no se pudo verificar contra el parser'
      if (!confirm(`Este borrador ${estado}. ¿Aprobar y desplegar igual?`)) return
    }
    const version = prompt('Versión a publicar (semver):', '1.0.0')
    if (!version) return
    const actor = prompt('Tu usuario (actor_id):', 'dev')
    try {
      await api.approve(selected.draft_id, version, actor || 'dev', '')
      setInfo(`✓ Aprobado y desplegado como ${selected.name}@${version}`)
      setSelected(null)
      refresh()
    } catch (e) {
      setError(e.message)
    }
  }

  const reject = async () => {
    const comment = prompt('Comentario de rechazo:')
    if (comment === null) return
    try {
      await api.reject(selected.draft_id, 'dev', comment)
      setInfo('Borrador rechazado')
      setSelected(null)
      refresh()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="layout">
      <header>
        <h1>TeleFlow</h1>
        <nav className="secciones">
          <button className={seccion === 'operacion' ? 'activo' : ''}
                  onClick={() => { setSeccion('operacion'); setError(''); setInfo('') }}>
            Operación
          </button>
          <button className={seccion === 'dominio' ? 'activo' : ''}
                  onClick={() => { setSeccion('dominio'); setError(''); setInfo('') }}>
            Dominio
          </button>
          <button className={seccion === 'revision' ? 'activo' : ''}
                  onClick={() => { setSeccion('revision'); setError(''); setInfo('') }}>
            Revisión de flows
          </button>
        </nav>
        <input
          className="apikey"
          type="password"
          placeholder="X-TeleFlow-API-Key"
          value={apiKey}
          onChange={(e) => saveKey(e.target.value)}
        />
      </header>

      {error && <div className="banner error">{error}</div>}
      {info && <div className="banner info">{info}</div>}

      {seccion === 'operacion' && <Operacion onError={setError} onInfo={setInfo} />}
      {seccion === 'dominio' && <Dominio onError={setError} onInfo={setInfo} />}

      {/* Se monta solo la sección activa. Con la otra oculta pero presente, las dos listas
          conviven en el DOM y cualquiera —una prueba, un lector de pantalla, un atajo de
          teclado— puede alcanzar la que no se está viendo. */}
      {seccion === 'revision' && (
      <div className="columns">
        <aside>
          <div className="aside-head">
            <h2>Borradores</h2>
            <button onClick={() => setShowCompose(!showCompose)}>+ Nuevo</button>
          </div>
          {showCompose && <ComposeForm onDone={() => { setShowCompose(false); refresh() }}
                                       onError={setError} />}
          <ul className="draft-list">
            {drafts.map((d) => (
              <li key={d.draft_id}
                  className={selected?.draft_id === d.draft_id ? 'active' : ''}
                  onClick={() => open(d.draft_id)}>
                <strong>{d.name}</strong>
                <span className={`status ${d.status}`}>{d.status}</span>
                <ValidationBadge validation={d.validation} />
                <p>{d.description?.slice(0, 80)}</p>
              </li>
            ))}
            {drafts.length === 0 && <li className="empty">Sin borradores aún</li>}
          </ul>
        </aside>

        <main>
          {selected ? (
            <>
              <div className="review-head">
                <h2>{selected.name} <span className={`status ${selected.status}`}>
                  {selected.status}</span></h2>
                {selected.status === 'pending' && (
                  <div className="actions">
                    <button className="approve" onClick={approve}>Aprobar y desplegar</button>
                    <button className="reject" onClick={reject}>Rechazar</button>
                  </div>
                )}
              </div>
              <p className="desc">{selected.description}</p>
              <ValidationPanel validation={selected.validation}
                               provider={selected.provider} />
              <DiffView oldText={baseSource} newText={selected.source} />
            </>
          ) : (
            <div className="placeholder">Seleccioná un borrador para revisarlo</div>
          )}
        </main>
      </div>
      )}
    </div>
  )
}

// `parses` tiene tres estados y los tres importan: compila, no compila, y no se pudo
// verificar (parser caído, o borrador anterior a que se validara). "No sé" no se muestra
// como "está bien": esa confusión es justo lo que hace que un borrador roto llegue a la
// revisión sin que nadie lo sepa.
function validationState(validation) {
  if (validation?.parses === true) return { cls: 'ok', label: 'compila' }
  if (validation?.parses === false) return { cls: 'bad', label: 'no compila' }
  return { cls: 'unknown', label: 'sin verificar' }
}

function ValidationBadge({ validation }) {
  const { cls, label } = validationState(validation)
  return <span className={`badge ${cls}`}>{label}</span>
}

function ValidationPanel({ validation, provider }) {
  const { cls } = validationState(validation)
  const issues = validation?.issues || []
  return (
    <div className={`validation ${cls}`}>
      <div className="validation-head">
        <ValidationBadge validation={validation} />
        <span className="provider">
          generado por <strong>{provider || 'desconocido'}</strong>
          {provider === 'stub' && ' — esqueleto para editar a mano, no lo escribió un modelo'}
        </span>
      </div>
      {validation?.error && (
        <p className="validation-error">
          No se pudo consultar al parser: {validation.error}
        </p>
      )}
      {issues.length > 0 && (
        <ul className="issues">
          {issues.map((issue, i) => (
            <li key={i} className={issue.level}>
              <span className="issue-level">{issue.level}</span>
              {issue.block && <span className="issue-block">{issue.block}</span>}
              {issue.message}
            </li>
          ))}
        </ul>
      )}
      {issues.length === 0 && cls === 'ok' && (
        <p className="validation-ok">Sin observaciones del parser.</p>
      )}
    </div>
  )
}

function ComposeForm({ onDone, onError }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      let base = ''
      if (name) base = await api.getLatestSource(name)
      await api.compose(name, description, base || null)
      setName('')
      setDescription('')
      onDone()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="compose" onSubmit={submit}>
      <input placeholder="nombre_del_flow" value={name} required
             onChange={(e) => setName(e.target.value)} />
      <textarea placeholder="Describí el proceso en lenguaje natural…" rows={5}
                value={description} required
                onChange={(e) => setDescription(e.target.value)} />
      <button disabled={busy}>{busy ? 'Generando…' : 'Generar borrador'}</button>
    </form>
  )
}

function DiffView({ oldText, newText }) {
  const rows = lineDiff(oldText, newText)
  const isNew = !oldText
  return (
    <div className="diff">
      <div className="diff-header">
        {isNew ? 'Archivo nuevo' : 'Diff contra la versión latest registrada'}
      </div>
      <pre>
        {rows.map((row, i) => (
          <div key={i} className={`line ${row.type}`}>
            <span className="gutter">
              {row.type === 'add' ? '+' : row.type === 'del' ? '−' : ' '}
            </span>
            {row.text}
          </div>
        ))}
      </pre>
    </div>
  )
}
