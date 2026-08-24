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
