Notebook Press exports Jupyter notebooks and books to PDF and editable LaTeX.

### New in 0.3.0

- **Open in Overleaf:** LaTeX exports include a portable project ZIP and a browser handoff through Overleaf's official import API. Figure files are included. Sign in in your browser; the app does not store Overleaf credentials.
- **Generate figures:** optionally run Python notebook cells before export using your own Python environment, including its plotting libraries and data files. Outputs are saved to a separate executed notebook; the original `.ipynb` is preserved.
- Choose the Python interpreter and per-cell timeout. Execution errors stop the export; cancellation stops the kernel as well as the exporter.
- Retains the sage workspace, offline math, saved-output export, and all three desktop platforms. Execution is optional and needs an external Python environment with `ipykernel` and the notebook's packages.

### Downloads

- **Windows x64:** Download `NotebookPress.exe` and double-click it. Python and the PDF browser are bundled. The first launch extracts the app and may take a moment.
- **macOS Apple Silicon:** Download `NotebookPress-macOS.zip`, extract it, and open `Notebook Press.app`.
- **Linux x64:** Download `NotebookPress-Linux.tar.gz`, extract it, and run `NotebookPress/NotebookPress`.

The Windows download is a single portable executable. No installer or Python setup is needed. These community builds are unsigned. Full Jupyter Book projects and LaTeX PDF typesetting need the optional publishing tools described in the [setup guide](https://github.com/dc73/notebook-press/blob/main/docs/usage.md).

Includes the Notebook Press logo, offline notebook math rendering, saved outputs and figures, code visibility controls, A4 / Letter sizing, progress logs, cancellation, and separate export folders.
