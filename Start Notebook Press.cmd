@echo off
pushd "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m notebook_press
) else (
    echo Install first: python -m venv .venv
    echo Then: .venv\Scripts\python.exe -m pip install -e .
    pause
)
popd
