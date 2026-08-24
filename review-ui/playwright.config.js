import { defineConfig, devices } from '@playwright/test'

// La UI se prueba contra el stack levantado (`docker compose up -d`), igual que los e2e de
// Python: nginx sirve el bundle en :3100 y proxea /api al gateway. Levantar un dev server
// aparte probaría un artefacto distinto del que se despliega.
const BASE_URL = process.env.REVIEW_UI_URL || 'http://localhost:3100'

export default defineConfig({
  testDir: './tests',
  // Sin paralelismo: los tests comparten los borradores del stack, y una suite de 6 tests no
  // gana nada corriendo en paralelo salvo intermitencias.
  workers: 1,
  fullyParallel: false,
  // En CI un test que falla suele ser el stack todavía arrancando, no un bug.
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'list' : [['list']],
  use: {
    baseURL: BASE_URL,
    // Solo cuando algo falla: no llenar el disco con capturas de corridas verdes.
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
