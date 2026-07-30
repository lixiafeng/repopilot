$ErrorActionPreference = "Stop"

Write-Host "== RepoPilot final check =="

Write-Host ""
Write-Host "1. Compile source"
python -m compileall src -q
if ($LASTEXITCODE -ne 0) {
    throw "compileall failed"
}

Write-Host ""
Write-Host "2. Run automated tests"
python -m pytest tests -q
if ($LASTEXITCODE -ne 0) {
    throw "pytest failed"
}

Write-Host ""
Write-Host "3. Check CLI help"
python -m repo_pilot.cli --help
if ($LASTEXITCODE -ne 0) {
    throw "CLI help failed"
}

Write-Host ""
Write-Host "4. Check Eval CLI help"
python -m repo_pilot.eval_cli --help
if ($LASTEXITCODE -ne 0) {
    throw "Eval CLI help failed"
}

Write-Host ""
Write-Host "Final check passed."
