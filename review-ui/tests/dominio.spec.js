import { expect, test } from '@playwright/test'

// Sección de dominio: las entidades del negocio y su ficha 360.
//
// Lo caro acá no es que un dato se vea feo: es **ofrecer una acción imposible**. El ciclo de
// vida de una entidad lo declara el `.tflow`, y si la pantalla ofrece transiciones que el
// estado actual no permite, el operador descubre a los golpes lo que la interfaz tendría que
// saber. Por eso el test central compara los botones contra el lifecycle, no contra una lista
// escrita en el test.
//
// Requieren el stack (`docker compose up -d`) con `ceibal` desplegado.

const API_KEY = process.env.TELEFLOW_API_KEY || 'dev-key-change-me'
const H = { 'X-TeleFlow-API-Key': API_KEY, 'Content-Type': 'application/json' }

async function crearNino(request, id) {
  const r = await request.post('/api/entities/nino', {
    headers: H,
    data: {
      entity_id: id,
      fields: {
        ci: `ui-${id}`, nombre: `Ficha ${id}`, fecha_nac: '2014-03-01',
        departamento: 'Montevideo', nivel: 'primaria',
      },
    },
  })
  expect(r.status(), await r.text()).toBe(201)
}

// El tipo se elige **explícitamente**, nunca se hereda el que la pantalla trae por defecto:
// ese default es el primer tipo del dominio mergeado, así que desplegar un flow nuevo lo
// cambia y la lista pasa a mostrar otra cosa. Un test que dependa de eso falla el día que
// alguien despliega algo sin relación.
async function abrirDominio(page, tipo = 'nino') {
  await page.goto('/')
  await page.evaluate((k) => localStorage.setItem('tflow_api_key', k), API_KEY)
  await page.reload()
  await page.getByRole('button', { name: 'Dominio' }).click()
  const selector = page.locator('.dominio .selector-tipo select')
  await expect(selector).toBeVisible()
  await selector.selectOption(tipo)
}

async function abrirEntidad(page, id) {
  await page.locator('.dominio .draft-list li', { hasText: id }).first().click()
  await expect(page.locator('.ficha-grid')).toBeVisible()
}

test.describe('ficha de una entidad', () => {
  test('la ficha muestra datos, historia y el estado actual', async ({ page, request }) => {
    const id = `ui-ficha-${Date.now()}`
    await crearNino(request, id)
    await abrirDominio(page)
    await abrirEntidad(page, id)

    await expect(page.locator('.review-head .status')).toHaveText('REGISTRADO')
    await expect(page.locator('.campos')).toContainText('Montevideo')
    // La historia sale de `entity_events`, que se escribe sola al crear la entidad.
    await expect(page.locator('.timeline')).toContainText('nino.registrado')
  })

  test('solo se ofrecen las transiciones válidas desde el estado actual', async ({
    page,
    request,
  }) => {
    const id = `ui-transiciones-${Date.now()}`
    await crearNino(request, id)
    await abrirDominio(page)
    await abrirEntidad(page, id)

    // El lifecycle de `nino` sale del flow desplegado, no de este archivo: se lee del AST y
    // se compara contra lo que la pantalla ofrece. Si mañana el DSL agrega una transición,
    // este test sigue siendo correcto sin tocarlo.
    const flow = await (await request.get('/api/flows/ceibal/latest', { headers: H })).json()
    const lifecycle = flow.ast.entities.nino.lifecycle
    const desdeRegistrado = lifecycle.transitions
      .filter((t) => t.from_state === 'REGISTRADO').map((t) => t.via)
    const noValidas = lifecycle.transitions
      .filter((t) => t.from_state !== 'REGISTRADO').map((t) => t.via)

    expect(desdeRegistrado.length).toBeGreaterThan(0)
    const acciones = page.locator('.review-head .actions')
    for (const via of desdeRegistrado) await expect(acciones).toContainText(via)
    for (const via of new Set(noValidas)) {
      if (desdeRegistrado.includes(via)) continue
      await expect(acciones).not.toContainText(via)
    }
  })

  test('transicionar cambia el estado y lo que se puede hacer después', async ({
    page,
    request,
  }) => {
    const id = `ui-activar-${Date.now()}`
    await crearNino(request, id)
    await abrirDominio(page)
    await abrirEntidad(page, id)

    await page.getByRole('button', { name: /^activar/ }).click()
    await expect(page.locator('.banner.info')).toContainText('ACTIVO')

    // El estado cambió de verdad, no solo en pantalla.
    const e = await (await request.get(`/api/entities/nino/${id}`, { headers: H })).json()
    expect(e.estado).toBe('ACTIVO')

    // Y las acciones se recalculan: desde ACTIVO ya no se puede volver a activar.
    //
    // Se compara el nombre completo del botón y no una subcadena: desde ACTIVO **sí** existe
    // `desactivar`, que contiene "activar" adentro. Un `not.toContainText('activar')` fallaría
    // con la pantalla funcionando bien — probado, es lo que pasó al escribir este test.
    await expect(page.locator('.review-head .status')).toHaveText('ACTIVO')
    await expect(page.getByRole('button', { name: /^activar → / })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /^desactivar → / })).toBeVisible()
  })

  test('crear una entidad usa los campos que declara el DSL', async ({ page }) => {
    await abrirDominio(page)
    await page.locator('.dominio .selector-tipo select').selectOption('nino')
    await page.getByRole('button', { name: '+ Nueva' }).click()

    const form = page.locator('.nuevo')
    await expect(form).toContainText('ci')
    await expect(form).toContainText('fecha_nac')
    // `nivel` es un enum en el DSL: tiene que llegar como desplegable con sus valores.
    const nivel = form.locator('label', { hasText: 'nivel' }).locator('select')
    await expect(nivel).toBeVisible()
    await expect(nivel.locator('option')).toContainText(['—', 'primaria', 'secundaria', 'utu'])
  })
})

test.describe('vínculos', () => {
  test('vincular desde la ficha crea la relación en su estado inicial', async ({
    page,
    request,
  }) => {
    const suf = Date.now()
    const nino = `ui-vinc-n-${suf}`
    await crearNino(request, nino)
    await request.post('/api/entities/curso', {
      headers: H,
      data: { entity_id: `ui-vinc-c-${suf}`, fields: { nombre: `Curso V ${suf}`, area: 'robotica' } },
    })

    await abrirDominio(page)
    await abrirEntidad(page, nino)
    await page.getByRole('button', { name: '+ Vincular' }).click()

    // El destino es un desplegable poblado con las entidades del tipo que declara `to_ref`,
    // no un campo donde escribir un id que puede no existir.
    await page.locator('.nuevo label', { hasText: 'curso' }).locator('select')
      .selectOption(`ui-vinc-c-${suf}`)
    await page.locator('.nuevo label', { hasText: 'fecha_inscripcion' }).locator('input')
      .fill('2026-08-25')
    // `exact` importa: "+ Vincular" (abre el formulario) contiene "Vincular" (lo envía), y sin
    // esto el localizador matchea los dos.
    await page.getByRole('button', { name: 'Vincular', exact: true }).click()

    // Nace en el estado inicial que declara su lifecycle, no "activa" por defecto.
    await expect(page.locator('.banner.info')).toContainText('PENDIENTE')
    await expect(page.locator('.lista-bloque .rel')).toContainText('inscripcion')
  })

  test('el vínculo ofrece solo las transiciones válidas desde su estado', async ({
    page,
    request,
  }) => {
    const suf = Date.now()
    const nino = `ui-reltrans-n-${suf}`
    const curso = `ui-reltrans-c-${suf}`
    await crearNino(request, nino)
    await request.post('/api/entities/curso', {
      headers: H,
      data: { entity_id: curso, fields: { nombre: `Curso T ${suf}`, area: 'robotica' } },
    })
    await request.post('/api/relations/inscripcion', {
      headers: H,
      data: {
        from_id: nino, to_id: curso,
        fields: { fecha_inscripcion: '2026-08-25', modalidad: 'virtual' },
      },
    })

    const flow = await (await request.get('/api/flows/ceibal/latest', { headers: H })).json()
    const trans = flow.ast.relations.inscripcion.lifecycle.transitions
    const desdePendiente = trans.filter((t) => t.from_state === 'PENDIENTE').map((t) => t.via)

    await abrirDominio(page)
    await abrirEntidad(page, nino)

    const acciones = page.locator('.lista-bloque .rel .rel-acciones')
    for (const via of desdePendiente) await expect(acciones).toContainText(via)
    // `completar` sale de ACTIVA, así que no puede estar disponible sobre una PENDIENTE.
    await expect(page.getByRole('button', { name: /^completar → / })).toHaveCount(0)
  })
})

test.describe('el dominio reacciona solo', () => {
  test('activar una inscripción hace aparecer un proceso que nadie pidió', async ({
    page,
    request,
  }) => {
    const suf = Date.now()
    const nino = `ui-cadena-n-${suf}`
    const curso = `ui-cadena-c-${suf}`
    await crearNino(request, nino)
    await request.post('/api/entities/curso', {
      headers: H,
      data: { entity_id: curso, fields: { nombre: `Curso ${suf}`, area: 'robotica' } },
    })
    const rel = await (await request.post('/api/relations/inscripcion', {
      headers: H,
      data: {
        from_id: nino, to_id: curso,
        fields: { fecha_inscripcion: '2026-08-25', modalidad: 'virtual' },
      },
    })).json()

    // Esta es la demostración del producto: nadie dispara un proceso. Se activa un vínculo
    // de negocio y una regla lo pone en marcha.
    const r = await request.post(`/api/relations/inscripcion/${rel.relation_id}/transition`, {
      headers: H, data: { via: 'activar' },
    })
    expect(r.status(), await r.text()).toBe(200)

    await abrirDominio(page)
    await abrirEntidad(page, nino)

    // La ficha muestra el vínculo activo…
    await expect(page.locator('.ficha-grid')).toContainText('inscripcion')
    // …y la historia registra el evento que disparó la regla.
    await expect(page.locator('.timeline')).toContainText('inscripcion.activada')
  })
})
