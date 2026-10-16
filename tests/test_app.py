"""Exercise the actual desktop controls and worker lifecycle."""

import time
import tkinter as tk

import nbformat
import pytest

from notebook_press.app import App


@pytest.fixture(scope="module")
def desktop():
    try:
        app = App()
    except tk.TclError as error:
        pytest.skip(f"Desktop display is unavailable: {error}")
    app.withdraw()
    yield app
    if app.process:
        app._cancel()
        app.process.wait(timeout=10)
    app.destroy()


def test_desktop_latex_export(desktop, tmp_path, monkeypatch):
    monkeypatch.setattr("notebook_press.app.settings_path", lambda: tmp_path / "settings.json")
    app = desktop
    try:
        source = tmp_path / "notebook.ipynb"
        nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell("# Desktop export")]), source)
        app.source.set(str(source))
        app.destination.set(str(tmp_path / "exports"))
        app.want_pdf.set(False)
        app._start()
        deadline = time.monotonic() + 45
        while app.process and time.monotonic() < deadline:
            app.update()
            time.sleep(0.03)
        assert app.process is None, "Worker did not finish"
        assert app.result, app.log.get("1.0", "end")
        assert app.status.get() == "Your export is ready."
        from pathlib import Path
        assert (Path(app.result) / "latex" / "notebook.tex").is_file()
    finally:
        if app.process:
            app._cancel()
            app.process.wait(timeout=10)


def test_cancel_cleans_the_job_workspace(desktop, tmp_path, monkeypatch):
    monkeypatch.setattr("notebook_press.app.settings_path", lambda: tmp_path / "settings.json")
    app = desktop
    try:
        app.withdraw()
        source = tmp_path / "long.ipynb"
        nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell("# Many cells\n\n$E=mc^2$") for _ in range(500)]), source)
        app.source.set(str(source))
        app.destination.set(str(tmp_path / "exports"))
        app.want_pdf.set(False)
        app._start()
        deadline = time.monotonic() + 30
        while app.process and not app.stage_workspace and time.monotonic() < deadline:
            app.update()
            time.sleep(0.03)
        assert app.stage_workspace
        app._cancel()
        while app.process and time.monotonic() < deadline:
            app.update()
            time.sleep(0.03)
        assert app.process is None
        assert app.status.get() == "Cancelled"
        assert list((tmp_path / "exports").iterdir()) == []
    finally:
        if app.process:
            app._cancel()
            app.process.wait(timeout=10)
