# Runs the regression suite with process-local configuration and AWS/network guards.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$testExitCode = 1
Push-Location -LiteralPath $projectRoot
try {
    & .\.venv\Scripts\python.exe -B -m tests.run_offline
    $testExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $testExitCode
