import React, { useEffect, useState } from 'react'
import { api } from './api.js'

// Pantalla de dominio: las entidades del negocio y su ficha 360.
//
// Es la otra mitad de la operación. La bandeja muestra **trámites**; acá está el **sujeto**:
// la persona, el curso, el vínculo entre los dos. Y es donde se ve lo más característico de
// la plataforma — cambiarle el estado a una entidad hace que **aparezcan procesos que nadie
// pidió**, porque una regla los disparó.
//
// Como en el alta de expedientes, la pantalla no sabe nada del dominio: los tipos de entidad,
// sus campos y sus transiciones salen del `.tflow` desplegado.

export default function Dominio({ onError, onInfo }) {
  const [tipos, setTipos] = useState([])          // [{name, fields, lifecycle}]
  const [relDefs, setRelDefs] = useState([])      // [{name, from_ref, to_ref, fields, lifecycle}]
  const [tipo, setTipo] = useState('')
  const [entidades, setEntidades] = useState([])
  const [ficha, setFicha] = useState(null)
  const [creando, setCreando] = useState(false)
  const [cargando, setCargando] = useState(false)

  // Los tipos de entidad salen del dominio **ya mergeado**, en una sola llamada. La primera
  // versión los juntaba pidiendo el AST de cada flow desplegado, y eso son N+1 requests que
  // crecen con cada deploy: con once flows ya chocaba contra el rate limit del gateway. El
  // catálogo sigue siendo el código — lo que cambió es quién lo arma.
  useEffect(() => {
    (async () => {
      try {
        const dominio = await api.getDomain()
        setTipos(dominio.entities || [])
        setRelDefs(dominio.relations || [])
        if (dominio.entities?.length) elegirTipo(dominio.entities[0].name, dominio.entities)
      } catch (e) {
        onError(e.message)
      }
    })()
  }, [])

  const elegirTipo = async (nombre, disponibles = tipos) => {
    setTipo(nombre)
    setFicha(null)
    setCreando(false)
    if (!nombre) return setEntidades([])
    setCargando(true)
    try {
      setEntidades(await api.listEntities(nombre))
      onError('')
    } catch (e) {
      onError(e.message)
    } finally {
      setCargando(false)
    }
  }

  const abrir = async (id) => {
    try {
      setFicha(await api.vista360(tipo, id))
      onError('')
    } catch (e) {
      onError(e.message)
    }
  }

  const refrescar = async () => {
    const abierta = ficha?.id
    await elegirTipo(tipo)
    if (abierta) await abrir(abierta)
  }

  const definicion = tipos.find((t) => t.name === tipo)

  const transicionar = async (via) => {
    const actor = localStorage.getItem('tflow_actor') || ''
    try {
      const r = await api.transitionEntity(tipo, ficha.id, via, actor || null)
      // El aviso nombra la consecuencia, no la acción: lo interesante de una transición no es
      // que el estado cambió, es lo que se puso en marcha sin que nadie lo pidiera.
      onInfo(`${ficha.id} pasó a ${r.estado}. Si alguna regla escuchaba este cambio, ya disparó su proceso.`)
      await refrescar()
    } catch (e) {
      onError(e.message)
    }
  }

  // Las relaciones que **salen** de este tipo de entidad. `from_ref.parts` es ["entity", "nino"],
  // así que el segundo elemento es el tipo. Vincular en el otro sentido sería otra relación, no
  // esta al revés: la dirección la declara el DSL.
  const relacionesDesdeAca = relDefs.filter((r) => r.from_ref?.parts?.[1] === tipo)

  const transicionarRelacion = async (relTipo, relId, via) => {
    const actor = localStorage.getItem('tflow_actor') || ''
    try {
      const r = await api.transitionRelation(relTipo, relId, via, actor || null)
      onInfo(`El vínculo ${relTipo} pasó a ${r.estado}. Si alguna regla lo escuchaba, ya disparó.`)
      await refrescar()
    } catch (e) {
      onError(e.message)
    }
  }

  return (
    <div className="columns dominio">
      <aside>
        <div className="aside-head">
          <h2>Dominio</h2>
          <div className="aside-acciones">
            <button onClick={() => setCreando(!creando)} disabled={!tipo}>+ Nueva</button>
            <button onClick={refrescar} disabled={cargando || !tipo}>
              {cargando ? '...' : 'Actualizar'}
            </button>
          </div>
        </div>

        <label className="selector-tipo">
          Tipo
          <select value={tipo} onChange={(e) => elegirTipo(e.target.value)}>
            <option value="">elegí…</option>
            {tipos.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}
          </select>
        </label>

        {creando && definicion && (
          <NuevaEntidad
            definicion={definicion}
            onError={onError}
            onCreada={async (id) => {
              setCreando(false)
              onInfo(`${tipo} ${id} creado en estado inicial.`)
              await elegirTipo(tipo)
              await abrir(id)
            }}
          />
        )}

        <ul className="draft-list">
          {entidades.map((e) => (
            <li key={e.entity_id}
                className={ficha?.id === e.entity_id ? 'active' : ''}
                onClick={() => abrir(e.entity_id)}>
              <strong>{e.campos?.nombre || e.entity_id}</strong>
              <span className={`status ${e.estado}`}>{e.estado}</span>
              <p>{e.entity_id}</p>
            </li>
          ))}
          {entidades.length === 0 && !cargando && tipo && (
            <li className="empty">No hay {tipo} todavía</li>
          )}
        </ul>
      </aside>

      <main>
        {ficha ? (
          <Ficha360 ficha={ficha} definicion={definicion} onTransicionar={transicionar}
                    relaciones={relacionesDesdeAca} tipos={tipos}
                    onTransicionarRelacion={transicionarRelacion}
                    onVinculado={refrescar} onError={onError} onInfo={onInfo} />
        ) : (
          <div className="placeholder">Elegí una entidad para ver su ficha</div>
        )}
      </main>
    </div>
  )
}

function Ficha360({ ficha, definicion, onTransicionar, relaciones = [], tipos = [],
                    onTransicionarRelacion, onVinculado, onError, onInfo }) {
  // Las transiciones posibles no son todas las del ciclo de vida: son las que salen **del
  // estado actual**. Ofrecer las demás sería ofrecer un error — el motor las rechaza, y la
  // interfaz no tiene por qué dejar que alguien lo descubra a los golpes.
  const salidas = (definicion?.lifecycle?.transitions || [])
    .filter((t) => t.from_state === ficha.estado_actual)

  return (
    <>
      <div className="review-head">
        <h2>{ficha.campos?.nombre || ficha.id}{' '}
          <span className={`status ${ficha.estado_actual}`}>{ficha.estado_actual}</span></h2>
        <div className="actions">
          {salidas.map((t) => (
            <button key={t.via} onClick={() => onTransicionar(t.via)}>
              {t.via} → {t.to_state}
            </button>
          ))}
          {salidas.length === 0 && <span className="hint">estado final</span>}
        </div>
      </div>

      <p className="desc">{ficha.entity} · <code>{ficha.id}</code></p>

      <div className="ficha-grid">
        <Campos campos={ficha.campos} />

        <BloqueRelaciones ficha={ficha} relaciones={relaciones} tipos={tipos}
                          onTransicionar={onTransicionarRelacion}
                          onVinculado={onVinculado} onError={onError} onInfo={onInfo} />

        {/* Acá se cierra el círculo con la bandeja: los procesos que corren sobre esta
            entidad. Si aparece uno que nadie disparó a mano, lo puso una regla. */}
        <Bloque titulo="Procesos en curso" vacio="Ningún proceso en curso.">
          {(ficha.procesos_activos || []).map((p, n) => (
            <li key={n}>
              <span className={`status ${p.status}`}>{p.status}</span>
              {/* La 360 devuelve el nombre del proceso en `flow` (view360.py). Leerlo como
                  `flow_name` —el nombre que usa el listado de instancias— dejaba el renglón
                  sin nombre: solo se veía el estado y el paso. */}
              <strong>{p.flow || p.flow_name}</strong>
              {p.current_step && <> · en <code>{p.current_step}</code></>}
            </li>
          ))}
        </Bloque>

        <Bloque titulo="Alertas" vacio="Sin alertas.">
          {(ficha.alertas || []).map((a, n) => (
            <li key={n}>
              <span className="badge warn">{a.severidad}</span>
              <strong>{a.rule}</strong> · {a.mensaje}
            </li>
          ))}
        </Bloque>
      </div>

      <div className="timeline">
        <h3>Historia</h3>
        {(ficha.timeline || []).length === 0 && <p className="hint">Sin eventos.</p>}
        <ol>
          {(ficha.timeline || []).map((e, n) => (
            <li key={n}>
              <span className="t-hora">{fecha(e.occurred_at || e.fecha)}</span>
              <span className="t-paso"><code>{e.evento}</code></span>
            </li>
          ))}
        </ol>
      </div>
    </>
  )
}

// Los vínculos de esta entidad, con lo que se puede hacer sobre cada uno.
//
// Una relación **no es un campo ni un join**: tiene estado propio y ciclo de vida. El caso de
// negocio de este dominio lo deja claro — la inscripción de una niña a un curso nace
// PENDIENTE, se activa, y puede completarse o abandonarse. Y es su activación, no la de la
// niña, la que dispara el proceso de acceso a la plataforma.
function BloqueRelaciones({ ficha, relaciones, tipos, onTransicionar,
                            onVinculado, onError, onInfo }) {
  const [vinculando, setVinculando] = useState(false)
  const activas = ficha.relaciones_activas || []

  return (
    <div className="bloque">
      <div className="bloque-head">
        <h3>Vínculos</h3>
        {relaciones.length > 0 && (
          <button onClick={() => setVinculando(!vinculando)}>+ Vincular</button>
        )}
      </div>

      {vinculando && (
        <NuevaRelacion
          desde={ficha}
          relaciones={relaciones}
          tipos={tipos}
          onError={onError}
          onCreada={async (tipoRel, estado) => {
            setVinculando(false)
            onInfo(`Vínculo ${tipoRel} creado en estado ${estado}.`)
            await onVinculado()
          }}
        />
      )}

      <ul className="lista-bloque">
        {activas.map((r, n) => {
          const def = relaciones.find((d) => d.name === r.tipo)
          const salidas = (def?.lifecycle?.transitions || [])
            .filter((t) => t.from_state === r.estado)
          return (
            <li key={r.relation_id || n} className="rel">
              <div className="rel-datos">
                <span className={`status ${r.estado}`}>{r.estado}</span>
                <strong>{r.tipo}</strong>
                {/* El otro extremo del vínculo viene anidado con el nombre del tipo destino
                    (`curso`), así que se busca por el tipo declarado y no por una clave fija. */}
                {otroExtremo(r, def)}
              </div>
              {salidas.length > 0 && (
                <div className="rel-acciones">
                  {salidas.map((t) => (
                    <button key={t.via}
                            onClick={() => onTransicionar(r.tipo, r.relation_id, t.via)}>
                      {t.via} → {t.to_state}
                    </button>
                  ))}
                </div>
              )}
            </li>
          )
        })}
        {activas.length === 0 && <li className="hint">Sin vínculos todavía.</li>}
      </ul>
    </div>
  )
}

function otroExtremo(rel, def) {
  const destino = def?.to_ref?.parts?.[1]
  const nodo = destino ? rel[destino] : null
  if (!nodo) return null
  return <span className="rel-destino">· {nodo.nombre || nodo.id}</span>
}

// Vincular esta entidad con otra. El tipo de relación declara con qué tipo se vincula
// (`to_ref`), así que el desplegable de destino se llena con esas entidades y no con un campo
// de texto donde escribir un id que no existe.
function NuevaRelacion({ desde, relaciones, tipos, onCreada, onError }) {
  const [tipoRel, setTipoRel] = useState(relaciones.length === 1 ? relaciones[0].name : '')
  const [destinos, setDestinos] = useState([])
  const [destino, setDestino] = useState('')
  const [valores, setValores] = useState({})
  const [enviando, setEnviando] = useState(false)

  const def = relaciones.find((r) => r.name === tipoRel)
  const tipoDestino = def?.to_ref?.parts?.[1]

  useEffect(() => {
    setDestino('')
    setDestinos([])
    if (!tipoDestino) return
    api.listEntities(tipoDestino)
      .then(setDestinos)
      .catch((e) => onError(e.message))
  }, [tipoDestino])

  const campos = def?.fields || []

  const enviar = async (e) => {
    e.preventDefault()
    setEnviando(true)
    try {
      const fields = {}
      for (const c of campos) {
        const bruto = valores[c.name]
        if (bruto === undefined || bruto === '') continue
        fields[c.name] = c.type === 'number' ? Number(bruto) : bruto
      }
      const r = await api.createRelation(tipoRel, desde.id, destino, fields)
      onCreada(tipoRel, r.estado)
    } catch (err) {
      onError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <form className="nuevo" onSubmit={enviar}>
      {relaciones.length > 1 && (
        <label>
          tipo de vínculo
          <select value={tipoRel} onChange={(e) => setTipoRel(e.target.value)}>
            <option value="">elegí…</option>
            {relaciones.map((r) => <option key={r.name} value={r.name}>{r.name}</option>)}
          </select>
        </label>
      )}

      <label>
        {tipoDestino || 'destino'}<span className="req">*</span>
        <select value={destino} onChange={(e) => setDestino(e.target.value)}>
          <option value="">elegí…</option>
          {destinos.map((d) => (
            <option key={d.entity_id} value={d.entity_id}>
              {d.campos?.nombre || d.entity_id}
            </option>
          ))}
        </select>
      </label>
      {tipoDestino && destinos.length === 0 && (
        <p className="hint">No hay {tipoDestino} para vincular. Creá uno primero.</p>
      )}

      {campos.map((c) => (
        <label key={c.name}>
          {c.name}{c.required && <span className="req">*</span>}
          <CampoEntidad campo={c} valor={valores[c.name] ?? ''}
                        onChange={(v) => setValores({ ...valores, [c.name]: v })} />
        </label>
      ))}

      <button type="submit" className="approve"
              disabled={enviando || !tipoRel || !destino ||
                        campos.some((c) => c.required && !String(valores[c.name] ?? '').trim())}>
        {enviando ? 'Vinculando…' : 'Vincular'}
      </button>
    </form>
  )
}

function Campos({ campos }) {
  const entradas = Object.entries(campos || {})
  return (
    <div className="bloque">
      <h3>Datos</h3>
      <ul className="campos">
        {entradas.map(([k, v]) => (
          <li key={k}><span className="k">{k}</span><span className="v">{String(v)}</span></li>
        ))}
        {entradas.length === 0 && <li className="hint">Sin datos.</li>}
      </ul>
    </div>
  )
}

function Bloque({ titulo, vacio, children }) {
  const hay = React.Children.count(children) > 0
  return (
    <div className="bloque">
      <h3>{titulo}</h3>
      <ul className="lista-bloque">
        {hay ? children : <li className="hint">{vacio}</li>}
      </ul>
    </div>
  )
}

// El alta de una entidad usa el mismo mecanismo que el alta de un expediente: los campos y
// sus tipos salen del DSL. La diferencia es que acá también se elige el identificador, porque
// una entidad de negocio suele tener uno propio (una cédula, un número de cliente).
function NuevaEntidad({ definicion, onCreada, onError }) {
  const [id, setId] = useState('')
  const [valores, setValores] = useState({})
  const [enviando, setEnviando] = useState(false)
  const campos = definicion.fields || []

  const enviar = async (e) => {
    e.preventDefault()
    setEnviando(true)
    try {
      const fields = {}
      for (const c of campos) {
        const bruto = valores[c.name]
        if (bruto === undefined || bruto === '') continue
        fields[c.name] = c.type === 'number' ? Number(bruto) : bruto
      }
      const r = await api.createEntity(definicion.name, id.trim(), fields)
      onCreada(r.entity_id)
    } catch (err) {
      onError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <form className="nuevo" onSubmit={enviar}>
      <label>
        identificador<span className="req">*</span>
        <input value={id} onChange={(e) => setId(e.target.value)} placeholder="ej. 12345" />
      </label>
      {campos.map((c) => (
        <label key={c.name}>
          {c.name}{c.required && <span className="req">*</span>}
          <CampoEntidad campo={c} valor={valores[c.name] ?? ''}
                        onChange={(v) => setValores({ ...valores, [c.name]: v })} />
        </label>
      ))}
      <button type="submit" className="approve"
              disabled={enviando || !id.trim() ||
                        campos.some((c) => c.required && !String(valores[c.name] ?? '').trim())}>
        {enviando ? 'Creando…' : `Crear ${definicion.name}`}
      </button>
    </form>
  )
}

function CampoEntidad({ campo, valor, onChange }) {
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
    <input type={tipos[campo.type] || 'text'} value={valor}
           placeholder={campo.optional ? 'opcional' : campo.type}
           onChange={(e) => onChange(e.target.value)} />
  )
}

function fecha(iso) {
  try {
    return new Date(iso).toLocaleString('es-UY',
      { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch { return '—' }
}
