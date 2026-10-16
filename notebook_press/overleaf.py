"""Portable source bundles and Overleaf's documented base64 ZIP form API."""

import base64
from html import escape
from pathlib import Path, PurePosixPath
import posixpath
import re
import zipfile

from .engine import ExportError


def _main_document(files):
    candidates = [name for name, contents in files.items() if name.endswith(".tex")
                  and re.search(rb"\\documentclass(?:\s*\[|\s*\{)", contents)]
    if not candidates:
        raise ExportError("No main LaTeX document was found for Overleaf.")
    return min(candidates, key=lambda name: (name.count("/"), name not in {"notebook.tex", "main.tex"}, name))


def _source_files(stage):
    root = stage / "latex"
    if root.is_dir():
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file() and not p.is_symlink()}
    root = stage / "book-exports"
    for archive in sorted(root.rglob("*.zip")):
        if not zipfile.is_zipfile(archive):
            continue
        with zipfile.ZipFile(archive) as bundle:
            files = {item.filename: bundle.read(item) for item in bundle.infolist() if not item.is_dir()}
        if any(name.endswith(".tex") for name in files):
            return files
    mains = [p for p in root.rglob("*.tex") if re.search(rb"\\documentclass(?:\s*\[|\s*\{)", p.read_bytes())]
    if mains:
        project = min(mains, key=lambda p: (len(p.parts), str(p))).parent
        return {p.relative_to(project).as_posix(): p.read_bytes() for p in project.rglob("*") if p.is_file() and not p.is_symlink()}
    raise ExportError("The book export does not contain a LaTeX project for Overleaf.")


def prepare_overleaf(stage: Path, title: str) -> Path:
    files = _source_files(stage)
    for name in files:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
            raise ExportError(f"Unsafe path in the LaTeX project: {name}")
    # Book exporters sometimes wrap the entire project in one directory. Make
    # that directory the upload root so TeX's relative figure paths still work.
    prefix = posixpath.commonpath([str(PurePosixPath(name).parent) for name in files]) if files else ""
    if prefix not in {"", "."}:
        files = {name[len(prefix) + 1:]: contents for name, contents in files.items()}
    main = _main_document(files)
    # Preserve PDF figures, bibliography data, class files, and styles. Exclude
    # build debris and the compiled document, which Overleaf recreates itself.
    debris = {".aux", ".log", ".out", ".toc", ".lof", ".lot", ".fls", ".fdb_latexmk", ".synctex.gz"}
    files = {name: data for name, data in files.items()
             if (name == ".latexmkrc" or not any(part.startswith(".") for part in PurePosixPath(name).parts))
             and not any(name.endswith(suffix) for suffix in debris)
             and name != str(PurePosixPath(main).with_suffix(".pdf"))}
    if "latexmkrc" not in files and ".latexmkrc" not in files:
        files["latexmkrc"] = b"$pdf_mode = 5; # XeLaTeX\n"
    files["OVERLEAF-README.txt"] = (
        f"Notebook Press: {title}\n\nMain document: {main}\nCompiler: XeLaTeX\n\n"
        "Upload overleaf.zip with New project > Upload project.\n"
        "All exported figure files are included with their relative paths.\n"
        "Overleaf compiles LaTeX; Python figures must be generated before upload.\n"
    ).encode("utf-8")
    archive = stage / "overleaf.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, contents in sorted(files.items()):
            bundle.writestr(name, contents)
    payload = base64.b64encode(archive.read_bytes()).decode("ascii")
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; form-action https://www.overleaf.com; base-uri 'none'">
<title>Open {escape(title)} in Overleaf</title>
<style>body{{margin:0;background:#edf2eb;color:#25332a;font:16px/1.6 system-ui,sans-serif}}main{{max-width:560px;margin:10vh auto;padding:40px;background:white;border-radius:18px}}h1{{font-size:30px;line-height:1.2}}p{{color:#657368}}button{{border:0;border-radius:9px;background:#52745b;color:white;padding:14px 22px;font:inherit;cursor:pointer}}a{{color:#42634b}}code{{overflow-wrap:anywhere}}small{{display:block;margin-top:24px;color:#657368}}@media(max-width:640px){{main{{margin:20px;padding:24px}}}}</style></head>
<body><main><p>NOTEBOOK PRESS / OVERLEAF</p><h1>{escape(title)}</h1>
<p>Your LaTeX source and figures are ready. The button sends this project directly to Overleaf in your browser. Sign in there if asked.</p>
<p>Main document: <code>{escape(main)}</code><br>Compiler: XeLaTeX · {len(files)} files</p>
<form method="post" action="https://www.overleaf.com/docs">
<input type="hidden" name="snip_uri" value="data:application/zip;base64,{payload}">
<input type="hidden" name="engine" value="xelatex">
<input type="hidden" name="main_document" value="{escape(main, quote=True)}">
<button type="submit">Upload project to Overleaf</button></form>
<p>Prefer to upload manually? <a href="overleaf.zip" download>Save project ZIP</a>, then choose New project → Upload project on Overleaf.</p>
<small>This includes the exported code when Include code is enabled. Notebook Press does not handle your Overleaf password.</small>
</main></body></html>'''
    (stage / "open-in-overleaf.html").write_text(page, encoding="utf-8")
    return archive
