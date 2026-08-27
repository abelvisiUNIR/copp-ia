import React, { useEffect, useState } from 'react'
import { api } from './api.js'

// Pantalla operativa: la bandeja de expedientes y su ficha.
//
// Responde las dos preguntas que hoy solo se podían contestar por API: **qué está esperando
// mi firma** y **por qué se frenó este expediente**. Los datos ya estaban todos en
// `instance_transitions` y en el error de la instancia; lo que faltaba era mirarlos sin
// armar un request a mano.
//
// Quién opera acá no es quien escribe flows: es un gerente aprobando una venta. Por eso la
// pantalla no pide saber cómo se llama el step —lo toma de `current_step`— ni qué es un
// `instance_id`.

// Los estados que le importan a un operador, y en el orden en que le importan. Los
// terminales quedan afuera del default a propósito: la bandeja es trabajo por hacer, no
// historial.
const FILTROS = [
  { key: 'WAITING_SIGNAL', label: 'Esperando firma' },
  { key: 'FAILED', label: 'Fallados' },
  { key: 'IN_PROGRESS', label: 'En curso' },
  { key: '', label: 'Todos' },
]

// Vocabulario convencional de señales. **No lo define la plataforma: lo define cada flow**
// en su `stage` de decisión (`venta_internet_hogar` compara contra "approve"). Por eso los
// dos botones son un atajo para el caso frecuente y no la única salida: si un flow usa otras
// palabras, se escriben en el campo de al lado.
const SENALES = [
  { valor: 'approve', label: 'Aprobar', cls: 'approve' },
  { valor: 'reject', label: 'Rechazar', cls: 'reject' },
]

export default function Operacion({ onError, onInfo }) {
  const [filtro, setFiltro] = useState('WAITING_SIGNAL')
  const [instancias, setInstancias] = useState([])
  const [abierta, setAbierta] = useState(null)
  const [actor, setActor] = useState(localStorage.getItem('tflow_actor') || '')
  const [cargando, setCargando] = useState(false)
  const [iniciando, setIniciando] = useState(false)

  const refrescar = async (estado = filtro, mantener = abierta?.instance_id) => {
    setCargando(true)
    try {
      const lista = await api.listInstances(estado)
      setInstancias(lista)
      onError('')
      // Si la que estaba abierta sigue existiendo, se recarga para reflejar el cambio de
      // estado; si no, se cierra. Sin esto, después de firmar quedaba en pantalla una ficha
      // que decía WAITING_SIGNAL sobre un expediente ya resuelto.
      if (mantener) await abrir(mantener, false)
    } catch (e) {
      onError(e.message)
    } finally {
      setCargando(false)
    }
  }

  const abrir = async (id, limpiarAviso = true) => {
    try {
      setAbierta(await api.getInstance(id))
      if (limpiarAviso) onInfo('')
      onError('')
    } catch (e) {
      onError(e.message)
    }
  }

  useEffect(() => { refrescar(filtro, null) }, [filtro])

  const guardarActor = (valor) => {
    setActor(valor)
    localStorage.setItem('tflow_actor', valor)
  }

  const firmar = async (senal) => {
    if (!actor.trim()) {
      onError('Poné tu usuario antes de firmar: queda registrado en el expediente.')
      return
    }
    try {
      await api.signal(abierta.instance_id, abierta.current_step, senal, actor.trim())
      onInfo(`Señal "${senal}" enviada sobre ${abierta.current_step}.`)
      await refrescar()
    } catch (e) {
      onError(e.message)
    }
  }

  const reintentar = async () => {
    try {
      await api.retry(abierta.instance_id)
      onInfo('Reintento disparado.')
      await refrescar()
    } catch (e) {
      onError(e.message)
    }
  }

  return (
    <div className="columns ops">
      <aside>
        <div className="aside-head">
          <h2>Expedientes</h2>
          <div className="aside-acciones">
            <button onClick={() => setIniciando(!iniciando)}>+ Nuevo expediente</button>
            <button onClick={() => refrescar()} disabled={cargando}>
              {cargando ? '...' : 'Actualizar'}
            </button>
          </div>
        </div>

        {iniciando && (
          <NuevoExpediente
            onError={onError}
            onIniciado={async (id, proceso) => {
              setIniciando(false)
              onInfo(`Expediente de ${proceso} iniciado.`)
              // Recién creado está en TRIGGERED, no en WAITING_SIGNAL: si el filtro siguiera
              // en "Esperando firma" el expediente no aparecería y parecería que no se creó.
              setFiltro('')
              await abrir(id, false)
            }}
          />
        )}

        <div className="filtros">
          {FILTROS.map((f) => (
            <button key={f.key}
                    className={filtro === f.key ? 'activo' : ''}
                    onClick={() => { setFiltro(f.key); setAbierta(null) }}>
              {f.label}
            </button>
          ))}
        </div>

        <ul className="draft-list">
          {instancias.map((i) => (
            <li key={i.instance_id}
                className={abierta?.instance_id === i.instance_id ? 'active' : ''}
                onClick={() => abrir(i.instance_id)}>
              <strong>{i.flow_name}</strong>
              <span className={`status ${i.status}`}>{i.status}</span>
              <p>{i.current_step ? `en ${i.current_step}` : 'sin step actual'} · {hace(i.updated_at)}</p>
            </li>
          ))}
          {instancias.length === 0 && !cargando && (
            <li className="empty">Nada en este estado</li>
          )}
        </ul>
      </aside>

      <main>
        {abierta ? (
          <>
            <div className="review-head">
              <h2>{abierta.flow_name} <span className={`status ${abierta.status}`}>
                {abierta.status}</span></h2>
              <div className="actions">
                {abierta.status === 'WAITING_SIGNAL' && (
                  <FirmaAcciones step={abierta.current_step} onFirmar={firmar} />
                )}
                {abierta.status === 'FAILED' && (
                  <button className="approve" onClick={reintentar}>Reintentar</button>
                )}
              </div>
            </div>

            <p className="desc">
              Versión {abierta.flow_version} · iniciado {hace(abierta.created_at)}
              {abierta.correlation_id && (
                // Cuando el proceso lo disparó una regla y no una persona, acá se ve cuál.
                // Es la diferencia entre "alguien pidió esto" y "el sistema reaccionó solo".
                <> · origen <code>{abierta.correlation_id}</code></>
              )}
            </p>

            <div className="operador">
              <label>
                Tu usuario
                <input value={actor} onChange={(e) => guardarActor(e.target.value)}
                       placeholder="nombre.apellido" />
              </label>
              <span className="hint">Queda asentado en el expediente junto a la firma.</span>
            </div>

            {abierta.error && <PanelError error={abierta.error} />}

            <LineaDeTiempo transiciones={abierta.transitions || []}
                           status={abierta.status}
                           step={abierta.current_step} />
          </>
        ) : (
          <div className="placeholder">Elegí un expediente para ver qué le pasó</div>
        )}
      </main>
    </div>
  )
}

// Iniciar un expediente sin salir de la bandeja.
//
// El formulario **no está escrito acá**: se genera desde el bloque `input` que el proceso
// declara en su `.tflow`, que viaja en el AST del flow desplegado. Si mañana la venta pide un
// campo más, el formulario lo pide solo. Escribir a mano un formulario por proceso sería
// contradecir la premisa del producto: el proceso es el código.
function NuevoExpediente({ onIniciado, onError }) {
  const [flows, setFlows] = useState([])
  const [flow, setFlow] = useState('')
  const [procesos, setProcesos] = useState([])
  const [proceso, setProceso] = useState('')
  const [valores, setValores] = useState({})
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    api.listFlows()
      .then((f) => {
        setFlows(f)
        if (f.length === 1) elegirFlow(f[0].name)
      })
      .catch((e) => onError(e.message))
  }, [])

  const elegirFlow = async (nombre) => {
    setFlow(nombre)
    setProceso('')
    setProcesos([])
    setValores({})
    if (!nombre) return
    try {
      const def = await api.getFlow(nombre)
      const encontrados = Object.values(def.ast?.processes || {})
      setProcesos(encontrados)
      // Un flow con un solo proceso no merece un selector de un elemento.
      if (encontrados.length === 1) setProceso(encontrados[0].name)
    } catch (e) {
      onError(e.message)
    }
  }

  const campos = procesos.find((p) => p.name === proceso)?.input || []

  const enviar = async (e) => {
    e.preventDefault()
    setEnviando(true)
    try {
      const payload = {}
      for (const c of campos) {
        const bruto = valores[c.name]
        if (bruto === undefined || bruto === '') continue   // los opcionales no viajan vacíos
        payload[c.name] = c.type === 'number' ? Number(bruto) : bruto
      }
      const { instance_id } = await api.execute(proceso, payload)
      onIniciado(instance_id, proceso)
    } catch (err) {
      onError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <form className="nuevo" onSubmit={enviar}>
      <label>
        Flow
        <select value={flow} onChange={(e) => elegirFlow(e.target.value)}>
          <option value="">elegí…</option>
          {flows.map((f) => <option key={f.name} value={f.name}>{f.name}</option>)}
        </select>
      </label>

      {procesos.length > 1 && (
        <label>
          Proceso
          <select value={proceso} onChange={(e) => { setProceso(e.target.value); setValores({}) }}>
            <option value="">elegí…</option>
            {procesos.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
          </select>
        </label>
      )}

      {campos.map((c) => (
        <label key={c.name}>
          {c.name}{c.required && <span className="req">*</span>}
          <CampoDeclarado campo={c}
                          valor={valores[c.name] ?? ''}
                          onChange={(v) => setValores({ ...valores, [c.name]: v })} />
        </label>
      ))}

      {proceso && campos.length === 0 && (
        <p className="hint">Este proceso no declara entradas.</p>
      )}

      <button type="submit" className="approve"
              disabled={!proceso || enviando ||
                        campos.some((c) => c.required && !String(valores[c.name] ?? '').trim())}>
        {enviando ? 'Iniciando…' : 'Iniciar expediente'}
      </button>
    </form>
  )
}

// El tipo del campo sale del DSL, así que el control también. Un `enum` con sus valores es un
// desplegable y no un campo de texto donde equivocarse.
function CampoDeclarado({ campo, valor, onChange }) {
  if (campo.enum_values?.length) {
    return (
      <select value={valor} onChange={(e) => onChange(e.target.value)}>
        <option value="">—</option>
        {campo.enum_values.map((v) => <option key={v} value={v}>{v}</option>)}
      </select>
    )
  }
  const tipos = { number: 'number', date: 'date', datetime: 'datetime-local' }
  return (
    <input type={tipos[campo.type] || 'text'}
           value={valor}
           placeholder={campo.optional ? 'opcional' : campo.type}
           onChange={(e) => onChange(e.target.value)} />
  )
}

function FirmaAcciones({ step, onFirmar }) {
  const [otra, setOtra] = useState('')
  return (
    <div className="firma">
      {SENALES.map((s) => (
        <button key={s.valor} className={s.cls} onClick={() => onFirmar(s.valor)}>
          {s.label}
        </button>
      ))}
      <input className="senal-otra" value={otra} placeholder="otra señal"
             onChange={(e) => setOtra(e.target.value)} />
      <button disabled={!otra.trim()} onClick={() => onFirmar(otra.trim())}>Enviar</button>
      <span className="hint">sobre <code>{step}</code></span>
    </div>
  )
}

// El error de una instancia trae el step donde ocurrió y un mensaje que ya viene clasificado
// como transitorio o permanente. Mostrar el step es la mitad de la respuesta a "por qué se
// frenó": sin él, el operador sabe que falló pero no dónde.
function PanelError({ error }) {
  const permanente = String(error.message || '').includes('permanente')
  return (
    <div className="panel-error">
      <div className="panel-error-head">
        <strong>Falló en {error.step || 'un paso sin nombre'}</strong>
        <span className={`badge ${permanente ? 'bad' : 'warn'}`}>
          {permanente ? 'error permanente' : 'error transitorio'}
        </span>
      </div>
      <p>{error.message}</p>
      {permanente && (
        <p className="hint">
          Un error permanente no se arregla reintentando: hay que corregir la causa
          (configuración, datos o el flow) antes de volver a intentarlo.
        </p>
      )}
    </div>
  )
}

function LineaDeTiempo({ transiciones, status, step }) {
  return (
    <div className="timeline">
      <h3>Línea de tiempo</h3>
      {transiciones.length === 0 && <p className="hint">Sin transiciones registradas.</p>}
      <ol>
        {transiciones.map((t, n) => (
          <li key={n}>
            <span className="t-hora">{hora(t.occurred_at)}</span>
            <span className="t-paso">
              <span className={`status ${t.to}`}>{t.to}</span>
              {t.step_name && <> en <code>{t.step_name}</code></>}
            </span>
            {t.actor_id && <span className="t-actor">por {t.actor_id}</span>}
          </li>
        ))}
        {status === 'WAITING_SIGNAL' && (
          // El estado actual no es una transición todavía: es lo que falta. Se muestra como
          // parte de la misma lista porque la pregunta del operador es "¿dónde está?", y la
          // respuesta está tanto en lo que pasó como en lo que se está esperando.
          <li className="esperando">
            <span className="t-hora">ahora</span>
            <span className="t-paso">esperando firma en <code>{step}</code></span>
          </li>
        )}
      </ol>
    </div>
  )
}

function hora(iso) {
  try {
    return new Date(iso).toLocaleTimeString('es-UY', { hour: '2-digit', minute: '2-digit' })
  } catch { return '—' }
}

function hace(iso) {
  try {
    const seg = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
    if (seg < 60) return 'recién'
    const min = Math.floor(seg / 60)
    if (min < 60) return `hace ${min} min`
    const hs = Math.floor(min / 60)
    if (hs < 24) return `hace ${hs} h`
    return `hace ${Math.floor(hs / 24)} d`
  } catch { return '' }
}
