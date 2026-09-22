# <img src="frontend/public/favicon.svg" width="28" height="28" alt="" align="center" /> Scheherazade's Hoard
### ¿Quién sigue vivo? ¿Quién está dónde? ¿Qué les has prometido?
**Un guardián de la coherencia y el estado del mundo para ficción interactiva y partidas de rol — recuerda todo lo que un modelo de lenguaje olvida, y le da al narrador exactamente lo que necesita para la siguiente escena.**

[English](README.md) · [Ejecutar en local](#ejecutar-en-local-en-windows) · [Conectar una IA](docs/MCP.md) · [Portfolio](https://luissalet.github.io/Portfolio/#projects)

![La pantalla Jugar, a mitad de escena, con la bandeja de dados y el panel de hilos y relojes](docs/media/02-play-es.png)
*Aplicación real, con datos de demostración ("El Archipiélago de Sal", un escenario original generado por `--demo`).*

## Por qué

Los modelos de lenguaje son buenos narrando y malísimos llevando la
continuidad. Después de una hora de ficción interactiva o una sesión de
rol olvidan quién sabe qué, resucitan personajes muertos, mueven pueblos
de sitio, pierden los hilos abiertos y se inventan las tiradas.
Scheherazade mantiene el **estado del mundo fuera del modelo** —
entidades, relaciones, secretos, lugares, una cronología, hilos abiertos,
relojes, tablas y un registro de dados auditado — y construye para el
narrador un resumen compacto, ordenado y con un presupuesto de caracteres
para la siguiente escena, y después registra lo que esa escena cambió de
verdad. Puede narrar por sí sola con un modelo local compartido, o ceder
sus herramientas a otra IA (Faustus) para que esa IA narre mientras esta
aplicación lo recuerda todo.

## Qué está implementado

| Área | Disponible ahora | Límite |
| --- | --- | --- |
| Estado del mundo | Entidades (personaje/lugar/facción/objeto/saber/criatura) con alias, estadísticas y secretos del máster, relaciones, hechos con procedencia y marca de canon, cronología, hilos, relojes y tablas aleatorias; SQLite + FTS5 con búsqueda que no distingue tildes | Un único escritor local; sin edición multiusuario |
| Dados | `NdM`, `+/-`, `kh/kl/dh/dl`, dados que explotan `!`, `adv(d20)`/`dis(d20)`, dados Fate `dF`; reproducibles con semilla; cada tirada queda en un registro de solo añadir; con un mundo, las tiradas de 2d6 traen su banda PbtA y las de d20 su valor natural y el crítico | Con topes a propósito (200 dados por tirada, 100 caracteres por expresión) |
| Constructor de contexto | `world_context()`: premisa, límites de contenido, escena y reparto actuales, hechos ordenados por relevancia, hilos vivos, relojes a partir de la mitad y últimos turnos, cada línea con un id citable y dentro de un presupuesto de caracteres | El orden es léxico y por reglas, no una búsqueda por embeddings |
| Motor de cambios (delta) | Validación elemento a elemento; después, el delta y su turno en una sola transacción de SQLite; la escena se mantiene de un turno a otro; deshacer retrocede turno a turno dentro de la sesión actual | No hay rehacer; los turnos de una sesión anterior no se pueden deshacer |
| Narrador (modo autónomo) | Construye el prompt, llama al modelo compartido a través de Hoard Link, separa la narración del delta (JSON en bloque, objetos sueltos, reparación de comas finales) y te deja aceptar o rechazar cada cambio propuesto | Sin streaming: una respuesta, con indicador de carga |
| Comprobación de coherencia | Reglas para un personaje muerto que actúa, un personaje situado lejos de donde se le vio por última vez y una relación contradicha (por palabra completa y con alias), más un juez por IA sobre los hechos que coinciden, obligado a citar sus ids; el resultado indica si el juez ha intervenido | Son heurísticas: se le escapan las contradicciones que ninguna regla cubre y ningún hecho recoge |
| Exportación | Sesión como capítulo en Markdown, con pulido opcional por el modelo compartido (si no puede, devuelve el capítulo sin pulir y dice por qué), biblia del mundo en Markdown, exportación e importación completas en JSON | El pulido tiene instrucciones de no añadir hechos, pero no se contrasta con el original; los capítulos de más de 6000 caracteres no se pulen |
| Ilustraciones | «Ilustrar» llama a la API de agente de Prospero's Hoard cuando responde en 127.0.0.1:8815; si no, el botón no aparece | Necesita esa otra aplicación; la imagen se muestra, pero no se guarda en el turno |
| Backend de modelos compartido | Hoard Link incluido sin modificar (`scheherazades_hoard/hoard_link/`): primero la configuración explícita, luego el registro de modelos de Faustus y después los modelos ya cargados en local (llama.cpp, Ollama, servidores compatibles con OpenAI); Ajustes muestra el motivo, permite borrar la configuración manual y nunca devuelve el token | Solo se usa la capacidad de modelo de lenguaje; la aplicación nunca carga un modelo por su cuenta |
| Interfaz | Jugar, Biblia, Mapa de relaciones (SVG), Cronología, Hilos y relojes (kanban y relojes segmentados), Tablas, Sesiones, Registro de dados, Backends, Actividad del asistente, Ajustes; comprobación de continuidad en Jugar; búsqueda sin tildes en la Biblia; en español e inglés, tema claro y oscuro | El mapa usa una disposición circular fija, no una simulación física |

## Conectar con Faustus

La aplicación se declara con `faustus-plugin.json`. Arranca la
aplicación y, en Faustus: **Conectores → Aplicaciones cercanas → Añadir**.
Faustus la encuentra escaneando puertos locales y leyendo ese manifiesto.

Dos formas de jugar con el mismo mundo: conectada, Faustus hace de
narrador y usa las herramientas de abajo (la skill `narrator-loop` le
indica en qué orden); por su cuenta, la aplicación narra con el modelo que
Faustus ya tiene cargado, localizado mediante Hoard Link, así que nada se
carga dos veces.

| Herramienta | Solo lectura | Qué hace |
| --- | --- | --- |
| `story_worlds()` | sí | Lista todos los mundos con sus recuentos y sesión actual |
| `story_world_create(...)` | no | Crea un mundo nuevo |
| `world_context(world, ...)` | sí | El resumen del narrador para la siguiente escena |
| `world_search(world, query, ...)` | sí | Busca entidades/hechos |
| `entity_get(world, ref, ...)` | sí | Una entidad con sus relaciones y hechos |
| `entity_upsert(world, kind, name, ...)` | no | Crea o actualiza una entidad |
| `story_append(world, text, ...)` | no | Registra un turno y aplica un delta, de forma atómica |
| `dice_roll(expression, ...)` | no | Tira dados con registro auditado |
| `table_roll(world, table)` | no | Tira en una tabla aleatoria |
| `thread_update(world, thread, ...)` | no | Avanza, resuelve o abandona un hilo |
| `clock_tick(world, clock, ticks=1)` | no | Avanza un reloj |
| `world_check(world, statement)` | sí | Comprueba una afirmación contra los hechos establecidos |
| `session_export(world, ...)` | sí | Exporta un capítulo / la biblia / el JSON completo, por páginas |
| `story_undo(world)` | no | Revierte el último turno y todo lo que cambió su delta |

Argumentos completos, forma de la respuesta y límites:
[`docs/MCP.md`](docs/MCP.md).

También funciona con cualquier otro cliente MCP por stdio:

```json
{
  "mcpServers": {
    "scheherazade": {
      "command": "/ruta/absoluta/a/scheherazades-hoard/.venv/Scripts/python.exe",
      "args": ["/ruta/absoluta/a/scheherazades-hoard/scheherazades_hoard/mcp_server.py"],
      "env": { "SCHEHERAZADE_URL": "http://127.0.0.1:8816" }
    }
  }
}
```

## Ejecutar en local en Windows

Haz doble clic en **`Iniciar Scheherazade's Hoard.cmd`**. Ejecuta
`scripts/start.ps1`, que busca Python 3.11 o posterior, crea `.venv` e
instala `requirements-lock.txt` (de nuevo cada vez que cambia el lock),
compila la interfaz si falta `frontend/dist` (solo entonces hace falta
Node 22), arranca la aplicación con la raíz del repositorio como
directorio de trabajo, espera a `/api/health` y abre el navegador. Si ya
estaba en marcha, solo abre el navegador. Detenla con
**`Detener Scheherazade's Hoard.cmd`** (`scripts/stop.ps1`), que también
detiene una instancia arrancada por Faustus.

Pasos manuales, desde la raíz del repositorio, en PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
cd frontend; npm ci; npm run build; cd ..
.venv\Scripts\python.exe -m scheherazades_hoard --demo
```

`--demo` usa un mundo sintético generado en `data-demo/` en vez de tu
`data/` real, para que puedas probarlo todo sin tocar (ni necesitar)
ningún dato real. Quita `--demo` para tus propios mundos; añade
`--no-browser` para que no abra la pestaña automáticamente.

## Arquitectura

Módulos, modelo de datos, el motor de cambios atómico y las decisiones
detrás de todo ello: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Pruebas

```
.venv\Scripts\python.exe -m pytest tests/ -q
```

240 pruebas, sin red (ningún modelo real: Hoard Link, el narrador y el
adaptador de Prospero se prueban contra `httpx.MockTransport`), en unos
15 segundos. Cubren la gramática de dados y sus topes, la lectura según
el reglamento, el presupuesto, el orden y la exclusión de secretos del
constructor de contexto, la validación del delta, el turno en una sola
transacción y el deshacer (también con varias actualizaciones de lo mismo
en un delta), la continuidad de la escena, la extracción de JSON, las
reglas de coherencia, la búsqueda sin tildes, la exportación e
importación, el servidor de archivos estáticos frente a recorridos de
ruta, la protección de Host/Origin, el arranque por línea de comandos con
su archivo de pid y su log, y una prueba del protocolo MCP que lanza el
adaptador real por stdio contra una instancia en marcha (`list_tools`,
anotaciones, líneas Keywords y un ciclo de crear, tirar, registrar,
contexto y deshacer).

`npm run build` (dentro de `frontend/`) ejecuta `tsc -b && vite build`
con TypeScript en modo estricto y `noUnusedLocals` y `noUnusedParameters`
activados.

## Privacidad y límites

- Solo escucha en `127.0.0.1`, rechaza otras cabeceras Host y las
  escrituras desde otros sitios, y no se deja incrustar en páginas web.
  Sin telemetría. Las únicas llamadas de red van a servidores de modelos
  de tu equipo (o al Faustus que hayas configurado) y a Prospero's Hoard,
  siempre por loopback.
- Tus mundos viven en `data/` (fuera de git) en un único archivo SQLite;
  el log es `data/logs/app.log` y guarda nombres de herramientas y
  tiempos, nunca texto de la historia, secretos ni tokens.
- Las herramientas del agente no devuelven secretos del máster salvo que
  se pidan con `include_secrets=true`; «Actividad del asistente» lista
  cada llamada del agente, y tus propios clics en la interfaz no aparecen
  ahí.
- La salida estructurada del narrador se extrae de texto libre; una
  respuesta que no se puede interpretar se guarda como narración marcada
  `unparsed`, nunca se rellena a ciegas.
