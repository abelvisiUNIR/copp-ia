import { expect, test } from '@playwright/test'

// La UI es chica (266 líneas) y lo que importa de ella no es cómo se ve un badge: es que
// **desde acá se despliega código**. Estos tests cubren el camino donde el error es caro —
// aprobar el borrador equivocado, o que rechazar despliegue igual— más la regresión de layout
// que apareció el 2026-07-25 con el build en verde.
//
// Requieren el stack (`docker compose up -d`): nginx sirve el bundle en :3100 y proxea /api.

const API_KEY = process.env.TELEFLOW_API_KEY || 'dev-key-change-me'
const H = { 'X-TeleFlow-API-Key': API_KEY, 'Content-Type': 'application/json' }

/** Crea un borrador por la API, por la misma puerta que usa la UI. */
async function crearBorrador(request, nombre) {
  const r = await request.post('/api/compose', {
    headers: H,
    data: { name: nombre, description: `borrador de prueba para ${nombre}` },
  })
  expect(r.status(), await r.text()).toBe(201)
  return r.json()
}

/** Borrador sintético para probar estados que la API no puede generar. */
function borradorFalso(nombre, validation) {
  return {
    draft_id: `falso-${nombre}`,
    name: nombre,
    description: `borrador sintético ${nombre}`,
    status: 'pending',
    comments: [],
    created_at: '2026-07-25T12:00:00+00:00',
    provider: 'stub',
    validation,
    source: 'process "x" {\n}\n',
    base_source: null,
  }
}

/**
 * Fija qué devuelve el listado (y el detalle) de borradores.
 *
 * Con el proveedor `stub` la API siempre genera borradores que compilan, así que los estados
 * "no compila" y "sin verificar" **no son alcanzables** por la puerta de siempre. Interceptar
 * la respuesta permite probar el render real de esos estados sin agregarle al producto una
 * puerta trasera que solo existiría para los tests.
 */
async function interceptarBorradores(page, borradores) {
  await page.route('**/api/drafts', async (route) => {
    await route.fulfill({ json: borradores })
  })
  await page.route('**/api/drafts/*', async (route) => {
    const id = route.request().url().split('/').pop()
    const encontrado = borradores.find((b) => b.draft_id === id) || borradores[0]
    await route.fulfill({ json: encontrado })
  })
}

async function abrirUI(page) {
  await page.goto('/')
  await page.evaluate((k) => localStorage.setItem('tflow_api_key', k), API_KEY)
  await page.reload()
}

/** Abre un borrador del listado por su nombre. */
async function abrirBorrador(page, nombre) {
  await page.getByText(nombre, { exact: true }).first().click()
  await expect(page.locator('.validation')).toBeVisible()
}

test.describe('revisión de borradores', () => {
  test('aprobar despliega ese borrador', async ({ page, request }) => {
    const nombre = `ui_aprobar_${Date.now()}`
    await crearBorrador(request, nombre)
    await abrirUI(page)
    await abrirBorrador(page, nombre)

    // Los dos prompts de la aprobación: versión y actor.
    const respuestas = ['1.0.0', 'test-e2e']
    page.on('dialog', async (d) => d.accept(respuestas.shift() ?? ''))

    await page.getByRole('button', { name: 'Aprobar y desplegar' }).click()
    await expect(page.locator('.banner.info')).toContainText('Aprobado y desplegado')

    // Lo que importa no es el cartel: es que el flow exista del otro lado.
    const flows = await (await request.get('/api/flows', { headers: H })).json()
    expect(flows.map((f) => f.name)).toContain(nombre)
  })

  test('rechazar no despliega nada', async ({ page, request }) => {
    const nombre = `ui_rechazar_${Date.now()}`
    await crearBorrador(request, nombre)
    await abrirUI(page)
    await abrirBorrador(page, nombre)

    page.on('dialog', async (d) => d.accept('no me convence'))
    await page.getByRole('button', { name: 'Rechazar' }).click()
    await expect(page.locator('.banner.info')).toContainText('rechazado')

    const flows = await (await request.get('/api/flows', { headers: H })).json()
    expect(flows.map((f) => f.name)).not.toContain(nombre)
  })

  test('el borrador muestra su estado de validación y quién lo generó', async ({
    page,
    request,
  }) => {
    const nombre = `ui_validacion_${Date.now()}`
    await crearBorrador(request, nombre)
    await abrirUI(page)
    await abrirBorrador(page, nombre)

    // Con el proveedor `stub` el esqueleto compila, así que el estado esperado es "compila".
    await expect(page.locator('.validation.ok')).toBeVisible()
    await expect(page.locator('.validation')).toContainText('generado por')
    // El stub avisa que no lo escribió un modelo: es el punto del ADR del composer.
    await expect(page.locator('.validation')).toContainText('esqueleto para editar a mano')
  })

  test('el badge de estado no se parte en dos líneas', async ({ page }) => {
    // Regresión del 2026-07-25: el pill "sin verificar" se partía y quedaba colgando fuera de
    // la tarjeta. El build de Vite pasaba y el bundle servido era correcto.
    //
    // Dos cosas que este test aprendió a los golpes:
    //
    // 1. **El estado se intercepta, no se genera.** Con el proveedor `stub` la API siempre
    //    produce borradores que compilan, así que "sin verificar" no es alcanzable por la
    //    puerta de siempre.
    // 2. **El nombre importa.** Con un nombre muy largo el badge cae en una línea propia y no
    //    se parte nunca: el defecto necesita un nombre que deje al pill justo en el borde.
    //    Se usa el mismo con el que apareció.
    //
    // Y la assertion no puede ser "está dentro de la tarjeta": medido con el CSS roto, el
    // pill partido **igual queda dentro** horizontalmente (287 < 303). Lo que lo delata es
    // que el navegador lo renderiza como **dos cajas** en vez de una.
    await interceptarBorradores(page, [borradorFalso('flow_sin_verificar', null)])
    await abrirUI(page)

    const badge = page.locator('.draft-list .badge').first()
    await expect(badge).toHaveText('sin verificar')

    const cajas = await badge.evaluate((el) => el.getClientRects().length)
    expect(cajas, 'el pill se partió en varias líneas').toBe(1)
  })

  test('los tres estados de validación se distinguen', async ({ page }) => {
    // "No sé" no puede parecerse a "está bien": es el punto del ADR del composer.
    await interceptarBorradores(page, [
      borradorFalso('flow_compila', { parses: true, issues: [] }),
      borradorFalso('flow_roto', {
        parses: false,
        issues: [{ level: 'error', message: "falta '}'", block: 'syntax' }],
      }),
      borradorFalso('flow_sin_datos', null),
    ])
    await abrirUI(page)

    const badges = page.locator('.draft-list .badge')
    await expect(badges.nth(0)).toHaveText('compila')
    await expect(badges.nth(1)).toHaveText('no compila')
    await expect(badges.nth(2)).toHaveText('sin verificar')
    // Y no solo el texto: cada estado tiene su propia clase, que es lo que los pinta distinto.
    await expect(badges.nth(0)).toHaveClass(/\bok\b/)
    await expect(badges.nth(1)).toHaveClass(/\bbad\b/)
    await expect(badges.nth(2)).toHaveClass(/\bunknown\b/)
  })

  test('aprobar algo que no compila pide confirmación, y cancelar no despliega', async ({
    page,
  }) => {
    await interceptarBorradores(page, [
      borradorFalso('flow_roto', {
        parses: false,
        issues: [{ level: 'error', message: "falta '}'", block: 'syntax' }],
      }),
    ])
    await abrirUI(page)
    await page.locator('.draft-list li').first().click()

    let desplegado = false
    await page.route('**/api/drafts/*/approve', async (route) => {
      desplegado = true
      await route.fulfill({ status: 200, body: '{}' })
    })

    const dialogos = []
    page.on('dialog', async (d) => {
      dialogos.push(d.message())
      await d.dismiss() // cancelar
    })

    await page.getByRole('button', { name: 'Aprobar y desplegar' }).click()
    await page.waitForTimeout(300)

    expect(dialogos[0]).toContain('NO compila')
    expect(desplegado).toBe(false)
  })

  test('el diff aparece al abrir un borrador', async ({ page, request }) => {
    const nombre = `ui_diff_${Date.now()}`
    await crearBorrador(request, nombre)
    await abrirUI(page)
    await abrirBorrador(page, nombre)

    await expect(page.locator('.diff')).toBeVisible()
    await expect(page.locator('.diff .line.add').first()).toBeVisible()
  })

  test('sin API key la UI avisa en vez de romperse', async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => localStorage.removeItem('tflow_api_key'))
    await page.reload()

    await expect(page.locator('.banner.error')).toBeVisible()
    await expect(page.locator('.banner.error')).toContainText('401')
  })
})

// --------------------------------------------------------- corregir el borrador
//
// El revisor veía el error con línea y columna y no tenía dónde corregirlo: tenía que salir a
// una terminal a cambiar una línea. Estos tests cubren el modo de falla que aparece con el
// editor y que antes no existía: que la pantalla afirme "compila" sobre código que nadie
// verificó.

/** Abre el editor y deja un texto nuevo, sin guardar. */
async function escribirEnElEditor(page, texto) {
  await page.getByRole('button', { name: 'Corregir', exact: true }).click()
  await page.locator('.editor-area').fill(texto)
}

/** Guarda contestando los dos prompts (comentario y actor). */
async function guardar(page, comentario = 'corrección de prueba') {
  const respuestas = [comentario, 'test-e2e']
  page.on('dialog', async (d) => d.accept(respuestas.shift() ?? ''))
  await page.getByRole('button', { name: 'Validar y guardar' }).click()
}

test.describe('corregir un borrador', () => {
  test('guardar revalida contra el parser, en los dos sentidos', async ({ page, request }) => {
    const nombre = `ui_editar_${Date.now()}`
    const draft = await crearBorrador(request, nombre)
    await abrirUI(page)
    await abrirBorrador(page, nombre)
    await expect(page.locator('.validation .badge')).toHaveText('compila')

    // Romperlo a propósito: el veredicto tiene que seguir al código, no quedarse pegado.
    await escribirEnElEditor(page, `${draft.source}\nesto no es DSL valido {`)
    await guardar(page, 'rompo a proposito')
    await expect(page.locator('.validation .badge')).toHaveText('no compila')
    await expect(page.locator('.validation .issues li').first()).toContainText('sintaxis')

    // Y volver a dejarlo bien lo devuelve a verde: la corrección es un ciclo, no un viaje
    // de ida.
    await page.locator('.editor-area').fill(draft.source)
    await page.getByRole('button', { name: 'Validar y guardar' }).click()
    await expect(page.locator('.validation .badge')).toHaveText('compila')
  })

  test('con cambios sin guardar el veredicto anterior no se muestra', async ({
    page, request,
  }) => {
    const nombre = `ui_sucio_${Date.now()}`
    const draft = await crearBorrador(request, nombre)
    await abrirUI(page)
    await abrirBorrador(page, nombre)
    await expect(page.locator('.validation .badge')).toHaveText('compila')

    await escribirEnElEditor(page, `${draft.source}\n// tocado`)

    // Lo caro sería que siguiera diciendo "compila": nadie validó esto todavía.
    await expect(page.locator('.validation .badge')).toHaveText('sin validar')
    await expect(page.locator('.validation')).toContainText('el veredicto anterior ya no habla')
  })

  test('aprobar con cambios sin guardar avisa que se despliega lo guardado', async ({
    page, request,
  }) => {
    const nombre = `ui_aprobar_sucio_${Date.now()}`
    const draft = await crearBorrador(request, nombre)
    await abrirUI(page)
    await abrirBorrador(page, nombre)
    await escribirEnElEditor(page, `${draft.source}\n// cambio que no guardé`)

    const dialogos = []
    page.on('dialog', async (d) => { dialogos.push(d.message()); await d.dismiss() })
    await page.getByRole('button', { name: 'Aprobar y desplegar' }).click()

    expect(dialogos[0]).toContain('sin guardar')
    // Cancelar tiene que cancelar de verdad.
    const flows = await (await request.get('/api/flows', { headers: H })).json()
    expect(flows.map((f) => f.name)).not.toContain(nombre)
  })

  test('el diff contra el modelo aparece recién cuando alguien editó', async ({
    page, request,
  }) => {
    const nombre = `ui_diff_modelo_${Date.now()}`
    const draft = await crearBorrador(request, nombre)
    await abrirUI(page)
    await abrirBorrador(page, nombre)

    // Sin ediciones no hay nada que comparar: el selector no existe.
    await expect(page.locator('.selector-diff')).toHaveCount(0)

    await escribirEnElEditor(page, `${draft.source}\n// linea agregada por una persona`)
    await guardar(page)
    await page.getByRole('button', { name: 'Cerrar editor' }).click()

    await expect(page.locator('.selector-diff')).toBeVisible()
    await page.getByRole('button', { name: 'contra lo que generó el modelo' }).click()
    await expect(page.locator('.line.add')).toContainText('linea agregada por una persona')
  })

  test('un borrador corregido queda marcado en la lista', async ({ page, request }) => {
    const nombre = `ui_marcado_${Date.now()}`
    const draft = await crearBorrador(request, nombre)
    await abrirUI(page)
    await abrirBorrador(page, nombre)

    const fila = page.locator('.draft-list li', { hasText: nombre }).first()
    await expect(fila.locator('.badge.editado')).toHaveCount(0)

    await escribirEnElEditor(page, `${draft.source}\n// revisado a mano`)
    await guardar(page)

    await expect(fila.locator('.badge.editado')).toHaveText('corregido')
  })
})

test.describe('el error como camino al error', () => {
  test('el fragmento con el apuntador se muestra preformateado', async ({ page, request }) => {
    const nombre = `ui_caret_${Date.now()}`
    const draft = await crearBorrador(request, nombre)
    await abrirUI(page)
    await abrirBorrador(page, nombre)

    await escribirEnElEditor(page, `${draft.source}\nentity "roto" { fields { a: ??? } }`)
    await guardar(page, 'rompo para ver el caret')

    // El `^` solo apunta si sobreviven los saltos de línea y la fuente es monoespaciada.
    // Renderizado como texto corrido queda flotando al final y no señala nada.
    const ctx = page.locator('.issue-ctx').first()
    await expect(ctx).toBeVisible()
    await expect(ctx).toContainText('^')
    expect((await ctx.textContent()).split('\n').length).toBeGreaterThan(1)
    await expect(ctx).toHaveCSS('white-space', 'pre')
  })

  test('el error lleva al editor hasta la línea', async ({ page, request }) => {
    const nombre = `ui_ir_linea_${Date.now()}`
    const draft = await crearBorrador(request, nombre)
    await abrirUI(page)
    await abrirBorrador(page, nombre)

    const marcador = 'step.notificación'
    await escribirEnElEditor(
      page,
      `${draft.source}\nprocess "roto" {\n  input { a: string required }\n` +
      `  stage "s" { mode: sequential steps [${marcador}] }\n}\n`,
    )
    await guardar(page, 'identificador con tilde')

    await page.getByRole('button', { name: /ir a la línea/ }).click()

    // Lo que importa no es que el botón exista: es que el cursor termine en la línea del
    // error. Sin esto, "línea 43" obliga a contar a mano.
    const seleccionado = await page.locator('.editor-area').evaluate(
      (el) => el.value.slice(el.selectionStart, el.selectionEnd))
    expect(seleccionado).toContain(marcador)
  })
})

test.describe('la columna de números del editor', () => {
  test('hay un número por línea y la del error queda marcada', async ({ page, request }) => {
    const nombre = `ui_gutter_${Date.now()}`
    const draft = await crearBorrador(request, nombre)
    await abrirUI(page)
    await abrirBorrador(page, nombre)

    const roto = `${draft.source}\nprocess "roto" {\n  input { a: string required }\n` +
      `  stage "s" { mode: sequential steps [step.notificación] }\n}\n`
    await escribirEnElEditor(page, roto)
    await guardar(page, 'identificador con tilde')

    const numeros = page.locator('.editor-gutter div')
    await expect(numeros).toHaveCount(roto.split('\n').length)

    // La línea marcada tiene que ser la que dice el parser, no una cualquiera.
    const linea = Number((await page.getByRole('button', { name: /ir a la línea/ })
      .textContent()).match(/\d+/)[0])
    await expect(page.locator('.editor-gutter .linea-error')).toHaveText(String(linea))
  })

  test('los números no se corren respecto del código', async ({ page, request }) => {
    const nombre = `ui_gutter_align_${Date.now()}`
    const draft = await crearBorrador(request, nombre)
    await abrirUI(page)
    await abrirBorrador(page, nombre)
    await escribirEnElEditor(page, draft.source)

    // Una diferencia de fuente, tamaño, altura de línea o padding entre las dos columnas
    // desalinea los números en silencio: siguen ahí, pero señalan la línea equivocada.
    const [gutter, area] = await Promise.all([
      page.locator('.editor-gutter').evaluate(medir),
      page.locator('.editor-area').evaluate(medir),
    ])
    expect(gutter).toEqual(area)

    // Y una línea larga no puede partirse en dos filas: ahí un número dejaría de corresponder
    // a una fila y toda la columna se correría de ahí para abajo.
    await expect(page.locator('.editor-area')).toHaveAttribute('wrap', 'off')

    function medir(el) {
      const s = getComputedStyle(el)
      return {
        fontFamily: s.fontFamily,
        fontSize: s.fontSize,
        lineHeight: s.lineHeight,
        paddingTop: s.paddingTop,
      }
    }
  })

  test('la columna sigue al código cuando se scrollea', async ({ page, request }) => {
    const nombre = `ui_gutter_scroll_${Date.now()}`
    const draft = await crearBorrador(request, nombre)
    await abrirUI(page)
    await abrirBorrador(page, nombre)

    const largo = `${draft.source}\n${Array.from({ length: 200 }, (_, i) => `// linea ${i}`).join('\n')}`
    await escribirEnElEditor(page, largo)

    await page.locator('.editor-area').evaluate((el) => { el.scrollTop = 900 })
    // Sin sincronizar, los números se quedan quietos mientras el código se mueve.
    await expect.poll(async () => page.locator('.editor-gutter')
      .evaluate((el) => el.scrollTop)).toBe(900)
  })
})
