# Tune 4.0 build. Usage: powershell -File build_v40.ps1 [-Out <folder outside the source tree>]
# Requires PyInstaller (see requirements-build.txt).
param([string]$Out = "$env:TEMP\Tune-v4.0-build")
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m unittest test_capture test_reference test_desk -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
New-Item -ItemType Directory -Force $Out | Out-Null
python desk_icon.py "$Out\Tune.ico"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Tune --icon "$Out\Tune.ico" `
  --distpath "$Out\dist" --workpath "$Out\work" --specpath "$Out" desk_app.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
