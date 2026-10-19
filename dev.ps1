$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
& '.\.venv\Scripts\python.exe' scripts/dev.py
