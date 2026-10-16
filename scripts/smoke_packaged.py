"""Test a frozen GUI executable through its file-based worker interface."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import nbformat
from pypdf import PdfReader


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument('--executable', type=Path)
    args = parser.parse_args()
    if args.executable:
        executable = args.executable.resolve()
    elif sys.platform == 'win32' and (root / 'dist' / 'NotebookPress.exe').is_file():
        executable = root / 'dist' / 'NotebookPress.exe'
    elif sys.platform == 'darwin':
        executable = root / 'dist' / 'Notebook Press.app' / 'Contents' / 'MacOS' / 'NotebookPress'
    else:
        executable = root / 'dist' / 'NotebookPress' / ('NotebookPress.exe' if sys.platform == 'win32' else 'NotebookPress')
    with tempfile.TemporaryDirectory(prefix='notebook-press-smoke-') as temporary:
        work = Path(temporary)
        source = work / 'sample.ipynb'
        nbformat.write(nbformat.v4.new_notebook(cells=[
            nbformat.v4.new_markdown_cell('# Packaged export\n\nA formula: $E=mc^2$.'),
            nbformat.v4.new_code_cell('raise Exception("Must not run")', outputs=[nbformat.v4.new_output('stream', name='stdout', text='Saved output: 42')])
        ]), source)
        request = work / 'request.json'
        request.write_text(json.dumps({'source': str(source), 'destination': str(work / 'exports')}))
        events = work / 'events.jsonl'
        process = subprocess.run([str(executable), '--worker', str(request), '--events', str(events)], timeout=180)
        assert events.exists(), f'Packaged worker did not start (exit {process.returncode})'
        rows = [json.loads(line) for line in events.read_text(encoding='utf-8').splitlines()]
        assert process.returncode == 0 and rows[-1]['event'] == 'done', rows
        result = Path(rows[-1]['path'])
        assert (result / 'latex' / 'notebook.tex').is_file()
        pdf = PdfReader(result / 'notebook.pdf')
        assert 'Packaged export' in pdf.pages[0].extract_text()
        assert 'Saved output: 42' in '\n'.join(page.extract_text() for page in pdf.pages)
        print('Packaged PDF and LaTeX export passed.')


if __name__ == '__main__':
    main()
