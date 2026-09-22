#!/usr/bin/env python3
"""Walk the person use cases in the browser and keep screenshots to read.

Usage:
    python scripts/person_walkthrough.py [base_url] [--out DIR] [--mock-llm URL]

Drives the running app with Playwright (the chromium already installed
under PLAYWRIGHT_BROWSERS_PATH; it never runs `playwright install`),
Spanish interface first, at 1280x800 and 1920x1080,
light and dark. It expects a world named "Velamar" (the one that
scripts/agent_walkthrough.py builds). Every step is timed; screenshots go
to --out (default data-uxtest/shots) and console errors are listed at
the end. With --mock-llm it points Backends at that URL and runs the
standalone narrator several times.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent


def chromium() -> str | None:
    root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"))
    found = sorted(root.glob("chromium-*/chrome-linux/chrome"), reverse=True)
    return str(found[0]) if found else None


class Walk:
    def __init__(self, page: Page, out: Path, base: str):
        self.p, self.out, self.base = page, out, base
        self.console: list[str] = []
        self.timings: list[tuple[str, float]] = []
        page.on("console", lambda m: self.console.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: self.console.append(f"pageerror: {e}"))

    def shot(self, name: str, full: bool = False) -> None:
        self.p.screenshot(path=str(self.out / f"{name}.png"), full_page=full)
        print(f"  shot {name}.png")

    def step(self, name: str, fn) -> None:
        t0 = time.perf_counter()
        try:
            fn()
            dt = time.perf_counter() - t0
            print(f"- {name}: {dt * 1000:.0f} ms")
        except Exception as e:  # keep walking; the report says what broke
            dt = time.perf_counter() - t0
            print(f"- {name}: FAILED after {dt * 1000:.0f} ms: {type(e).__name__}: {str(e)[:300]}")
            self.shot(f"fail-{name.replace(' ', '_')}")
        self.timings.append((name, dt))

    def nav(self, label: str) -> None:
        self.p.locator("nav .nav-item", has_text=label).first.click()
        self.p.wait_for_load_state("networkidle")
        time.sleep(0.3)


def open_velamar(w: Walk) -> None:
    w.p.goto(w.base, wait_until="networkidle")
    w.p.wait_for_selector(".grid-cards .card, .empty-state", timeout=10000)
    w.p.locator(".grid-cards .card", has_text="Velamar").locator(".btn-primary").click()
    w.p.wait_for_selector(".play-layout", timeout=10000)
    time.sleep(0.5)


def run(w: Walk, mock_llm: str | None) -> None:
    p = w.p
    # UC1 - first look and a new world
    w.step("worlds page", lambda: (p.goto(w.base, wait_until="networkidle"), p.wait_for_selector(".grid-cards .card, .empty-state"), w.shot("01-worlds")))

    def new_world():
        p.get_by_role("button", name="Nuevo mundo").click()
        w.shot("02-new-world-form")
        inputs = p.locator(".card input")
        inputs.nth(0).fill("Cuaderno de pruebas")
        p.get_by_role("button", name="Crear").click()
        p.wait_for_load_state("networkidle")
        time.sleep(0.5)
        w.shot("03-after-create")
    w.step("create a world", new_world)

    def empty_world_tour():
        # Where does creating land? Try the Play screen of the empty world.
        if not p.locator(".play-layout").count():
            p.locator(".grid-cards .card", has_text="Cuaderno de pruebas").locator(".btn-primary").click()
            p.wait_for_selector(".play-layout", timeout=10000)
        time.sleep(0.4)
        w.shot("04-empty-play")
        w.nav("Biblia"); w.shot("05-empty-bible")
        w.nav("Hilos y relojes"); w.shot("06-empty-threads")
        w.nav("Sesiones"); w.shot("07-empty-sessions")
    w.step("empty world tour", empty_world_tour)

    # UC1 - first characters and places by hand, then a scene with no model
    def first_entities():
        w.nav("Biblia")
        for kind, name in (("Personaje", "Iria Castro"), ("Lugar", "Hospicio de San Telmo"),
                           ("Lugar", "Muelle Viejo"), ("Personaje", "El Farolero")):
            p.locator(".bible-layout .icon-button").first.click()
            p.locator(".bible-layout .card input").first.fill(name)
            p.locator(".bible-layout .card select").first.select_option(label=kind)
            p.get_by_role("button", name="Crear").click()
            p.wait_for_load_state("networkidle")
            time.sleep(0.3)
        w.shot("08-first-entities")
    w.step("UC1 first entities", first_entities)

    def first_scene():
        w.nav("Jugar")
        w.shot("08b-play-no-scene")
        p.get_by_role("button", name="Cambiar escena").click()
        p.locator(".scene-editor select").select_option(label="Hospicio de San Telmo")
        p.locator(".scene-cast-item", has_text="Iria Castro").locator("input").check()
        p.locator(".scene-editor input[aria-label='Ambiente']").fill("inquietante")
        w.shot("09-scene-editor")
        p.get_by_role("button", name="Aplicar escena").click()
        p.wait_for_load_state("networkidle")
        time.sleep(0.4)
        p.locator(".mode-tab", has_text="Narración").click()
        p.locator(".play-input-box textarea").fill("La lluvia golpea los cristales del hospicio. Alguien ha dejado un farol negro en la escalera.")
        p.get_by_role("button", name="Enviar").click()
        time.sleep(0.4)
        p.locator(".mode-tab", has_text="Acción").click()
        p.locator(".play-input-box textarea").fill("Iria recoge el farol.")
        p.get_by_role("button", name="Enviar").click()
        time.sleep(0.4)
        p.locator(".side-panel .btn", has_text="2d6").first.click()
        p.wait_for_load_state("networkidle")
        time.sleep(0.5)
        w.shot("09b-first-scene-played")
    w.step("UC1 first scene", first_scene)

    # UC7 - the long world, every screen
    w.step("open Velamar", lambda: (open_velamar(w), w.shot("10-play-velamar")))

    def play_scrolled():
        p.locator(".transcript").evaluate("el => el.scrollTop = el.scrollHeight")
        time.sleep(0.3)
        w.shot("11-play-bottom")
    w.step("play transcript bottom", play_scrolled)

    def check_box():
        box = p.locator(".side-panel input").nth(1)
        box.fill("Mateo Lür abre la puerta del hospicio")
        box.press("Enter")
        p.wait_for_load_state("networkidle")
        time.sleep(0.4)
        w.shot("12-check-dead")
        box.fill("Nuño Vidal espera en el Hospicio de San Telmo")
        p.locator(".side-panel .card", has_text="Comprobar continuidad").locator("button").click()
        time.sleep(0.6)
        w.shot("13-check-location")
    w.step("continuity box", check_box)

    def narrate_no_model():
        p.get_by_role("button", name="Narrar").click()
        time.sleep(3)
        w.shot("14-narrate-no-model")
    w.step("narrate without a model", narrate_no_model)

    def bible():
        w.nav("Biblia")
        w.shot("15-bible")
        p.locator("input[placeholder='Buscar…']").fill("farol")
        time.sleep(0.5)
        w.shot("16-bible-search-farol")
        p.locator("input[placeholder='Buscar…']").fill("")
        p.locator(".entity-list-item", has_text="Mateo Lür").first.click()
        time.sleep(0.5)
        w.shot("17-bible-mateo", full=True)
    w.step("bible", bible)

    # UC8 - fix by hand what the model got wrong
    def bible_edit():
        p.locator(".entity-list-item", has_text="Mateo Lür").first.click()
        time.sleep(0.4)
        p.get_by_role("button", name="Editar").click()
        summary = p.locator(".entity-edit textarea").first
        summary.fill("Farolero retirado, sesenta años, manos quemadas. Murió en el Faro Viejo.")
        w.shot("17b-bible-edit-form")
        p.get_by_role("button", name="Guardar").click()
        p.wait_for_load_state("networkidle")
        time.sleep(0.4)
        p.locator(".entity-list-item", has_text="Tobías").first.click()
        time.sleep(0.4)
        p.get_by_role("button", name="Editar").click()
        p.locator(".entity-edit select").select_option(label="desaparecido")
        p.get_by_role("button", name="Guardar").click()
        p.wait_for_load_state("networkidle")
        time.sleep(0.4)
        w.shot("17c-bible-marked-missing")
    w.step("UC8 bible edit", bible_edit)

    for label, name in (("Mapa de relaciones", "18-map"), ("Cronología", "19-timeline"), ("Hilos y relojes", "20-threads"),
                        ("Tablas", "21-tables"), ("Sesiones", "22-sessions"), ("Registro de dados", "23-dice"),
                        ("Actividad del asistente", "24-activity"), ("Backends", "25-backends"), ("Ajustes", "26-settings")):
        w.step(f"screen {label}", lambda label=label, name=name: (w.nav(label), w.shot(name)))

    # UC3 - export a chapter from the UI
    def export_chapter():
        w.nav("Sesiones")
        with p.expect_download(timeout=10000) as dl:
            p.locator("table.simple tbody tr").first.locator("button", has_text="Exportar capítulo").click()
        d = dl.value
        target = w.out / f"ui-{d.suggested_filename}"
        d.save_as(str(target))
        print(f"  downloaded {d.suggested_filename} -> {target} ({target.stat().st_size} bytes)")
    w.step("export chapter", export_chapter)

    # UC4 - standalone narrator against a sloppy model
    if mock_llm:
        def configure():
            w.nav("Backends")
            p.locator("input[placeholder='http://127.0.0.1:8081/v1/chat/completions']").fill(mock_llm)
            p.get_by_role("button", name="Guardar").first.click()
            time.sleep(1.5)
            w.shot("30-backend-mock")
        w.step("configure the model", configure)
        for i in range(1, 7):
            def narrate(i=i):
                w.nav("Jugar")
                ta = p.locator(".play-input-box textarea")
                ta.fill("Iria sale del hospicio con el farol." if i == 1 else "Sigo caminando.")
                t0 = time.perf_counter()
                p.get_by_role("button", name="Narrar").click()
                p.wait_for_selector(".delta-card, .error-banner, [role=alert]", timeout=30000)
                print(f"  narrator reply shown after {(time.perf_counter() - t0) * 1000:.0f} ms")
                time.sleep(0.3)
                w.shot(f"3{i}-narrate-{i}")
                if p.locator(".delta-card").count():
                    p.get_by_role("button", name="Aceptar").click()
                    time.sleep(0.8)
                    p.locator(".transcript").evaluate("el => el.scrollTop = el.scrollHeight")
                    w.shot(f"3{i}-narrate-{i}-accepted")
            w.step(f"narrate sloppy reply {i}", narrate)

    # Undo with the two-step confirm, keyboard only
    def undo():
        w.nav("Jugar")
        b = p.get_by_role("button", name="Deshacer último turno")
        b.click()
        time.sleep(0.3)
        w.shot("40-undo-confirm")
        p.keyboard.press("Escape")
        time.sleep(0.2)
    w.step("undo confirm", undo)

    def keyboard():
        w.nav("Jugar")
        p.locator("body").click(position={"x": 5, "y": 5})
        for _ in range(6):
            p.keyboard.press("Tab")
        w.shot("41-keyboard-focus")
    w.step("keyboard focus", keyboard)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default="http://127.0.0.1:18860")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "data-uxtest" / "shots")
    ap.add_argument("--mock-llm", default=None)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium())
        ctx = browser.new_context(viewport={"width": 1280, "height": 800}, locale="es-ES", accept_downloads=True)
        w = Walk(ctx.new_page(), args.out, args.base)
        run(w, args.mock_llm)
        ctx.close()
        # Big screen, dark, English
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, locale="en-US", color_scheme="dark")
        w2 = Walk(ctx.new_page(), args.out, args.base)
        w2.step("1920 dark play", lambda: (open_velamar(w2), w2.shot("50-play-1920-dark-en")))
        w2.step("1920 dark map", lambda: (w2.nav("Map of relations"), w2.shot("51-map-1920-dark")))
        w2.step("1920 dark bible", lambda: (w2.nav("Bible"), w2.shot("52-bible-1920-dark")))
        ctx.close()
        # Narrow window
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="es-ES")
        w3 = Walk(ctx.new_page(), args.out, args.base)
        w3.step("phone play", lambda: (open_velamar(w3), w3.shot("60-play-phone")))
        ctx.close()
        browser.close()
    print("\nconsole errors/warnings:")
    for line in w.console + w2.console + w3.console:
        print("  " + line[:300])
    slow = [(n, t) for n, t in w.timings + w2.timings + w3.timings if t > 3]
    print("steps over 3 s: " + (", ".join(f"{n} {t:.1f}s" for n, t in slow) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
