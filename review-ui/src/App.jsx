import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { lineDiff } from './diff.js'

export default function App() {
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
        <h1>TeleFlow <span>· revisión de flows generados por IA</span></h1>
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
              <DiffView oldText={baseSource} newText={selected.source} />
            </>
          ) : (
            <div className="placeholder">Seleccioná un borrador para revisarlo</div>
          )}
        </main>
      </div>
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
