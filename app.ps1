param(
    [ValidateSet('start','update','doctor','check','stop','status','logs')][string]$Action = 'start',
    [ValidateSet('dev','installed')][string]$Mode = 'dev',
    [string]$Image,
    [int]$Port = 0,
    [switch]$AllowLocalImage
)
$ErrorActionPreference = 'Stop'
$appPython = $null
foreach ($appCandidate in @('python', 'py', 'python3')) {
    if (Get-Command $appCandidate -ErrorAction SilentlyContinue) {
        $ErrorActionPreference = 'Continue'
        $null = & $appCandidate -c 'import sys; sys.exit(sys.version_info < (3,10))' 2>&1
        $ErrorActionPreference = 'Stop'
        if ($LASTEXITCODE -eq 0) { $appPython = $appCandidate; break }
    }
}
if (-not $appPython) { throw 'Install Python 3.10+, Git and Docker with Compose v2, then retry.' }
$appArguments = @((Join-Path $PSScriptRoot 'scripts/app.py'), $Action, '--mode', $Mode)
if ($Image) { $appArguments += @('--image', $Image) }
if ($Port) { $appArguments += @('--port', "$Port") }
if ($AllowLocalImage) { $appArguments += '--allow-local-image' }
& $appPython @appArguments
exit $LASTEXITCODE
