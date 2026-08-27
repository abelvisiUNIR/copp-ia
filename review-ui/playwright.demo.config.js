import { defineConfig, devices } from '@playwright/test'

// Configuración **solo para la demo**, aparte de `playwright.config.js`.
//
// Existe separada por dos motivos. El primero es que la demo se mira: corre con ventana
// visible y con `slowMo`, así que tarda minutos donde la suite tarda segundos. El segundo es
// que CI usa el config de siempre, cuyo `testDir` es `./tests` — al vivir en `./demo`, este
// recorrido **no entra al pipeline** y no lo hace más lento ni más frágil.
//
//   npx playwright test --config=playwright.demo.config.js
//
// Requiere el stack levantado (`docker compose up -d`) con `ceibal` y
// `venta_internet_hogar` desplegados.

const BASE_URL = process.env.REVIEW_UI_URL || 'http://localhost:3100'

// Milisegundos entre acciones. Bajalo si te resulta lento de mirar, subilo si querés explicar
// mientras corre.
const RITMO = Number(process.env.DEMO_SLOWMO || 900)

export default defineConfig({
  testDir: './demo',
  workers: 1,
  fullyParallel: false,
  // Un recorrido completo con pausas para mirar no entra en los 30 s de un test común.
  timeout: 10 * 60 * 1000,
  expect: { timeout: 15000 },
  reporter: [['list']],
  use: {
    baseURL: BASE_URL,
    // Headed por default: la demo se mira. `DEMO_HEADLESS=1` sirve para verificar que el
    // recorrido sigue funcionando sin abrirle una ventana a nadie.
    headless: process.env.DEMO_HEADLESS === '1',
    viewport: { width: 1600, height: 900 },
    launchOptions: { slowMo: RITMO },
    // Queda el video del recorrido para volver a verlo o compartirlo sin repetirlo en vivo.
    video: { mode: 'on', size: { width: 1600, height: 900 } },
    trace: 'on',
  },
  outputDir: './demo-resultados',
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
