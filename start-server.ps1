$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
Set-Location $root
& $python (Join-Path $root "server.py")
