import React, { useEffect, useRef, useState } from 'react'
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
  // Edición del borrador. `editado` es el texto en pantalla; mientras difiera del guardado, el
  // veredicto que trae el borrador ya no habla de lo que se está viendo.
  const [editando, setEditando] = useState(false)
  const [editado, setEditado] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [verDiff, setVerDiff] = useState('desplegada')
  const areaRef = useRef(null)

  const sinGuardar = editando && editado !== selected?.source

  // La línea del primer error de sintaxis, para marcarla en la columna de números. Con cambios
  // sin guardar no se marca nada: el veredicto habla de la versión anterior, y señalar una
  // línea del texto nuevo apuntaría a cualquier lado.
  const lineaError = sinGuardar
    ? null
    : (selected?.validation?.issues || []).find((i) => i.line != null)?.line ?? null

  /**
   * Lleva el cursor a `linea`/`columna` del editor y deja la línea seleccionada.
   *
   * Abre el editor si estaba cerrado: el revisor que hace clic en un error quiere corregirlo,
   * no mirarlo de más cerca. `setTimeout` porque el textarea todavía no existe en el DOM en
   * ese mismo tick.
   *
   * Selecciona la **línea entera** en vez de poner el cursor en la columna: el rango marcado
   * se ve, un cursor en la columna 62 de una línea larga no. La columna igual se usa para
   * dejar el cursor donde corresponde dentro de la selección.
   */
  const irALinea = (linea, columna) => {
    if (!editando) editar()
    setTimeout(() => {
      const area = areaRef.current
      if (!area) return
      const lineas = area.value.split('\n')
      const indice = Math.min(Math.max(linea - 1, 0), lineas.length - 1)
      const desde = lineas.slice(0, indice).reduce((n, l) => n + l.length + 1, 0)
      const hasta = desde + lineas[indice].length
      area.focus()
      area.setSelectionRange(desde, hasta)
      // Sin esto la selección queda fuera de la vista en un archivo largo, que es justamente
      // el caso donde alguien necesita que lo lleven.
      const alto = area.clientHeight
      const porLinea = area.scrollHeight / Math.max(lineas.length, 1)
      area.scrollTop = Math.max(0, indice * porLinea - alto / 2)
    }, 0)
  }

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
      // Abrir otro borrador cierra el editor: dejarlo abierto mostraría el texto de uno sobre
      // el veredicto de otro.
      setEditando(false)
      setEditado('')
      setVerDiff('desplegada')
      setInfo('')
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }

  const editar = () => {
    setEditado(selected.source)
    setEditando(true)
    setInfo('')
  }

  const cancelarEdicion = () => {
    if (sinGuardar && !confirm('Perdés los cambios que no guardaste. ¿Cerrar el editor?')) return
    setEditando(false)
    setEditado('')
  }

  // Guardar **es** validar: no hay forma de dejar una corrección sin que el parser opine.
  // El borrador vuelve con su veredicto nuevo y el editor queda abierto, porque arreglar un
  // error suele destapar el siguiente y la vuelta cuesta menos de un segundo.
  const validarYGuardar = async () => {
    const comment = prompt('Qué corregiste (queda en el historial del borrador):', '')
    if (comment === null) return
    const actor = prompt('Tu usuario (actor_id):', 'dev')
    if (actor === null) return
    setGuardando(true)
    try {
      const draft = await api.editDraftSource(selected.draft_id, editado, actor || 'dev', comment)
      setSelected(draft)
      setEditado(draft.source)
      setInfo(draft.validation?.parses === true
        ? '✓ Guardado y compila'
        : 'Guardado — el parser todavía tiene observaciones')
      setError('')
      refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setGuardando(false)
    }
  }

  const saveKey = (value) => {
    setApiKey(value)
    localStorage.setItem('tflow_api_key', value)
  }

  const approve = async () => {
    // Lo que se despliega es la fuente **guardada**, no la que está en el textarea. Con
    // cambios sin guardar, la pantalla estaría mostrando una cosa y el deploy publicando otra:
    // es la confusión más cara que puede tener este editor.
    if (sinGuardar && !confirm(
      'Tenés cambios sin guardar. Se va a desplegar la última versión guardada, ' +
      'no lo que estás viendo. ¿Seguir igual?')) return
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
                {/* Un borrador corregido ya pasó por una persona. Quien lo abra después
                    quiere saberlo antes de leerlo como si fuera salida cruda del modelo. */}
                {d.editado && <span className="badge editado">corregido</span>}
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
                    {!editando && (
                      <button className="edit" onClick={editar}>Corregir</button>
                    )}
                    <button className="approve" onClick={approve}>Aprobar y desplegar</button>
                    <button className="reject" onClick={reject}>Rechazar</button>
                  </div>
                )}
              </div>
              <p className="desc">{selected.description}</p>
              <ValidationPanel validation={selected.validation}
                               provider={selected.provider}
                               desactualizada={sinGuardar}
                               onIrALinea={selected.status === 'pending' ? irALinea : null} />
              {editando ? (
                <Editor ref={areaRef} texto={editado} onCambio={setEditado}
                        sinGuardar={sinGuardar} guardando={guardando}
                        onGuardar={validarYGuardar} onCancelar={cancelarEdicion}
                        lineaError={lineaError} />
              ) : (
                <>
                  <SelectorDiff valor={verDiff} onCambio={setVerDiff}
                                hayOriginal={!!selected.source_generado} />
                  <DiffView
                    oldText={verDiff === 'modelo' ? selected.source_generado : baseSource}
                    newText={selected.source} />
                </>
              )}
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

// Con cambios sin guardar, el veredicto que trae el borrador habla de la versión anterior.
// Mostrarlo con su color diría que el código de la pantalla compila, y nadie lo verificó: es
// exactamente la mentira que este panel existe para no contar.
// El mensaje del parser trae, después de la primera línea, un fragmento del código con un
// `^` apuntando a la columna exacta. Renderizarlo como texto corrido colapsa los saltos y deja
// el apuntador flotando al final: la información llegaba y la pantalla la destruía. Va en
// `<pre>` con la misma fuente monoespaciada del editor, que es lo que hace que el `^` caiga
// donde tiene que caer.
function Issue({ issue, onIr }) {
  const [cabecera, ...contexto] = (issue.message || '').split('\n')
  const ubicado = issue.line != null && onIr
  return (
    <li className={issue.level}>
      <span className="issue-level">{issue.level}</span>
      {issue.block && <span className="issue-block">{issue.block}</span>}
      {/* Decir "línea 43" y no poder ir ahí obliga a contar a mano. Con la línea como dato,
          el error es el camino hacia el error. */}
      {ubicado && (
        <button className="ir-a-linea" onClick={() => onIr(issue.line, issue.column)}>
          ir a la línea {issue.line}
        </button>
      )}
      <span className="issue-msg">{cabecera}</span>
      {contexto.length > 0 && (
        <pre className="issue-ctx">{contexto.join('\n')}</pre>
      )}
    </li>
  )
}

function ValidationPanel({ validation, provider, desactualizada, onIrALinea }) {
  const { cls } = desactualizada ? { cls: 'unknown' } : validationState(validation)
  const issues = desactualizada ? [] : (validation?.issues || [])
  if (desactualizada) {
    return (
      <div className="validation unknown">
        <div className="validation-head">
          <span className="badge unknown">sin validar</span>
          <span className="provider">
            editaste el código — el veredicto anterior ya no habla de esto
          </span>
        </div>
        <p className="validation-ok">Guardá para que el parser lo revise.</p>
      </div>
    )
  }
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
            <Issue key={i} issue={issue} onIr={onIrALinea} />
          ))}
        </ul>
      )}
      {issues.length === 0 && cls === 'ok' && (
        <p className="validation-ok">Sin observaciones del parser.</p>
      )}
    </div>
  )
}

// El editor es deliberadamente pobre: un textarea. Lo que se corrige acá son tres líneas —un
// tipo de paso inventado, un estado mal escrito, una concatenación que el lenguaje no tiene—,
// no se escribe un flow desde cero. Para eso está el archivo `.tflow` en el repositorio.
const Editor = React.forwardRef(function Editor(
  { texto, onCambio, sinGuardar, guardando, onGuardar, onCancelar, lineaError }, ref,
) {
  const gutterRef = useRef(null)
  const total = texto.split('\n').length

  // El textarea no emite su scroll a nadie, así que la columna de números se sincroniza a
  // mano. Sin esto los números se quedan quietos mientras el código se mueve, que es peor que
  // no tenerlos: mienten.
  const sincronizar = (e) => {
    if (gutterRef.current) gutterRef.current.scrollTop = e.target.scrollTop
  }

  return (
    <div className="editor">
      <div className="editor-head">
        <span className="editor-label">
          Corrigiendo la fuente
          {sinGuardar && <em className="sin-guardar"> · sin guardar</em>}
        </span>
        <div className="editor-actions">
          <button className="approve" onClick={onGuardar} disabled={guardando || !sinGuardar}>
            {guardando ? 'Validando…' : 'Validar y guardar'}
          </button>
          <button onClick={onCancelar}>Cerrar editor</button>
        </div>
      </div>
      <div className="editor-cuerpo">
        {/* `aria-hidden`: para un lector de pantalla esta columna es ruido — repite números
            sin contenido. El textarea de al lado ya tiene el código. */}
        <div className="editor-gutter" ref={gutterRef} aria-hidden="true">
          {Array.from({ length: total }, (_, i) => (
            <div key={i} className={i + 1 === lineaError ? 'linea-error' : ''}>{i + 1}</div>
          ))}
        </div>
        <textarea
          ref={ref}
          className="editor-area"
          spellCheck={false}
          /* Sin ajuste de línea: si el textarea parte una línea larga en dos filas, un número
             deja de corresponder a una fila y toda la columna se corre. */
          wrap="off"
          value={texto}
          onChange={(e) => onCambio(e.target.value)}
          onScroll={sincronizar}
        />
      </div>
    </div>
  )
})

// Contra qué se compara. Por defecto contra la versión desplegada, que es la pregunta del
// revisor ("¿qué cambia esto de lo que ya está corriendo?"). Contra el original del modelo
// solo aparece si alguien editó: es la otra pregunta, la de quién escribió qué.
function SelectorDiff({ valor, onCambio, hayOriginal }) {
  if (!hayOriginal) return null
  return (
    <div className="selector-diff">
      <button className={valor === 'desplegada' ? 'activo' : ''}
              onClick={() => onCambio('desplegada')}>
        contra lo desplegado
      </button>
      <button className={valor === 'modelo' ? 'activo' : ''}
              onClick={() => onCambio('modelo')}>
        contra lo que generó el modelo
      </button>
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
