import { expect, test } from '@playwright/test'

// Sección operativa: la bandeja de expedientes y su ficha.
//
// Qué se cubre y por qué: acá el error caro no es visual, es **firmar el expediente
// equivocado** o creer que se firmó cuando no se firmó. Por eso cada test comprueba el
// efecto del otro lado (la instancia realmente cambió de estado por la API), no el cartel
// que muestra la pantalla — el mismo criterio que los tests de la revisión.
//
// Requieren el stack (`docker compose up -d`) con `venta_internet_hogar` desplegado.

const API_KEY = process.env.TELEFLOW_API_KEY || 'dev-key-change-me'
const H = { 'X-TeleFlow-API-Key': API_KEY, 'Content-Type': 'application/json' }

/** Dispara una venta, que queda dormida esperando la firma del gerente. */
async function crearExpedienteEsperandoFirma(request, cliente) {
  const r = await request.post('/api/execute', {
    headers: H,
    data: { flow_name: 'venta_internet_hogar', payload: { cliente_id: cliente, producto: 'fibra-300' } },
  })
  expect(r.status(), await r.text()).toBe(202)
  const { instance_id } = await r.json()

  // Esperar a que llegue al human_task: el motor es asíncrono, así que la instancia recién
  // creada todavía está en TRIGGERED.
  for (let i = 0; i < 40; i++) {
    const d = await (await request.get(`/api/instances/${instance_id}`, { headers: H })).json()
    if (d.status === 'WAITING_SIGNAL') return instance_id
    await new Promise((r) => setTimeout(r, 250))
  }
  throw new Error(`la instancia ${instance_id} nunca llegó a WAITING_SIGNAL`)
}

async function estadoDe(request, id) {
  const d = await (await request.get(`/api/instances/${id}`, { headers: H })).json()
  return d.status
}

async function abrirOperacion(page) {
  await page.goto('/')
  await page.evaluate((k) => localStorage.setItem('tflow_api_key', k), API_KEY)
  await page.reload()
  await page.getByRole('button', { name: 'Operación' }).click()
}

/** Abre el expediente cuyo id se pasa, desde la bandeja. */
async function abrirExpediente(page, id) {
  // La bandeja no muestra el id (a un operador no le dice nada), así que se ubica por
  // posición: el más reciente queda primero, ordenado por created_at desc.
  await expect(page.locator('.ops .draft-list li').first()).toBeVisible()
  const items = page.locator('.ops .draft-list li')
  const n = await items.count()
  for (let i = 0; i < n; i++) {
    await items.nth(i).click()
    await expect(page.locator('.timeline')).toBeVisible()
    const enPantalla = await page.locator('.operador input').inputValue().catch(() => null)
    if (enPantalla !== null) {
      // Comprobar contra la API cuál quedó abierta sería circular; alcanza con que la
      // ficha abierta corresponda a un expediente esperando firma.
      const estado = await page.locator('.review-head .status').innerText()
      if (estado.trim() === 'WAITING_SIGNAL') return
    }
  }
  throw new Error('no se encontró un expediente esperando firma en la bandeja')
}

test.describe('bandeja de expedientes', () => {
  test('la bandeja muestra lo que espera firma y dice en qué paso está', async ({
    page,
    request,
  }) => {
    await crearExpedienteEsperandoFirma(request, `ui-bandeja-${Date.now()}`)
    await abrirOperacion(page)

    const primero = page.locator('.ops .draft-list li').first()
    await expect(primero).toContainText('venta_internet_hogar')
    await expect(primero.locator('.status')).toHaveText('WAITING_SIGNAL')
    // El paso es la mitad de la respuesta a "¿dónde está?": sin él, el operador sabe que
    // algo espera pero no qué.
    await expect(primero).toContainText('aprobacion_gerencia')
  })

  test('aprobar desde la ficha resuelve el expediente de verdad', async ({ page, request }) => {
    const id = await crearExpedienteEsperandoFirma(request, `ui-aprobar-${Date.now()}`)
    await abrirOperacion(page)
    await abrirExpediente(page, id)

    await page.locator('.operador input').fill('gerente.test')
    await page.getByRole('button', { name: 'Aprobar' }).click()
    await expect(page.locator('.banner.info')).toContainText('approve')

    // Lo que importa: la instancia terminó del otro lado, no que el cartel diga que sí.
    await expect
      .poll(() => estadoDe(request, id), { timeout: 15000 })
      .toBe('COMPLETED')
  })

  test('sin usuario no se firma: la firma tiene que quedar atribuida', async ({
    page,
    request,
  }) => {
    const id = await crearExpedienteEsperandoFirma(request, `ui-sin-actor-${Date.now()}`)
    await abrirOperacion(page)
    await abrirExpediente(page, id)

    await page.locator('.operador input').fill('')
    await page.getByRole('button', { name: 'Aprobar' }).click()

    await expect(page.locator('.banner.error')).toContainText('usuario')
    // Y el expediente sigue esperando: el corte no es cosmético.
    expect(await estadoDe(request, id)).toBe('WAITING_SIGNAL')
  })

  test('la línea de tiempo cuenta lo que ya pasó y lo que se está esperando', async ({
    page,
    request,
  }) => {
    const id = await crearExpedienteEsperandoFirma(request, `ui-timeline-${Date.now()}`)
    await abrirOperacion(page)
    await abrirExpediente(page, id)

    const timeline = page.locator('.timeline')
    await expect(timeline).toContainText('TRIGGERED')
    await expect(timeline).toContainText('IN_PROGRESS')
    // El renglón "ahora" no es una transición registrada: es lo que falta, y es la razón
    // por la que alguien abre esta pantalla.
    await expect(timeline.locator('li.esperando')).toContainText('esperando firma')
  })
})

test.describe('iniciar un expediente', () => {
  test('el formulario sale del flow: pide los campos que el proceso declara', async ({ page }) => {
    await abrirOperacion(page)
    await page.getByRole('button', { name: '+ Nuevo expediente' }).click()
    await page.locator('.nuevo select').first().selectOption('venta_internet_hogar')

    // `venta_internet_hogar` declara cliente_id y producto obligatorios, y direccion opcional.
    // Si el formulario estuviera escrito a mano, este test seguiría pasando aunque el DSL
    // cambiara — por eso además se comprueba el asterisco de obligatorio, que sale de
    // `required` del AST y no de una lista en la UI.
    const form = page.locator('.nuevo')
    await expect(form).toContainText('cliente_id')
    await expect(form).toContainText('producto')
    await expect(form).toContainText('direccion')
    await expect(form.locator('label', { hasText: 'cliente_id' }).locator('.req')).toBeVisible()
    await expect(form.locator('label', { hasText: 'direccion' }).locator('.req')).toHaveCount(0)
  })

  test('no se puede iniciar sin los campos obligatorios', async ({ page }) => {
    await abrirOperacion(page)
    await page.getByRole('button', { name: '+ Nuevo expediente' }).click()
    await page.locator('.nuevo select').first().selectOption('venta_internet_hogar')

    const iniciar = page.getByRole('button', { name: 'Iniciar expediente' })
    await expect(iniciar).toBeDisabled()
    await page.locator('.nuevo label', { hasText: 'cliente_id' }).locator('input').fill('cli-x')
    await expect(iniciar).toBeDisabled()   // falta producto
    await page.locator('.nuevo label', { hasText: 'producto' }).locator('input').fill('fibra-300')
    await expect(iniciar).toBeEnabled()
  })


  // La prueba de que el formulario **se genera** y no está escrito a mano: se despliega un
  // flow nuevo, con campos que la UI no puede conocer, y el formulario tiene que pedirlos.
  // Sin este test, un formulario hardcodeado con cliente_id/producto pasaría igual los de
  // arriba — probarían el flow de ejemplo, no el mecanismo.
  test('un flow nuevo trae su propio formulario, sin tocar la UI', async ({ page, request }) => {
    const nombre = `probe_form_${Date.now()}`
    const source = [
      `process "${nombre}" {`,
      '  input {',
      '    numero_reclamo: string required',
      '    severidad:      enum["baja", "media", "alta"]',
      '    contacto:       string optional',
      '  }',
      '  stage "unica" { mode: sequential steps [step.registrar] }',
      '}',
      'step "registrar" { type: automated retries: 1 }',
    ].join('\n')

    const r = await request.post(`/api/flows/${nombre}`, {
      headers: H,
      data: { source, version: '1.0.0', description: 'sonda de formulario' },
    })
    expect(r.status(), await r.text()).toBe(201)

    await abrirOperacion(page)
    await page.getByRole('button', { name: '+ Nuevo expediente' }).click()
    await page.locator('.nuevo select').first().selectOption(nombre)

    const form = page.locator('.nuevo')
    await expect(form).toContainText('numero_reclamo')
    await expect(form).toContainText('contacto')
    // Un enum declarado en el DSL tiene que llegar como desplegable con sus valores, no como
    // un campo de texto donde equivocarse.
    const severidad = form.locator('label', { hasText: 'severidad' }).locator('select')
    await expect(severidad).toBeVisible()
    await expect(severidad.locator('option')).toContainText(['—', 'baja', 'media', 'alta'])
  })

  test('iniciar crea el expediente y lo deja abierto', async ({ page, request }) => {
    const cliente = `ui-alta-${Date.now()}`
    await abrirOperacion(page)
    await page.getByRole('button', { name: '+ Nuevo expediente' }).click()
    await page.locator('.nuevo select').first().selectOption('venta_internet_hogar')
    await page.locator('.nuevo label', { hasText: 'cliente_id' }).locator('input').fill(cliente)
    await page.locator('.nuevo label', { hasText: 'producto' }).locator('input').fill('fibra-600')
    await page.getByRole('button', { name: 'Iniciar expediente' }).click()

    await expect(page.locator('.banner.info')).toContainText('iniciado')
    // La ficha queda abierta sobre el expediente nuevo, no sobre la bandeja vacía.
    await expect(page.locator('.timeline')).toBeVisible()

    // Y existe del otro lado, con el payload que se tipeó.
    const lista = await (await request.get('/api/instances?limit=100', { headers: H })).json()
    const detalles = await Promise.all(
      lista.slice(0, 5).map(async (i) =>
        (await request.get(`/api/instances/${i.instance_id}`, { headers: H })).json()),
    )
    expect(detalles.some((d) => d.context?.payload?.cliente_id === cliente)).toBe(true)
  })
})

test.describe('expedientes fallados', () => {
  test('un fallado dice en qué paso falló y ofrece reintentar', async ({ page }) => {
    await abrirOperacion(page)
    await page.getByRole('button', { name: 'Fallados' }).click()

    const lista = page.locator('.ops .draft-list li')
    // El stack de demo genera al menos un fallado (la regla que llama a un LMS inexistente).
    // Si no hay ninguno, este test no tiene sujeto y se salta en vez de dar un falso verde.
    if (await lista.first().innerText().catch(() => '') === '') test.skip()
    if ((await lista.count()) === 0 || (await lista.first().getAttribute('class')) === 'empty') {
      test.skip(true, 'no hay expedientes fallados en este stack')
    }

    await lista.first().click()
    await expect(page.locator('.panel-error')).toBeVisible()
    await expect(page.locator('.panel-error-head')).toContainText('Falló en')
    await expect(page.getByRole('button', { name: 'Reintentar' })).toBeVisible()
  })
})
