import { expect, test } from '@playwright/test'

// Recorrido completo de la plataforma, para mirar.
//
// No es un test de regresión: es la demo. Hace el camino de negocio entero por la interfaz —
// dar de alta el sujeto, vincularlo, ver que el sistema reacciona solo, atender el trámite que
// espera a una persona, y cerrar el círculo generando un proceso nuevo con IA.
//
// Corre con ventana visible y en cámara lenta:
//
//   cd review-ui
//   npx playwright test --config=playwright.demo.config.js
//
// Cada paso imprime en consola qué está haciendo y **qué mirar** en la pantalla, así se puede
// narrar mientras corre. Los identificadores llevan un sufijo de tiempo, así que se puede
// repetir todas las veces que haga falta sin limpiar la base.

const API_KEY = process.env.TELEFLOW_API_KEY || 'dev-key-change-me'
const SUF = Date.now().toString().slice(-6)
const NINO = `ana-${SUF}`
const CURSO = `robotica-${SUF}`

/** Narra el paso en la consola, para poder seguir la demo sin mirar el código. */
function narrar(titulo, mirar) {
  console.log(`\n▶ ${titulo}`)
  if (mirar) console.log(`  👁  ${mirar}`)
}

/** Pausa para que el ojo alcance a leer lo que acaba de pasar. */
async function respirar(page, ms = 2500) {
  await page.waitForTimeout(ms)
}

test('recorrido completo de negocio', async ({ page }) => {
  // ---------------------------------------------------------------- preparación
  await page.goto('/')
  await page.evaluate((k) => localStorage.setItem('tflow_api_key', k), API_KEY)
  await page.evaluate(() => localStorage.setItem('tflow_actor', 'gerencia.demo'))
  await page.reload()

  // ============================================================ ACTO 1 · el sujeto
  await test.step('Acto 1 · Dar de alta a la estudiante', async () => {
    narrar('Creamos la estudiante en el dominio',
           'nace en REGISTRADO, y ese estado lo declara el ciclo de vida del .tflow')
    await page.getByRole('button', { name: 'Dominio' }).click()
    await page.locator('.dominio .selector-tipo select').selectOption('nino')
    await page.getByRole('button', { name: '+ Nueva' }).click()

    const form = page.locator('.nuevo')
    await form.locator('label', { hasText: 'identificador' }).locator('input').fill(NINO)
    await form.locator('label', { hasText: 'ci' }).locator('input').fill(`5.111.${SUF}-3`)
    await form.locator('label', { hasText: 'nombre' }).locator('input').fill('Ana Pérez')
    await form.locator('label', { hasText: 'fecha_nac' }).locator('input').fill('2014-03-01')
    await form.locator('label', { hasText: 'departamento' }).locator('input').fill('Montevideo')
    // `nivel` es un enum en el DSL, así que la interfaz lo ofrece como desplegable.
    await form.locator('label', { hasText: 'nivel' }).locator('select').selectOption('primaria')
    await respirar(page)

    await page.getByRole('button', { name: 'Crear nino' }).click()
    await expect(page.locator('.review-head .status')).toHaveText('REGISTRADO')
    await respirar(page)
  })

  await test.step('Acto 1 · Activarla', async () => {
    narrar('Activamos a la estudiante',
           'solo se ofrece "activar": es la única transición válida desde REGISTRADO')
    await page.getByRole('button', { name: /^activar → / }).click()
    await expect(page.locator('.review-head .status')).toHaveText('ACTIVO')
    narrar('Ahora las acciones son otras',
           'inscribir, graduar y desactivar — las salidas de ACTIVO, no las de antes')
    await respirar(page)
  })

  // ============================================================ ACTO 2 · el catálogo
  await test.step('Acto 2 · Publicar un curso', async () => {
    narrar('Creamos el curso')
    await page.locator('.dominio .selector-tipo select').selectOption('curso')
    await page.getByRole('button', { name: '+ Nueva' }).click()
    const form = page.locator('.nuevo')
    await form.locator('label', { hasText: 'identificador' }).locator('input').fill(CURSO)
    await form.locator('label', { hasText: 'nombre' }).locator('input').fill('Robótica Básica')
    await form.locator('label', { hasText: 'area' }).locator('select').selectOption('robotica')
    await respirar(page)
    await page.getByRole('button', { name: 'Crear curso' }).click()

    narrar('Aparece cupo 30, que nadie cargó',
           'es el default declarado en el modelo, no en la interfaz')
    await expect(page.locator('.campos')).toContainText('30')
    await respirar(page)

    narrar('Publicamos el curso',
           'ATENCIÓN al bloque "Procesos en curso": va a aparecer uno que nadie inició')
    await page.getByRole('button', { name: /^publicar → / }).click()
    await expect(page.locator('.review-head .status')).toHaveText('DISPONIBLE')

    // La regla `notificar_oferta` escucha `curso.disponible` y dispara un proceso. Si se llega
    // a tiempo se lo ve en vuelo, pero **no se afirma acá**: el proceso dura menos de un
    // segundo, así que verlo depende de ganarle una carrera. Afirmar sobre eso daría un test
    // que falla o pasa según la máquina, y encima escondería el hecho real — que el proceso
    // existió — detrás de un problema de tiempos. La prueba dura va en el Acto 4, sobre la
    // bandeja, donde el expediente queda con la regla que lo disparó escrita en su origen.
    const enVuelo = page.locator('.bloque', { hasText: 'Procesos en curso' })
    if (await enVuelo.getByText('notificar_oferta').count() > 0) {
      narrar('Lo agarramos en vuelo: notificacion_oferta_curso',
             'lo disparó la regla notificar_oferta al escuchar el evento curso.disponible')
    } else {
      narrar('El proceso ya terminó, dura menos de un segundo',
             'lo vamos a ver igual en la bandeja, con la regla que lo disparó — Acto 4')
    }
    // Lo que sí es durable: el evento que la regla escuchó quedó en la historia.
    await expect(page.locator('.timeline')).toContainText('curso.disponible')
    await respirar(page, 4000)
  })

  // ============================================================ ACTO 3 · el vínculo
  await test.step('Acto 3 · Inscribir a la estudiante', async () => {
    narrar('Volvemos a la ficha de la estudiante y la vinculamos al curso')
    await page.locator('.dominio .selector-tipo select').selectOption('nino')
    await page.locator('.dominio .draft-list li', { hasText: NINO }).first().click()
    await page.getByRole('button', { name: '+ Vincular' }).click()

    const form = page.locator('.nuevo')
    narrar('El destino es un desplegable con los cursos que existen',
           'no un campo donde escribir un id que puede no existir')
    await form.locator('label', { hasText: 'curso' }).locator('select').selectOption(CURSO)
    await form.locator('label', { hasText: 'fecha_inscripcion' }).locator('input')
      .fill('2026-08-25')
    await form.locator('label', { hasText: 'modalidad' }).locator('select')
      .selectOption('virtual')
    await respirar(page)

    await page.getByRole('button', { name: 'Vincular', exact: true }).click()
    narrar('El vínculo nace en PENDIENTE',
           'una inscripción no es una fila de cruce: tiene estado propio y ciclo de vida')
    await expect(page.locator('.lista-bloque .rel')).toContainText('PENDIENTE')
    await respirar(page)

    narrar('Y ahora lo activamos',
           'este es el momento: no vamos a pedir ningún proceso, solo activar el vínculo')
    await page.locator('.rel-acciones').getByRole('button', { name: /^activar → / }).click()
    await expect(page.locator('.lista-bloque .rel')).toContainText('ACTIVA')
    await respirar(page, 4000)
  })

  // ============================================================ ACTO 4 · lo que pasó solo
  await test.step('Acto 4 · Los procesos que nadie pidió', async () => {
    narrar('Vamos a Operación, filtro Todos',
           'hay expedientes que nadie inició, cada uno con la regla que lo disparó')
    await page.getByRole('button', { name: 'Operación' }).click()
    await page.locator('.filtros').getByRole('button', { name: 'Todos' }).click()
    await expect(page.locator('.ops .draft-list li').first()).toBeVisible()

    // La prueba dura de que el sistema reaccionó solo: abrimos el expediente más reciente y
    // su origen tiene que nombrar la **regla** que lo disparó, no una persona.
    await page.locator('.ops .draft-list li').first().click()
    await expect(page.locator('.desc')).toContainText('rule:', { timeout: 15000 })
    narrar('Miren el "origen" del expediente',
           'dice rule:<regla>:<evento> — nadie lo pidió, lo puso en marcha una regla')
    await respirar(page, 4000)

    // El proceso de acceso al LMS falla a propósito: el sistema externo no existe acá.
    narrar('Abrimos el que falló',
           'dice EN QUÉ PASO falló, que el error es permanente, y por qué reintentar no alcanza')
    await page.locator('.filtros').getByRole('button', { name: 'Fallados' }).click()
    const fallados = page.locator('.ops .draft-list li')
    if (await fallados.count() > 0 &&
        await fallados.first().getAttribute('class') !== 'empty') {
      await fallados.first().click()
      await expect(page.locator('.panel-error')).toBeVisible()
      await respirar(page, 4000)
    } else {
      narrar('(no hay fallados en este stack, seguimos)')
    }
  })

  // ============================================================ ACTO 5 · el trámite humano
  await test.step('Acto 5 · Una venta que espera una firma', async () => {
    narrar('Iniciamos una venta desde la bandeja',
           'el formulario sale del bloque input que declara el proceso')
    await page.locator('.filtros').getByRole('button', { name: 'Esperando firma' }).click()
    await page.getByRole('button', { name: '+ Nuevo expediente' }).click()
    await page.locator('.nuevo select').first().selectOption('venta_internet_hogar')
    await page.locator('.nuevo label', { hasText: 'cliente_id' }).locator('input').fill(NINO)
    await page.locator('.nuevo label', { hasText: 'producto' }).locator('input')
      .fill('fibra-300')
    await respirar(page)
    await page.getByRole('button', { name: 'Iniciar expediente' }).click()

    // Recién creado el expediente está en TRIGGERED: el motor es asíncrono y todavía no
    // llegó al human_task. La bandeja **no se refresca sola** —es una limitación conocida de
    // esta versión— así que acá se aprieta Actualizar, igual que lo haría una persona.
    await respirar(page, 1500)
    await page.getByRole('button', { name: 'Actualizar' }).click()

    narrar('Se durmió esperando a un humano',
           'el renglón ámbar "ahora · esperando firma" no es historia: es lo que falta')
    await expect(page.locator('.timeline li.esperando')).toBeVisible({ timeout: 20000 })
    await respirar(page, 4000)

    narrar('Firmamos como gerencia.demo',
           'después de firmar, la línea de tiempo va a decir QUIÉN firmó')
    await page.getByRole('button', { name: 'Aprobar' }).click()
    await expect(page.locator('.banner.info')).toContainText('approve')
    await respirar(page)

    await page.locator('.filtros').getByRole('button', { name: 'Todos' }).click()
    await page.locator('.ops .draft-list li').first().click()
    await expect(page.locator('.timeline')).toContainText('gerencia.demo')
    narrar('Ahí está la firma, atribuida',
           'sin usuario la interfaz no deja firmar: una firma sin responsable no es una firma')
    await respirar(page, 4000)
  })

  // ============================================================ ACTO 6 · el círculo completo
  await test.step('Acto 6 · Un proceso nuevo, escrito por IA', async () => {
    const nuevo = `reclamo_corte_${SUF}`
    narrar('Pedimos un proceso nuevo describiéndolo en castellano')
    await page.getByRole('button', { name: 'Revisión de flows' }).click()
    await page.getByRole('button', { name: '+ Nuevo' }).click()
    await page.locator('.compose input').first().fill(nuevo)
    await page.locator('.compose textarea').fill(
      'Proceso de reclamo por corte de servicio: se registra el reclamo, ' +
      'un tecnico lo evalua en terreno y se notifica al cliente el resultado')
    await respirar(page)
    await page.getByRole('button', { name: 'Generar borrador' }).click()

    narrar('Se revisa como un pull request',
           'el badge dice si COMPILA, y el borrador avisa que salió del stub y no de un modelo real')
    await page.getByText(nuevo, { exact: true }).first().click()
    await expect(page.locator('.validation')).toBeVisible()
    await respirar(page, 4000)

    narrar('Lo aprobamos y queda desplegado')
    page.on('dialog', async (d) => d.accept(d.message().includes('Versión') ? '1.0.0' : 'demo'))
    await page.getByRole('button', { name: 'Aprobar y desplegar' }).click()
    await expect(page.locator('.banner.info')).toContainText('desplegado')
    await respirar(page)

    narrar('Y cierra el círculo: ya se puede iniciar un expediente con él',
           'lo describió una persona, lo escribió un modelo, lo aprobó otra, y ya es ejecutable')
    await page.getByRole('button', { name: 'Operación' }).click()
    await page.getByRole('button', { name: '+ Nuevo expediente' }).click()
    await expect(page.locator('.nuevo select').first()).toContainText(nuevo)
    await respirar(page, 5000)
  })

  console.log('\n✔ Recorrido completo. El video queda en review-ui/demo-resultados/.\n')
})
