$ErrorActionPreference = 'Stop'
$project = $PSScriptRoot
$today = (Get-Date).ToString('yyyy-MM-dd')
$out = Join-Path $project "output\$today"
$stateDir = Join-Path $out 'automation'
$statusFile = Join-Path $stateDir 'run-status.json'
$notifier = 'E:\workload\tools\feishu-notifier\send_report.py'
$stage = 'discover'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

$codexDir = Join-Path $env:APPDATA 'npm'
$codexCommand = Join-Path $codexDir 'codex.cmd'
if(-not (Test-Path -LiteralPath $codexCommand -PathType Leaf)) {
  throw "Codex CLI missing: $codexCommand. Install with npm.cmd install -g @openai/codex."
}
$env:PATH = "$codexDir;$env:PATH"

function Save-Status($value) {
  $value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $statusFile -Encoding UTF8
}

function Confirm-Report($path) {
  if(-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Report missing: $path" }
  $bundle = Split-Path -Parent $path
  $manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $bundle 'manifest.json') | ConvertFrom-Json
  if($manifest.identity.day -ne $today) { throw "Report date mismatch: $path" }
  $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
  if($manifest.report_sha256 -ne $hash) { throw "Report hash mismatch: $path" }
  return $hash
}

try {
  Save-Status @{date=$today; status='running'; stage='discover'; pid=$PID; started_at=(Get-Date).ToString('o')}
  $report = $null
  $manifests = @(Get-ChildItem (Join-Path $out 'reports') -Filter 'manifest.json' -Recurse -File -ErrorAction SilentlyContinue)
  foreach($file in $manifests) {
    $entry = Get-Content -Raw -Encoding UTF8 $file.FullName | ConvertFrom-Json
    if($entry.identity.day -eq $today -and $entry.identity.publication_policy -eq 'no-repeat-v1') {
      $candidate = Join-Path $file.DirectoryName 'report.md'
      $null = Confirm-Report $candidate
      $report = $candidate
      break
    }
  }
  if(-not $report) {
    $stage = 'generation'
    Save-Status @{date=$today; status='running'; stage='generation'; pid=$PID; started_at=(Get-Date).ToString('o')}
    $stdout = Join-Path $stateDir 'generation.stdout.json'
    $stderr = Join-Path $stateDir 'generation.stderr.log'
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
      Push-Location $project
      try {
        & python -B (Join-Path $project 'trending.py') run --output-dir $out --timeout 600 1> $stdout 2> $stderr
        $exitCode = $LASTEXITCODE
      } finally { Pop-Location }
    } finally { $ErrorActionPreference = $previousErrorAction }
    if($exitCode -ne 0) {
      $errorText = Get-Content -Raw -Encoding UTF8 $stderr -ErrorAction SilentlyContinue
      if($errorText -match 'all collected repositories have already appeared') {
        Save-Status @{date=$today; status='no-new-projects'; stage='generation'; completed_at=(Get-Date).ToString('o')}
        exit 0
      }
      throw "Trending generation failed (exit $exitCode); inspect $stderr"
    }
    $result = Get-Content -Raw -Encoding UTF8 $stdout | ConvertFrom-Json
    $report = [string]$result.report
    if(-not $report) { throw 'Trending run returned no report path' }
    $expectedRoot = [IO.Path]::GetFullPath($out).TrimEnd('\') + '\'
    if(-not [IO.Path]::GetFullPath($report).StartsWith($expectedRoot,[StringComparison]::OrdinalIgnoreCase)) {
      throw "Trending report escaped today's output directory: $report"
    }
    $null = Confirm-Report $report
  }
  $stage = 'delivery'
  Save-Status @{date=$today; status='running'; stage='delivery'; report=$report; pid=$PID; started_at=(Get-Date).ToString('o')}
  $deliveryDir = Join-Path $out 'delivery'
  $pushOut = Join-Path $stateDir 'feishu.stdout.json'
  $pushErr = Join-Path $stateDir 'feishu.stderr.log'
  $previousErrorAction = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    & python -B $notifier --report $report --state-dir $deliveryDir 1> $pushOut 2> $pushErr
    $pushExit = $LASTEXITCODE
  } finally { $ErrorActionPreference = $previousErrorAction }
  if($pushExit -ne 0) { throw "Feishu delivery failed (exit $pushExit); inspect $pushErr" }
  $pushResult = Get-Content -Raw -Encoding UTF8 $pushOut | ConvertFrom-Json
  if($pushResult.status -notin @('sent','already_sent')) { throw 'Feishu returned no confirmed delivery status' }
  Save-Status @{date=$today; status='success'; stage='complete'; report=$report; push_status=$pushResult.status; push_receipt=$pushResult.receipt; completed_at=(Get-Date).ToString('o')}
} catch {
  Save-Status @{date=$today; status='failed'; stage=$stage; error=$_.Exception.Message; completed_at=(Get-Date).ToString('o')}
  exit 1
}
