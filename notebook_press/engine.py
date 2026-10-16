"""Conversion engine shared by the desktop app and command line.

Every export is built in a fresh staging directory, then published to a new
directory. Notebook cells are never re-executed by this application.
"""

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import unquote, urlparse


class ExportError(Exception):
    """An actionable export failure."""


@dataclass
class ExportRequest:
    source: str
    destination: str
    pdf: bool = True
    latex: bool = True
    pdf_engine: str = "browser"
    include_code: bool = True
    paper: str = "A4"
    book_command: str = ""

    def validate(self) -> tuple[Path, Path, str]:
        source = Path(self.source).expanduser().resolve()
        if not source.exists():
            raise ExportError("Choose an existing notebook or Jupyter Book folder.")
        kind = source_kind(source)
        if not self.pdf and not self.latex:
            raise ExportError("Select PDF, LaTeX, or both formats.")
        if self.pdf_engine not in {"browser", "latex"}:
            raise ExportError("The PDF engine must be browser or latex.")
        if self.paper not in {"A4", "Letter"}:
            raise ExportError("Paper size must be A4 or Letter.")
        if not self.destination.strip():
            raise ExportError("Choose an export destination.")
        destination = Path(self.destination).expanduser().resolve()
        if destination.exists() and not destination.is_dir():
            raise ExportError("The export destination must be a folder.")
        if kind != "notebook" and not self.include_code:
            raise ExportError("For books, control code visibility in the book configuration.")
        return source, destination, kind


def source_kind(path: Path) -> str:
    if path.is_file() and path.suffix.lower() == ".ipynb":
        return "notebook"
    if path.is_dir():
        if (path / "myst.yml").is_file() or (path / "myst.yaml").is_file():
            return "book-v2"
        if (path / "_config.yml").is_file() and (path / "_toc.yml").is_file():
            return "book-v1"
    raise ExportError("Choose an .ipynb file, or a book folder containing myst.yml or _config.yml + _toc.yml.")


def find_tool(name: str) -> str | None:
    # A packaged app can use engines installed by pip alongside an external Python.
    # Source installs also discover entry points beside their own interpreter.
    scripts = Path(sys.executable).parent
    for suffix in (".exe", ".cmd", "") if os.name == "nt" else ("",):
        candidate = scripts / (name + suffix)
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def external_environment() -> dict[str, str]:
    """Use system library paths for independently shipped publishing tools."""
    environment = os.environ.copy()
    if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
        original = environment.get("LD_LIBRARY_PATH_ORIG")
        if original is None:
            environment.pop("LD_LIBRARY_PATH", None)
        else:
            environment["LD_LIBRARY_PATH"] = original
    return environment


def configure_pandoc() -> str:
    import pypandoc

    try:
        path = pypandoc.get_pandoc_path()
    except OSError as error:
        raise ExportError("Pandoc is missing. Install pypandoc-binary or add Pandoc to PATH.") from error
    os.environ["PYPANDOC_PANDOC"] = path
    os.environ["PATH"] = str(Path(path).parent) + os.pathsep + os.environ.get("PATH", "")
    return path


def dependency_report() -> list[tuple[str, bool, str]]:
    report = []
    for module, label in (("nbconvert", "Notebook conversion"), ("playwright", "Browser PDF")):
        available = importlib.util.find_spec(module) is not None
        report.append((label, available, "Installed" if available else f"Install {module}"))
    try:
        report.append(("Pandoc / LaTeX source", True, configure_pandoc()))
    except (ImportError, ExportError) as error:
        report.append(("Pandoc / LaTeX source", False, str(error)))
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(timeout=15000, env=external_environment())
            browser.close()
        report.append(("Chromium", True, "Headless PDF browser is ready"))
    except Exception as error:
        report.append(("Chromium", False, "Use Install PDF browser below. " + str(error).splitlines()[0]))
    for tool, label in (("xelatex", "XeLaTeX (optional)"), ("latexmk", "latexmk (book PDF)"),
                        ("jupyter-book", "Jupyter Book 1 (optional)"), ("myst", "MyST / Book 2 (optional)")):
        path = find_tool(tool)
        report.append((label, bool(path), path or "Not found on PATH"))
    return report


def _command(command: list[str], cwd: Path, log: Callable[[str], None]) -> None:
    log("Running: " + subprocess.list2cmdline(command))
    env = external_environment()
    env.update({"PYTHONIOENCODING": "utf-8", "NO_COLOR": "1", "FORCE_COLOR": "0"})
    with subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0) as process:
        assert process.stdout is not None
        tail = []
        for line in process.stdout:
            line = line.rstrip()
            log(line)
            tail = (tail + [line])[-15:]
        if process.wait():
            raise ExportError("The book engine failed.\n" + "\n".join(tail))


def _prepare_latex_images(notebook, source: Path, target: Path) -> None:
    """Copy local Markdown/HTML images and use portable LaTeX asset paths."""
    images = target / "linked-images"
    copied: dict[Path, str] = {}

    def relocate(value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme or value.startswith("#"):
            return value
        original = (source.parent / unquote(parsed.path)).resolve()
        if not original.is_file():
            raise ExportError(f"A linked image could not be found: {value}")
        if original not in copied:
            images.mkdir(exist_ok=True)
            name = f"{len(copied) + 1}{original.suffix.lower()}"
            shutil.copy2(original, images / name)
            copied[original] = f"linked-images/{name}"
        return copied[original]

    # Handles inline images, reference definitions, and HTML images. Attachments
    # are handled by nbconvert below and are not filesystem paths.
    inline = re.compile(r'(!\[[^\]]*\]\(\s*)(<[^>]+>|[^\s)]+)([^)]*\))')
    reference = re.compile(r'(^\s*\[[^\]]+\]:\s*)(<[^>]+>|\S+)', re.MULTILINE)
    html = re.compile(r'(<img\b[^>]*\bsrc=["\'])([^"\']+)(["\'])', re.IGNORECASE)
    for index, cell in enumerate(notebook.cells):
        if cell.cell_type != "markdown":
            continue
        if cell.get("attachments"):
            renamed = {}
            for number, (name, data) in enumerate(cell.attachments.items()):
                new_name = f"cell-{index}-attachment-{number}{Path(name).suffix}"
                renamed[new_name] = data
                cell.source = cell.source.replace("attachment:" + name, "attachment:" + new_name)
            cell.attachments = renamed
        used_refs = {ref.casefold() for ref in re.findall(r'!\[[^\]]*\]\[([^\]]+)\]', cell.source)}
        used_refs.update(ref.casefold() for ref in re.findall(r'!\[([^\]]+)\](?![\[(])', cell.source))

        def rewrite(match):
            value = match[2].strip("<>")
            return match[1] + relocate(value) + (match[3] if match.lastindex == 3 else "")

        cell.source = inline.sub(rewrite, cell.source)
        cell.source = html.sub(rewrite, cell.source)

        def rewrite_reference(match):
            key = re.search(r'\[([^\]]+)\]', match[1])[1].casefold()
            return rewrite(match) if key in used_refs else match[0]

        cell.source = reference.sub(rewrite_reference, cell.source)


async def _browser_pdf(html: str, target: Path, paper: str, base: Path) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(args=["--allow-file-access-from-files"], env=external_environment())
        except Exception as error:
            raise ExportError("PDF browser could not start. Open Setup and install the PDF browser.\n" + str(error)) from error
        try:
            page = await browser.new_page()
            # Local file navigation allows relative images without a local server.
            document = target.with_suffix(".html")
            from html import escape

            html = html.replace("<head>", '<head><base href="' + escape(base.as_uri() + "/", quote=True) + '">', 1)
            document.write_text(html, encoding="utf-8")
            await page.goto(document.as_uri(), wait_until="load", timeout=60000)
            # Ship MathJax so equations don't depend on a CDN or an internet link.
            await page.evaluate("""() => { window.MathJax = {
                tex: {inlineMath: [['$', '$'], ['\\\\(', '\\\\)']]},
                svg: {fontCache: 'local'}, startup: {typeset: false}
            }; }""")
            await page.add_script_tag(path=str(Path(__file__).parent / "assets" / "tex-svg-full.js"))
            await page.evaluate("async () => { await MathJax.startup.promise; await MathJax.typesetPromise(); await document.fonts.ready; }")
            broken = await page.evaluate("""async () => {
                await Promise.all([...document.images].map(i => i.decode().catch(() => {})));
                return [...document.images].filter(i => !i.naturalWidth).map(i => i.src);
            }""")
            if broken:
                raise ExportError("PDF contains missing images. Check these image paths:\n" + "\n".join(broken[:8]))
            await page.emulate_media(media="print")
            await page.pdf(path=str(target), format=paper, print_background=True,
                           margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})
            document.unlink()
        finally:
            await browser.close()


def _notebook(request: ExportRequest, source: Path, stage: Path, log: Callable[[str], None]) -> None:
    import nbformat
    from nbconvert import HTMLExporter, LatexExporter
    from nbconvert.writers import FilesWriter
    from traitlets.config import Config

    log("Reading saved notebook cells and outputs…")
    try:
        notebook = nbformat.read(source, as_version=4)
        nbformat.validate(notebook)
    except Exception as error:
        raise ExportError(f"Could not read this notebook: {error}") from error
    config = Config()
    config.TemplateExporter.exclude_input = not request.include_code
    config.TemplateExporter.exclude_input_prompt = True
    config.TemplateExporter.exclude_output_prompt = True
    resources = {"metadata": {"path": str(source.parent), "name": source.stem},
                 "unique_key": "notebook", "output_files_dir": "notebook_files"}
    if request.latex or (request.pdf and request.pdf_engine == "latex"):
        pandoc = configure_pandoc()
        latex_dir = stage / "latex"
        latex_dir.mkdir()
        tex_notebook = copy.deepcopy(notebook)
        _prepare_latex_images(tex_notebook, source, latex_dir)
        exporter = LatexExporter(config=config)

        def convert_pandoc(text, from_format, to_format, extra_args=None):
            # Explicit stdin/stdout/stderr handles are required by Pandoc in
            # windowed Windows executables, which have no inherited console.
            process = subprocess.run([pandoc, "-f", from_format, "-t", to_format, *(extra_args or [])],
                                     input=text, capture_output=True, encoding="utf-8", errors="replace",
                                     env=external_environment(),
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if process.returncode or not process.stdout.strip():
                raise ExportError("Pandoc could not convert this notebook:\n" + (process.stderr or f"exit {process.returncode}"))
            return process.stdout.rstrip("\n")

        exporter.register_filter("convert_pandoc", convert_pandoc)
        log("Exporting LaTeX and supporting figures…")
        body, tex_resources = exporter.from_notebook_node(tex_notebook, resources=copy.deepcopy(resources))
        paper = "a4paper" if request.paper == "A4" else "letterpaper"
        body = re.sub(r'(\\documentclass\[)([^\]]*)(\])', lambda m: m[1] + m[2] + "," + paper + m[3], body, count=1)
        FilesWriter(build_directory=str(latex_dir)).write(body, tex_resources, notebook_name="notebook")
        if request.pdf and request.pdf_engine == "latex":
            if not find_tool("xelatex"):
                raise ExportError("XeLaTeX is missing. Install MiKTeX / MacTeX / TeX Live, or choose Browser PDF.")
            log("Typesetting PDF with XeLaTeX…")
            # Compile the exported bundle so the PDF and .tex use identical assets.
            for _ in range(3):
                _command([find_tool("xelatex"), "-interaction=nonstopmode", "-halt-on-error", "notebook.tex"], latex_dir, log)
            shutil.copy2(latex_dir / "notebook.pdf", stage / "notebook.pdf")
            for suffix in (".aux", ".log", ".out", ".toc", ".pdf"):
                (latex_dir / ("notebook" + suffix)).unlink(missing_ok=True)
        if not request.latex:
            shutil.rmtree(latex_dir)
    if request.pdf and request.pdf_engine == "browser":
        log("Rendering PDF with Chromium…")
        html_exporter = HTMLExporter(config=config, template_name="lab", embed_images=True)
        # MathJax is loaded locally after navigation by the browser PDF renderer.
        html_exporter.mathjax_url = ""
        html, _ = html_exporter.from_notebook_node(notebook, resources=copy.deepcopy(resources))
        html = html.replace("</head>", "<style>@media print { pre { white-space: pre-wrap !important; overflow-wrap: anywhere; } .jp-OutputArea-output { overflow: visible !important; } }</style></head>")
        asyncio.run(_browser_pdf(html, stage / "notebook.pdf", request.paper, source.parent))


def _book(request: ExportRequest, source: Path, stage: Path, work: Path, kind: str, log: Callable[[str], None]) -> None:
    import yaml

    tool_name = "jupyter-book" if kind == "book-v1" else "myst"
    tool = find_tool(request.book_command or tool_name)
    if not tool:
        package = '"jupyter-book>=1,<2"' if kind == "book-v1" else "mystmd"
        raise ExportError(f"{tool_name} was not found. Install with: python -m pip install {package}\n"
                          "You can also enter its full executable path in Book engine.")
    project = work / "project"
    destination = Path(request.destination).expanduser().resolve()

    def ignore(directory, names):
        ignored = {".git", ".venv", "venv", "node_modules", "_build", "__pycache__", ".ipynb_checkpoints"}
        return [name for name in names if name in ignored or
                (Path(directory) / name).resolve() in {destination, work.resolve()} or (Path(directory) / name).is_symlink()]

    log("Copying book to an isolated workspace…")
    shutil.copytree(source, project, ignore=ignore)
    if kind == "book-v1":
        config_path = project / "_config.yml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        config.setdefault("execute", {})["execute_notebooks"] = "off"
        sphinx = config.setdefault("sphinx", {}).setdefault("config", {})
        sphinx["nb_execution_mode"] = "off"
        metadata_key = sphinx.get("nb_metadata_key", "mystnb")
        # Per-page configuration can override the global execution setting.
        # Override it in the isolated copy, retaining all rendering settings.
        import nbformat
        for page in project.rglob("*.ipynb"):
            notebook = nbformat.read(page, as_version=4)
            notebook.metadata.setdefault(metadata_key, {})["execution_mode"] = "off"
            nbformat.write(notebook, page)
        for page in project.rglob("*.md"):
            content = page.read_text(encoding="utf-8")
            frontmatter = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)', content, re.DOTALL)
            if frontmatter:
                metadata = yaml.safe_load(frontmatter[1])
                if isinstance(metadata, dict) and isinstance(metadata.get(metadata_key), dict):
                    metadata[metadata_key]["execution_mode"] = "off"
                    page.write_text("---\n" + yaml.safe_dump(metadata, sort_keys=False) + "---\n" + content[frontmatter.end():], encoding="utf-8")
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        builder = "pdflatex" if request.pdf else "latex"
        _command([tool, "build", str(project), "--builder", builder], project, log)
        built = project / "_build" / "latex"
        if request.pdf:
            pdfs = list(built.glob("*.pdf"))
            if not pdfs:
                raise ExportError("Jupyter Book completed without producing a PDF. Check LaTeX setup and the build log.")
            for pdf in pdfs:
                shutil.copy2(pdf, stage / pdf.name)
        if request.latex:
            if not list(built.glob("*.tex")):
                raise ExportError("The book engine did not produce LaTeX source.")
            shutil.copytree(built, stage / "latex")
    else:
        config_path = project / "myst.yml"
        if not config_path.exists():
            (project / "myst.yaml").rename(config_path)
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        # Redirect configured project outputs into the staged export tree. A
        # book may normally export to ./exports or even an absolute location.
        # Preserve filenames and keep each export's supporting assets together.
        entries = (config.get("project") or {}).get("exports", [])
        for index, entry in enumerate(entries):
            if isinstance(entry, dict) and entry.get("output"):
                name = str(entry["output"]).replace("\\", "/").rstrip("/").split("/")[-1]
                if name in {"", ".", ".."}:
                    name = "document"
                entry["output"] = f"_build/exports/export-{index + 1}/{name}"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        command = [tool, "build"]
        if request.pdf:
            command.append("--pdf")
        if request.latex:
            command.append("--tex")
        # Honor the project's export articles, ordering, and templates. MyST does
        # not execute notebook cells unless --execute is requested.
        _command(command, project, log)
        exports = project / "_build" / "exports"
        if not exports.is_dir():
            raise ExportError("No document exports were created. Define project.exports in myst.yml; see the bundled example.")
        pdfs = list(exports.rglob("*.pdf"))
        if request.pdf and not pdfs:
            raise ExportError("No PDF was produced. Add a PDF export to myst.yml and install its LaTeX or Typst engine.")
        latex_archives = []
        for archive in exports.rglob("*.zip"):
            if zipfile.is_zipfile(archive):
                with zipfile.ZipFile(archive) as bundle:
                    if any(name.lower().endswith(".tex") for name in bundle.namelist()):
                        latex_archives.append(archive)
        if request.latex and not (list(exports.rglob("*.tex")) or latex_archives):
            raise ExportError("No LaTeX source was produced. Add a tex export to myst.yml using a LaTeX template.")
        # Keep the complete export tree to preserve all relative asset paths.
        shutil.copytree(exports, stage / "book-exports")
    log("Book export complete. Paper size and PDF engine follow the book's configuration.")


def export(request: ExportRequest, log: Callable[[str], None] = print,
           on_workspace: Callable[[Path], None] | None = None) -> Path:
    source, destination, kind = request.validate()
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".notebook-press-", dir=destination) as temporary:
        work = Path(temporary)
        if on_workspace:
            on_workspace(work)
        stage = work / "result"
        stage.mkdir()
        if kind == "notebook":
            _notebook(request, source, stage, log)
        else:
            _book(request, source, stage, work, kind, log)
        files = sorted(str(path.relative_to(stage)) for path in stage.rglob("*") if path.is_file())
        (stage / "export.json").write_text(json.dumps({
            "created_utc": datetime.now(timezone.utc).isoformat(), "source_kind": kind,
            "request": asdict(request), "files": files,
        }, indent=2), encoding="utf-8")
        stem = re.sub(r'[^\w. -]', "_", source.stem if source.is_file() else source.name)[:70] or "book"
        result = destination / f"{stem}-export-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        stage.rename(result)
    log(f"Saved {len(files)} files to {result}")
    return result
