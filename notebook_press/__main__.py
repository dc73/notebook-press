"""Desktop launcher, CLI, and isolated conversion worker."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import traceback

from .engine import ExportRequest, export


def emit(stream, event: str, **data) -> None:
    stream.write(json.dumps({"event": event, **data}, ensure_ascii=False) + "\n")
    stream.flush()


def worker(request_file: str | None, events: str, install: bool = False) -> int:
    with open(events, "w", encoding="utf-8", buffering=1) as stream:
        try:
            if install:
                # Playwright's own CLI works from frozen applications as well.
                # Route its console output to a real file for windowed builds.
                from playwright._impl._driver import compute_driver_executable, get_driver_env
                import subprocess

                node, cli = compute_driver_executable()
                emit(stream, "log", message="Downloading Chromium for PDF export…")
                process = subprocess.Popen([node, cli, "install", "chromium"],
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           env=get_driver_env(), text=True, encoding="utf-8", errors="replace",
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                for line in process.stdout:
                    emit(stream, "log", message=line.rstrip())
                if process.wait():
                    raise RuntimeError("Browser installation failed. See the installation log above.")
                emit(stream, "done", path="", message="PDF browser installed. You can now export notebooks to PDF.")
            else:
                request = ExportRequest(**json.loads(Path(request_file).read_text(encoding="utf-8")))
                result = export(request, lambda message: emit(stream, "log", message=message),
                                lambda path: emit(stream, "workspace", path=str(path)))
                emit(stream, "done", path=str(result), message="Your export is ready.")
            return 0
        except Exception as error:
            emit(stream, "error", message=str(error), detail=traceback.format_exc())
            return 1


def main() -> int:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
        elif hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Export Jupyter notebooks and books to PDF and LaTeX.")
    parser.add_argument("--worker", metavar="REQUEST", help=argparse.SUPPRESS)
    parser.add_argument("--events", help=argparse.SUPPRESS)
    parser.add_argument("--check-desktop", metavar="RESULT", help=argparse.SUPPRESS)
    parser.add_argument("--install-browser", action="store_true", help="Install Chromium for notebook PDFs")
    commands = parser.add_subparsers(dest="command")
    convert = commands.add_parser("export", help="Export without opening the desktop app")
    convert.add_argument("source")
    convert.add_argument("-o", "--output", required=True)
    convert.add_argument("--format", choices=["pdf", "latex", "both"], default="both")
    convert.add_argument("--pdf-engine", choices=["browser", "latex"], default="browser")
    convert.add_argument("--paper", choices=["A4", "Letter"], default="A4")
    convert.add_argument("--hide-code", action="store_true")
    convert.add_argument("--book-command", default="")
    convert.add_argument("--execute", action="store_true", help="Run Python notebook cells before exporting")
    convert.add_argument("--python", dest="python_executable", default="", help="Python interpreter with ipykernel and notebook libraries")
    convert.add_argument("--cell-timeout", type=int, default=600, help="Execution timeout per cell in seconds")
    commands.add_parser("doctor", help="Show installed conversion tools")
    args = parser.parse_args()
    if args.check_desktop:
        # Exercise bundled themes, fonts, images and Tk, not just worker imports.
        from .app import App

        app = App()
        try:
            app.update()
            Path(args.check_desktop).write_text(json.dumps({"desktop": "ready"}), encoding="utf-8")
        finally:
            app.destroy()
        return 0
    if args.worker or (args.install_browser and args.events):
        return worker(args.worker, args.events, args.install_browser)
    if args.install_browser:
        from playwright.__main__ import main as playwright_main

        sys.argv = ["playwright", "install", "chromium"]
        playwright_main()
        return 0
    if args.command == "export":
        try:
            result = export(ExportRequest(source=args.source, destination=args.output,
                                         pdf=args.format != "latex", latex=args.format != "pdf",
                                         pdf_engine=args.pdf_engine, include_code=not args.hide_code,
                                         paper=args.paper, book_command=args.book_command, execute=args.execute,
                                         python_executable=args.python_executable, execution_timeout=args.cell_timeout))
            print(result)
            return 0
        except Exception as error:
            print(f"Export failed: {error}", file=sys.stderr)
            return 1
    if args.command == "doctor":
        from .engine import dependency_report

        for name, ready, detail in dependency_report():
            print(f"{'OK' if ready else '--'}  {name}: {detail}")
        return 0
    from .app import App

    App().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
