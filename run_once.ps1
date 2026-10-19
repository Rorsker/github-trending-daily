param(
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [string]$Python = 'python',
    [string]$Model,
    [ValidateRange(1,2147483647)][int]$TimeoutSeconds = 120,
    [ValidateSet('codex','json')][string]$Backend = 'codex',
    [string]$AnalysisFile
)
# Windows PowerShell otherwise encodes redirected diagnostics using the OEM code page.
# Match the Python CLI UTF-8 contract for normal output and localized errors.
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$ErrorActionPreference = 'Stop'
$invokeArgs = @('-B', (Join-Path $PSScriptRoot 'trending.py'), 'run', '--output-dir', $OutputDir, '--timeout', "$TimeoutSeconds", '--backend', $Backend)
if ($Model) { $invokeArgs += @('--model', $Model) }
if ($AnalysisFile) { $invokeArgs += @('--analysis-file', $AnalysisFile) }
try {
    # Resolve launch errors before allowing child stderr to flow normally.
    $null = Get-Command -Name $Python -ErrorAction Stop
    # Stop would turn a child's Write-Error/native stderr into a wrapper
    # exception and replace its real exit code with 1 (Windows PowerShell).
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    & $Python @invokeArgs
    $childExitCode = $LASTEXITCODE
    exit $childExitCode
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
