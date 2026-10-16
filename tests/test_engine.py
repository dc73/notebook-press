"""Real conversion tests, including images, math, and no code execution."""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import nbformat
from pypdf import PdfReader
import pytest

from notebook_press.engine import ExportError, ExportRequest, export, find_tool, source_kind

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")


@pytest.fixture
def notebook(tmp_path):
    source = tmp_path / "source with spaces"
    source.mkdir()
    (source / "my figure.png").write_bytes(PNG)
    nb = nbformat.v4.new_notebook(cells=[
        nbformat.v4.new_markdown_cell("# Export verification\n\nEquation: $E = mc^2$.\n\n![Figure](<my figure.png>)\n\n![Referenced][figure]\n\n[figure]: <my figure.png>"),
        nbformat.v4.new_markdown_cell("![Attached](attachment:pixel.png)", attachments={"pixel.png": {"image/png": base64.b64encode(PNG).decode()}}),
        nbformat.v4.new_code_cell("raise RuntimeError('THIS CODE MUST NEVER RUN')", execution_count=1,
                                 outputs=[nbformat.v4.new_output("stream", text="Saved result: 42\n", name="stdout"),
                                          nbformat.v4.new_output("display_data", data={"image/png": base64.b64encode(PNG).decode(), "text/plain": "A figure"})]),
    ])
    path = source / "research.ipynb"
    nbformat.write(nb, path)
    return path


def test_latex_is_portable_and_does_not_execute_or_modify_source(notebook, tmp_path):
    before = hashlib.sha256(notebook.read_bytes()).hexdigest()
    result = export(ExportRequest(str(notebook), str(tmp_path / "out"), pdf=False), lambda _: None)
    tex = (result / "latex" / "notebook.tex").read_text(encoding="utf-8")
    assert "Saved result: 42" in tex
    assert "mc" in tex
    assert "a4paper" in tex
    assert "linked-images/1.png" in tex
    assert (result / "latex" / "linked-images" / "1.png").is_file()
    assert list((result / "latex").rglob("*.png"))
    assert "attachment:pixel.png" not in tex
    assert hashlib.sha256(notebook.read_bytes()).hexdigest() == before
    assert not list((tmp_path / "out").glob(".notebook-press-*"))
    assert json.loads((result / "export.json").read_text())["source_kind"] == "notebook"
    # Every generated includegraphics reference resolves inside the bundle.
    import re
    for image in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', tex):
        assert (result / "latex" / image).is_file(), image


def test_hidden_code_keeps_saved_outputs_and_letter_paper(notebook, tmp_path):
    result = export(ExportRequest(str(notebook), str(tmp_path / "out"), pdf=False, include_code=False, paper="Letter"), lambda _: None)
    tex = (result / "latex" / "notebook.tex").read_text(encoding="utf-8")
    assert "THIS CODE MUST NEVER RUN" not in tex
    assert "Saved result: 42" in tex
    assert "letterpaper" in tex


def test_pdf_and_latex_with_real_chromium(notebook, tmp_path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            pytest.skip("Install Chromium to run the browser integration test")
    result = export(ExportRequest(str(notebook), str(tmp_path / "out"), include_code=False), lambda _: None)
    pdf = PdfReader(result / "notebook.pdf")
    text = "\n".join(page.extract_text() for page in pdf.pages)
    assert "Export verification" in text
    assert "Saved result: 42" in text
    assert "THIS CODE MUST NEVER RUN" not in text
    assert len(pdf.pages) >= 1
    assert sum(len(page.images) for page in pdf.pages) >= 1
    assert float(pdf.pages[0].mediabox.width) == pytest.approx(595.28, abs=1)  # Chromium rounds to CSS pixels
    assert (result / "latex" / "notebook.tex").is_file()
    assert not list(result.glob("*.html"))


def test_export_never_overwrites_previous_result(notebook, tmp_path):
    request = ExportRequest(str(notebook), str(tmp_path / "out"), pdf=False)
    first = export(request, lambda _: None)
    snapshot = (first / "latex" / "notebook.tex").read_bytes()
    second = export(request, lambda _: None)
    assert first != second
    assert (first / "latex" / "notebook.tex").read_bytes() == snapshot


def test_failure_does_not_publish_partial_files(notebook, tmp_path):
    (notebook.parent / "my figure.png").unlink()
    out = tmp_path / "out"
    with pytest.raises(ExportError, match="linked image"):
        export(ExportRequest(str(notebook), str(out), pdf=False), lambda _: None)
    assert list(out.iterdir()) == []


def test_input_validation(tmp_path):
    with pytest.raises(ExportError):
        ExportRequest(str(tmp_path / "missing"), str(tmp_path)).validate()
    bad = tmp_path / "bad.ipynb"
    bad.write_text("not a notebook")
    with pytest.raises(ExportError, match="Select PDF"):
        ExportRequest(str(bad), str(tmp_path), pdf=False, latex=False).validate()
    with pytest.raises(ExportError, match="Could not read"):
        export(ExportRequest(str(bad), str(tmp_path / "out"), pdf=False), lambda _: None)


def test_worker_reports_errors_as_events(tmp_path):
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"source": str(tmp_path / "missing.ipynb"), "destination": str(tmp_path / "out")}))
    events = tmp_path / "events.jsonl"
    process = subprocess.run([sys.executable, "-m", "notebook_press", "--worker", str(request), "--events", str(events)], capture_output=True)
    assert process.returncode == 1
    rows = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["event"] == "error"
    assert "existing notebook" in rows[-1]["message"]


def test_real_jupyter_book_v1_latex_in_source_directory(tmp_path):
    if not importlib.util.find_spec("jupyter_book"):
        pytest.skip("Optional Jupyter Book 1 engine is not installed")
    root = Path(__file__).parent.parent
    source = tmp_path / "book"
    shutil.copytree(root / "examples" / "book-v1", source)
    danger = nbformat.v4.new_notebook(metadata={"mystnb": {"execution_mode": "force"}}, cells=[
        nbformat.v4.new_code_cell("raise RuntimeError('Execution must remain disabled')")
    ])
    nbformat.write(danger, source / "saved.ipynb")
    with (source / "_toc.yml").open("a", encoding="utf-8") as stream:
        stream.write("  - file: saved\n")
    before = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    # Destination equals source: staging must be excluded from recursive copying.
    result = export(ExportRequest(str(source), str(source), pdf=False), lambda _: None)
    assert list((result / "latex").glob("*.tex"))
    for name, contents in before.items():
        assert (source / name).read_bytes() == contents
    assert not (source / "_build").exists()


def test_real_myst_latex_export(tmp_path):
    if not find_tool("myst"):
        pytest.skip("Optional MyST engine is not installed")
    source = tmp_path / "book-v2"
    shutil.copytree(Path(__file__).parent.parent / "examples" / "book-v2", source)
    config_path = source / "myst.yml"
    original = config_path.read_text(encoding="utf-8").replace("_build/exports/research-book-latex", "custom-output/latex")
    config_path.unlink()
    (source / "myst.yaml").write_text(original, encoding="utf-8")
    result = export(ExportRequest(str(source), str(tmp_path / "out"), pdf=False), lambda _: None)
    tex = list((result / "book-exports").rglob("*.tex"))
    assert tex
    text = "\n".join(path.read_text(encoding="utf-8") for path in tex)
    assert "Experiment" in text
    assert "13.35" in text
    assert not (source / "_build").exists()
    assert not (source / "custom-output").exists()
    assert (source / "myst.yaml").read_text(encoding="utf-8") == original


def test_book_detection():
    root = Path(__file__).parent.parent / "examples"
    assert source_kind(root / "book-v1") == "book-v1"
    assert source_kind(root / "book-v2") == "book-v2"
