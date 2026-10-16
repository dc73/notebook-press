# Notebook Press

A native desktop app for **Windows, Linux, and macOS** that turns Jupyter notebooks and Jupyter Books into **PDF** and **LaTeX with supporting figures**. Built with Python and Tk, with real conversion through nbconvert, Chromium, and the official book engines.

## Open the app

Download the matching build from [GitHub Releases](https://github.com/dc73/notebook-press/releases/latest). On Windows, double-click the single `NotebookPress.exe`; no installer or Python setup is needed. On macOS, extract the ZIP and open `Notebook Press.app`. On Linux, extract the tarball and run `NotebookPress/NotebookPress`.

1. Choose an `.ipynb` file with **Notebook…**, or a complete project with **Book folder…**.
2. Select PDF, LaTeX, or both. For notebooks, choose browser or LaTeX PDF, paper size, and whether code is included.
3. Choose a destination and click **Export documents**.
4. Click **Open export folder** when the export is ready.

Release builds include Chromium, so notebook PDF export is ready without a separate browser install. For source installations and builds without Chromium, open **Setup & tools → Install PDF browser** once. Standard builds use a browser in the user cache; builds made with `--with-browser` include Chromium.

Each export creates a new, uniquely named folder. A notebook export contains:

```text
research-export-.../
  notebook.pdf
  latex/
    notebook.tex
    notebook_files/       # extracted output images and attachments
    linked-images/        # locally linked images, if present
  export.json             # chosen settings and generated file list
```

Only the selected formats are produced. Book output filenames follow the book configuration. LaTeX exports stay as editable folders, including image assets; use your editor or zip the folder to share it.

Notebook code is not executed during export. Run and save the notebook first to include up-to-date results. Book builds run on an isolated copy with notebook execution disabled. Existing exports and original source files are preserved. Failed jobs do not publish partial export folders. Cancellation terminates the worker and its child processes.

## Install from source on any platform

Use Python 3.11 or later (3.12 is used in CI). Run these commands inside this project directory:

```sh
python -m venv .venv
```

Activate the environment on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Or on Linux / macOS:

```sh
source .venv/bin/activate
```

Then install and launch:

```sh
python -m pip install -e .
python -m notebook_press --install-browser
python -m notebook_press
```

On Debian / Ubuntu, install Tk with `sudo apt install python3-tk python3-venv`. Chromium may also need system libraries: `python -m playwright install-deps chromium`. On macOS, use a Python distribution with Tk support; Python.org installers include it. Linux sessions need a graphical display.

After installation you can use the `notebook-press` command, the Windows launcher, or `sh start.sh` on Linux / macOS. The app remembers your last source, destination, and options in your operating system's user configuration directory.

## Supported inputs and required tools

| Input / export | Included or needed |
| --- | --- |
| Notebook → browser PDF | nbconvert + Playwright included; Chromium downloaded once or bundled |
| Notebook → LaTeX source | Pandoc included through `pypandoc-binary`; no TeX installation needed |
| Notebook → LaTeX PDF | XeLaTeX and a complete TeX package installation |
| Jupyter Book 1 → LaTeX | Optional Jupyter Book 1 command-line engine |
| Jupyter Book 1 → PDF | Jupyter Book 1, TeX, and `latexmk` |
| Jupyter Book 2 / MyST → LaTeX | Optional `mystmd` engine and a configured `tex` export |
| Jupyter Book 2 / MyST → PDF | MyST engine, a configured PDF export, and the template's TeX or Typst toolchain |

For LaTeX PDF typesetting, install **MiKTeX** on Windows, **MacTeX** on macOS, or **TeX Live** on Linux. Ensure the relevant commands are on PATH before launching the app. Notebook LaTeX can require additional utilities for certain output types, such as Inkscape for SVG-only figures. Interactive widgets and JavaScript visualizations should have saved static image outputs for reliable document export.

Browser PDFs use bundled MathJax to typeset equations locally. Locally linked images and embedded notebook figures work offline. Remote images and remote embeds still require access to their original URLs. Browser PDF styling follows the notebook's HTML representation; LaTeX styling follows nbconvert's LaTeX template.

### Jupyter Book 1

Select the folder containing `_config.yml` and `_toc.yml`. Install its engine in the active environment:

```sh
python -m pip install -e '.[book-v1]'
```

Or install it separately for use by a packaged app:

```sh
python -m pip install 'jupyter-book>=1,<2'
```

The app runs `jupyter-book build ... --builder latex` or `--builder pdflatex` on a temporary copy. It keeps the generated LaTeX project, supporting files, and selected PDFs. The original book's `_build` directory is not used. `examples/book-v1` is a two-chapter sample.

### Jupyter Book 2 / MyST

Select the folder containing `myst.yml` or `myst.yaml`. Install the engine:

```sh
python -m pip install -e '.[book-v2]'
# Or, separately for a packaged app:
python -m pip install mystmd
```

MyST also needs Node.js available to its CLI. Use a current Node.js LTS installation if the Python wrapper reports that Node is missing.

Define `project.exports` with `format: tex` and/or `format: pdf`, the desired template, and ordered `articles`. See `examples/book-v2/myst.yml`. The app redirects configured project output paths into its isolated workspace, preserving each output filename and supporting assets. LaTeX exports need a LaTeX template; a Typst template cannot produce `.tex` source. Template downloads require internet access.

The app runs `myst build --pdf`, `myst build --tex`, or both, honoring configured templates and article order. It preserves the complete `_build/exports` tree under `book-exports/`. Code is not re-executed. Book paper size, PDF engine, and code visibility are controlled by the book configuration, rather than notebook options.

If a packaged app cannot find a book engine on PATH, put the full `jupyter-book` or `myst` executable path in **Setup & tools → Book engine**. This field is a single executable path, not a shell command.

## Command line

```sh
python -m notebook_press export research.ipynb -o exports --format both
python -m notebook_press export research.ipynb -o exports --format pdf --hide-code --paper Letter
python -m notebook_press export research.ipynb -o exports --format pdf --pdf-engine latex
python -m notebook_press export examples/book-v1 -o exports --format latex
python -m notebook_press export examples/book-v2 -o exports --format latex
python -m notebook_press doctor
```

## Build Windows, macOS, and Linux apps

Build on the target operating system. PyInstaller does not cross-compile desktop applications.

```sh
python -m pip install -e '.[dev]'
python scripts/build.py
# Windows single executable, including Chromium:
python scripts/build.py --with-browser --onefile
# Include Chromium for PDF export without a first-run browser download:
python scripts/build.py --with-browser
python scripts/smoke_packaged.py
```

The Windows single-file build is `dist/NotebookPress.exe`. Folder-build outputs are `dist/NotebookPress/NotebookPress.exe` on Windows, `dist/Notebook Press.app` on macOS, and `dist/NotebookPress/NotebookPress` on Linux. The optional book engines and full TeX / Typst toolchains are separate installations. Builds are unsigned; signing and notarization require your own certificates.

The included GitHub Actions workflow tests and packages all three operating systems when run manually, on pull requests, or on a `v*` tag. It bundles Chromium and smoke-tests PDF and LaTeX conversion from each packaged application, then publishes a Windows executable, macOS app ZIP, and Linux tarball to the tagged release. Use this project directory as the repository root for that workflow.

## Validation

```sh
python -m pip install -e '.[dev,book-v1,book-v2]'
python -m playwright install chromium
python -m pytest -q
# Headless Linux:
xvfb-run -a python -m pytest -q
```

The tests cover actual LaTeX and Chromium PDF exports, portable figures and attachments, saved-output preservation, code visibility, paper size, unique destinations, failure cleanup, source preservation, worker error reporting, the desktop export lifecycle, cancellation cleanup, and real Jupyter Book 1 and MyST builds. The packaged smoke test separately checks the executable's PDF and LaTeX outputs.

See [GitHub Actions](https://github.com/dc73/notebook-press/actions) for the current Windows, macOS, and Linux build results. LaTeX PDF compilation requires an external TeX installation and is not covered by the local browser-PDF checks.

## Upstream documentation

- [nbconvert export formats and requirements](https://nbconvert.readthedocs.io/en/latest/usage.html)
- [Jupyter Book 1 PDF and LaTeX builds](https://jupyterbook.org/v1/advanced/pdf.html)
- [MyST export configuration](https://mystmd.org/guide/documents-exports)
- [Playwright browser installation](https://playwright.dev/python/docs/browsers)

MathJax 3.2.2 is vendored under its included Apache 2.0 license in `notebook_press/assets/MathJax-LICENSE.txt`. Other dependencies retain their own licenses.
