"""Exercise the actual desktop controls and worker lifecycle."""

import time
import tkinter as tk

import customtkinter as ctk
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


@pytest.mark.parametrize("selection,pdf,latex", [("PDF", True, False), ("LaTeX", False, True), ("Both", True, True)])
def test_format_selection_and_book_settings(desktop, tmp_path, selection, pdf, latex):
    app = desktop
    notebook = tmp_path / "selected.ipynb"
    nbformat.write(nbformat.v4.new_notebook(), notebook)
    app.source.set(str(notebook))
    app._set_format(selection)
    request = app._request()
    assert (request.pdf, request.latex) == (pdf, latex)
    assert app.engine_picker.cget("state") == ("normal" if pdf else "disabled")
    letter = next(child for child in app.paper_picker.winfo_children()
                  if isinstance(child, ctk.CTkButton) and child.cget("text") == "Letter")
    letter.invoke()
    assert app._request().paper == "Letter", "Paper size also applies to standalone LaTeX"
    app.include_code.set(False)
    book = tmp_path / "book"
    book.mkdir()
    (book / "_config.yml").write_text("title: My book\n")
    (book / "_toc.yml").write_text("format: jb-book\nroot: intro\n")
    app.source.set(str(book))
    assert app.engine_picker.cget("state") == "disabled"
    paper_buttons = [child for child in app.paper_picker.winfo_children() if isinstance(child, ctk.CTkButton)]
    app.paper.set("A4")
    for button in paper_buttons:
        button.invoke()
    assert app.paper.get() == "A4", "Book paper controls must not override the project configuration"
    assert app.code_check.cget("state") == "disabled"
    assert app._request().include_code is True
    app.source.set(str(notebook))
    assert app.code_check.cget("state") == "normal"
    assert app._request().include_code is False
