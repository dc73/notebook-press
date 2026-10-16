"""Run an unsaved plot, preserve its source, and submit the actual ZIP form."""

import base64
import hashlib
import sys
from urllib.parse import parse_qs
import zipfile

import nbformat
from pypdf import PdfReader
import pytest

from notebook_press.engine import ExportError, ExportRequest, export
from notebook_press.overleaf import prepare_overleaf


@pytest.fixture(scope="module")
def generated_export(tmp_path_factory):
    work = tmp_path_factory.mktemp("generated-figures")
    (work / "data.txt").write_text("2,5,3,8")
    source = work / "unrun.ipynb"
    nbformat.write(nbformat.v4.new_notebook(cells=[
        nbformat.v4.new_markdown_cell("# Figures from an unrun notebook\n\nA formula: $E=mc^2$."),
        nbformat.v4.new_code_cell("from pathlib import Path\nvalues = [int(x) for x in Path('data.txt').read_text().split(',')]\nprint('Computed total:', sum(values))"),
        nbformat.v4.new_code_cell("import matplotlib.pyplot as plt\nplt.plot(values)\nplt.title('Generated during export')\nplt.show()"),
    ]), source)
    original = source.read_bytes()
    result = export(ExportRequest(str(source), str(work / "exports"), execute=True,
                                 python_executable=sys.executable, include_code=False), lambda _: None)
    assert source.read_bytes() == original
    return result


def test_unrun_figures_reach_pdf_latex_and_overleaf(generated_export):
    result = generated_export
    notebook = nbformat.read(result / "executed.ipynb", as_version=4)
    assert all(cell.execution_count for cell in notebook.cells if cell.cell_type == "code")
    images = [output.data["image/png"] for cell in notebook.cells for output in cell.get("outputs", [])
              if "image/png" in output.get("data", {})]
    assert images
    tex = (result / "latex" / "notebook.tex").read_text(encoding="utf-8")
    assert "Computed total: 18" in tex
    assert "import matplotlib" not in tex
    figures = [path.relative_to(result / "latex").as_posix() for path in (result / "latex").rglob("*.png")]
    assert figures
    with zipfile.ZipFile(result / "overleaf.zip") as bundle:
        for name in figures:
            assert name in tex
            assert bundle.read(name) == (result / "latex" / name).read_bytes()
        assert base64.b64decode(images[0]) in [bundle.read(name) for name in figures]
        assert "notebook.tex" in bundle.namelist()
        assert not any(name.endswith(".ipynb") for name in bundle.namelist())
    pdf = PdfReader(result / "notebook.pdf")
    assert sum(len(page.images) for page in pdf.pages) >= 1
    assert "Computed total: 18" in "\n".join(page.extract_text() for page in pdf.pages)


def test_browser_posts_project_to_official_overleaf_api(generated_export):
    from playwright.sync_api import sync_playwright

    captured = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()

        def capture(route):
            captured.append(parse_qs(route.request.post_data))
            route.fulfill(status=200, content_type="text/html", body="Project received by test")

        page.route("https://www.overleaf.com/docs", capture)
        page.goto((generated_export / "open-in-overleaf.html").as_uri())
        page.get_by_role("button", name="Upload project to Overleaf").click()
        assert captured
        assert captured[0]["engine"] == ["xelatex"]
        assert captured[0]["main_document"] == ["notebook.tex"]
        uri = captured[0]["snip_uri"][0]
        assert uri.startswith("data:application/zip;base64,")
        assert base64.b64decode(uri.split(",", 1)[1]) == (generated_export / "overleaf.zip").read_bytes()
        browser.close()


@pytest.mark.parametrize("code,timeout,match", [
    ("raise ValueError('Deliberate cell error')", 30, "Deliberate cell error"),
    ("import time; time.sleep(10)", 1, "timed out"),
])
def test_execution_errors_and_timeouts_publish_no_partial_export(tmp_path, code, timeout, match):
    source = tmp_path / "fails.ipynb"
    nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(code)]), source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    destination = tmp_path / "exports"
    with pytest.raises(ExportError, match=match):
        export(ExportRequest(str(source), str(destination), pdf=False, execute=True,
                             python_executable=sys.executable, execution_timeout=timeout), lambda _: None)
    assert list(destination.iterdir()) == []
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_overleaf_keeps_pdf_figures_and_removes_compiled_document(tmp_path):
    latex = tmp_path / "latex"
    latex.mkdir()
    (latex / "main.tex").write_text(r"\documentclass{article}\begin{document}\includegraphics{plot.pdf}\end{document}")
    (latex / "plot.pdf").write_bytes(b"PDF figure")
    (latex / "main.pdf").write_bytes(b"Compiled document")
    (latex / "main.aux").write_text("Build debris")
    (latex / ".latexmkrc").write_text("# Custom settings")
    prepare_overleaf(tmp_path, '<script>alert("escaped")</script>')
    with zipfile.ZipFile(tmp_path / "overleaf.zip") as bundle:
        assert "plot.pdf" in bundle.namelist()
        assert "main.pdf" not in bundle.namelist()
        assert "main.aux" not in bundle.namelist()
        assert bundle.read(".latexmkrc") == b"# Custom settings"
    assert '<script>alert("escaped")</script>' not in (tmp_path / "open-in-overleaf.html").read_text()


def test_overleaf_flattens_a_book_archive_project_directory(tmp_path):
    exports = tmp_path / "book-exports"
    exports.mkdir()
    with zipfile.ZipFile(exports / "book.zip", "w") as bundle:
        bundle.writestr("project/main.tex", r"\documentclass{article}\includegraphics{figures/plot.pdf}")
        bundle.writestr("project/figures/plot.pdf", b"PDF figure")
    prepare_overleaf(tmp_path, "Book")
    with zipfile.ZipFile(tmp_path / "overleaf.zip") as bundle:
        assert "main.tex" in bundle.namelist()
        assert bundle.read("figures/plot.pdf") == b"PDF figure"
