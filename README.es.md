# El Tesoro de Scheherazade
### ¿Quién sigue vivo? ¿Quién está dónde? ¿Qué les has prometido?
**Un guardián de la coherencia y el estado del mundo para ficción interactiva y partidas de rol — recuerda todo lo que un modelo de lenguaje olvida, y le da al narrador exactamente lo que necesita para la siguiente escena.**

[English](README.md) · [Ejecutar en local](#ejecutar-en-local-en-windows) · [Conectar una IA](docs/MCP.md) · [Portfolio](https://luissalet.github.io/Portfolio/#projects)

![La pantalla de Jugar, a mitad de escena, con la bandeja de dados y el panel de hilos y relojes](docs/media/02-play.png)
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
| Estado del mundo | Entidades (personaje/lugar/facción/objeto/saber/criatura), relaciones, hechos con procedencia, cronología, hilos, relojes, tablas aleatorias — SQLite + FTS5, búsqueda en español sin distinguir acentos | Sin edición multiusuario; un único escritor local |
| Dados | Gramática completa (`NdM`, `+/-`, `kh/kl`/`dh/dl`, explosivos `!`, `adv`/`dis`, dados de hado), ayudantes `check(dc, mod)` y `move(stat)`, reproducibilidad con semilla, registro auditado | Sin renderizado de imágenes de dados físicos |
| Constructor de contexto | `world_context()` determinista, ordenado y con presupuesto de caracteres, con ids citables | El orden es léxico/por reglas, no una búsqueda semántica por embeddings |
| Motor de cambios (delta) | Aplicación atómica (`SAVEPOINT` de SQLite), validación por elemento, deshacer completo del último turno | Un solo nivel de deshacer (el último turno), no una pila de historial completa |
| Narrador (modo autónomo) | Construye el prompt, llama al backend de modelo compartido, analiza narración + delta de forma robusta (JSON en bloque, llaves sueltas, reparación de comas finales) | Sin streaming; un indicador de carga, no texto token a token |
| Comprobación de coherencia | Tres reglas concretas (actuar estando muerto, lugar incoherente, relación contradicha) más un juez por IA opcional que cita los hechos | No detecta contradicciones que ninguna regla cubre y ningún hecho hace explícitas |
| Exportación | Sesión → capítulo en Markdown (con un pulido opcional por IA), biblia del mundo → Markdown, exportación/importación completa en JSON | El pulido tiene instrucciones de no añadir hechos, pero no se verifica formalmente contra el original |
| Ilustraciones | Llama a la API de agente de Prospero's Hoard cuando está en marcha; oculto si no lo está | Requiere esa aplicación aparte; no está integrada en esta |
| Backend de modelo compartido | Resuelve, en este orden, una configuración manual explícita, el registro de modelos de una IA conectada, o un servidor local por loopback; toda función sigue funcionando sin ningún modelo conectado, de forma visible | Implementado como adaptador propio (`backend.py`) con la misma interfaz compartida, en vez del paquete compartido "vendorizado" — ver más abajo |
| Interfaz | Jugar, Biblia, Mapa de relaciones (SVG), Cronología, Hilos y relojes (kanban + relojes como círculos segmentados), Tablas, Sesiones, Registro de dados, Backends, Actividad del asistente, Ajustes; ES/EN, claro/oscuro | El mapa usa una disposición circular fija, no una simulación física |

**Límite — el adaptador de backend compartido.** La convención de esta
familia de aplicaciones es compartir un paquete de "backend de modelo"
vendorizado para que todas resuelvan un modelo de la misma forma. En el
momento de construir esta aplicación, ese paquete compartido lo estaba
terminando otro proceso en paralelo, así que esta aplicación implementa
la misma interfaz pública por su cuenta, en `backend.py` (`resolve()` /
`status()` / `wait_idle()` / `chat()`, los mismos estados y tipos de
error). Sustituirlo por el paquete vendorizado más adelante es un cambio
de ese único archivo; nada más en la aplicación depende de cómo esté
implementado.

## Conectar con Faustus

La aplicación se declara con `faustus-plugin.json`. Arranca la
aplicación y, en Faustus: **Conectores → Aplicaciones cercanas → Añadir**.
Faustus la encuentra escaneando puertos locales y leyendo ese manifiesto.

| Herramienta | Solo lectura | Qué hace |
| --- | --- | --- |
| `story_worlds()` | sí | Lista todos los mundos con sus recuentos y sesión actual |
| `story_world_create(...)` | no | Crea un mundo nuevo |
| `world_context(world, ...)` | sí | El resumen del narrador para la siguiente escena |
| `world_search(world, query, ...)` | sí | Busca entidades/hechos |
| `entity_get(world, ref, ...)` | sí | Una entidad con sus relaciones y hechos |
| `entity_upsert(world, kind, name, ...)` | no | Crea o actualiza una entidad |
| `story_append(world, text, ...)` | no | Registra un turno y aplica un delta |
| `dice_roll(expression, ...)` | no | Tira dados con registro auditado |
| `table_roll(world, table)` | no | Tira en una tabla aleatoria |
| `thread_update(world, thread, ...)` | no | Avanza, resuelve o abandona un hilo |
| `clock_tick(world, clock, ticks=1)` | no | Avanza un reloj |
| `world_check(world, statement)` | sí | Comprueba una afirmación contra los hechos establecidos |
| `session_export(world, ...)` | sí | Exporta un capítulo / la biblia / el JSON completo |
| `story_undo(world)` | no | Revierte el último turno |

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

Haz doble clic en **`Iniciar Scheherazade's Hoard.cmd`** (la primera vez
crea el entorno virtual, instala las dependencias y compila la interfaz
automáticamente; abre la aplicación en tu navegador en cuanto está
lista). Detenla con **`Detener Scheherazade's Hoard.cmd`**.

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
python -m pytest tests/ -q
```

171 pruebas, sin red por defecto (ni red real ni modelo real — los
adaptadores de narrador, backend y Prospero se ejercitan con
`httpx.MockTransport` y llamadas HTTP simuladas), en menos de 10
segundos. Cubren la gramática de dados completa y su reproducibilidad
con semilla, el presupuesto/orden/exclusión de secretos del constructor
de contexto, la validación y aplicación atómica del delta más su
deshacer, la robustez de la extracción de JSON, las reglas del
comprobador de coherencia, la búsqueda FTS insensible a acentos, la
exportación a Markdown/JSON, y una prueba de protocolo MCP que lanza el
adaptador real por stdio contra una instancia viva de la aplicación
(`mcp.client.stdio`, `list_tools` más un ciclo completo de
crear-mundo → tirar → registrar → deshacer).

`npm run build` (dentro de `frontend/`) ejecuta `tsc -b && vite build`
con TypeScript en modo estricto, `noUnusedLocals` y `noUnusedParameters`
activados.

## Privacidad y límites

- Solo escucha en `127.0.0.1`; sin telemetría; sin acceso a red salvo una
  llamada a un modelo que tú provocaste (el backend compartido, o
  Prospero's Hoard para ilustraciones), y ambas son opcionales de forma
  visible — toda función que no necesita un modelo sigue funcionando sin
  él.
- Tus mundos viven en `data/` (excluido de git) como un archivo SQLite
  local. No hay sincronización en la nube ni cuenta de usuario.
- Un personaje muerto puede seguir mencionado en el texto narrado; solo
  *actuar* como uno lo detecta la comprobación de coherencia. Deshacer
  cubre el último turno, no una pila de historial completa.
- La salida estructurada del narrador es un análisis de mejor esfuerzo
  sobre texto libre; una respuesta realmente malformada se conserva como
  narración con `unparsed: true` en vez de descartarse o adivinarse en
  silencio.
