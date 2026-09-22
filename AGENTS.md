# AGENTS.md

Reglas para agentes de codificación que trabajen en este repositorio.

- **Lee primero `docs/ARCHITECTURE.md` y `docs/MCP.md`** antes de tocar
  código; explican por qué está organizado así.
- **Los scripts `.ps1` se quedan en ASCII** y deben funcionar en Windows
  PowerShell 5.1 y en PowerShell 7.
- **El núcleo (`db.py`, `dice.py`, `context.py`, `delta.py`,
  `consistency.py`, `jsonx.py`, `export.py`) no importa FastAPI.** Es
  lógica pura, testeable sin servidor. Si necesitas HTTP, ese código va en
  `api.py`, nunca al revés.
- **`mcp_server.py` es un script independiente.** Solo importa la
  librería estándar, `httpx` y `mcp` — nunca nada de `scheherazades_hoard`.
  Cada tool es un envoltorio fino sobre `POST /api/agent/<tool>`; la
  lógica real vive en `api.py` y está testeada con `TestClient`. No
  dupliques lógica en el adaptador MCP.
- **Todo lo que puede hacer un agente, puede hacerlo también una persona
  desde la interfaz, y viceversa**, a través de los mismos endpoints
  `/api/agent/*`. No añadas una ruta o un tool que solo sirva a uno de los
  dos.
- **Cada función de `store.py` que escribe acepta `commit: bool = True`.**
  Si añades una función de escritura nueva, respeta ese patrón — es lo
  que permite que `delta.py` aplique varios cambios en una sola
  transacción atómica (`SAVEPOINT`).
- **Nunca `window.confirm` / `window.alert` en el frontend.** Congelan la
  pestaña cuando la controla un agente de automatización de navegador.
  Usa el patrón de confirmación en dos pasos (`ConfirmButton` en
  `components/ui.tsx`).
- **`npm run build` debe pasar con cero errores de TypeScript** antes de
  dar una tarea de frontend por terminada (`tsc -b && vite build`).
- **Antes de dar algo por hecho, pruébalo.** `pytest tests/ -q` para el
  backend; para cambios de interfaz, levanta la app (`--demo
  --no-browser`) y verifica con Playwright o a mano — no basta con que
  compile.
- **Compatibilidad Windows/Linux siempre.** `pathlib`, no scripts solo de
  shell, `encoding="utf-8"` en cada apertura de texto, nada de rutas
  `/tmp` fijas.
- **Nunca cargues tu propio servidor de modelo.** El backend de modelos
  es compartido: Hoard Link está copiado tal cual en
  `scheherazades_hoard/hoard_link/` (no se edita; para actualizarlo se
  sustituye la carpeta entera y se anota el commit en `VENDORED.txt`) y
  `backend.py` es su envoltorio. Si necesitas un modelo, resuélvelo por
  ahí.
- **Las herramientas del agente devuelven vistas compactas** (`views.py`):
  ids estables, textos cortos y nunca secretos salvo `include_secrets`.
  No devuelvas filas completas de la base de datos por `/api/agent/*`.
- **Un turno y su delta se escriben juntos** con `delta.record_turn()`;
  no apliques un delta por un lado y añadas el turno por otro.
- **Git**: identidad de autor `Luissalet
  <luissalet@users.noreply.github.com>` en cada commit, mensajes en
  inglés con prefijo convencional (`feat:`, `fix:`, `test:`, `docs:`,
  `chore:`), nunca nombres de otras aplicaciones o datos personales.
