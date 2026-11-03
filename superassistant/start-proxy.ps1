# start-proxy.ps1 - Windows (PowerShell) launcher for the MCP SuperAssistant proxy.
# Same behavior as start-proxy.sh: resolves the GitHub PAT, generates a gitignored
# .generated-config.json (UTF-8, no BOM), then runs the proxy on port 3006.
# Usage:
#   .\start-proxy.bat            (or: powershell -File .\start-proxy.ps1)
#   .\start-proxy.bat sse        (SSE output at /sse instead of /mcp)
#   $env:DRY_RUN='1'; .\start-proxy.bat   (only generate + show config, secrets masked)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$pat = $env:GITHUB_PAT
if (-not $pat -and (Test-Path .github-pat)) { $pat = (Get-Content .github-pat -Raw).Trim() }
if (-not $pat -and (Test-Path "$HOME\.config\perplexity-connector\github-pat.txt")) { $pat = (Get-Content "$HOME\.config\perplexity-connector\github-pat.txt" -Raw).Trim() }
if (-not $pat) {
  Write-Host "ERROR: no GitHub PAT found." -ForegroundColor Red
  Write-Host "  Set it for this window:  `$env:GITHUB_PAT = 'github_pat_...'"
  Write-Host "  or save it in this folder:  echo github_pat_... > .github-pat   (git-ignored)"
  exit 1
}
if ($pat.Contains('...')) {
  Write-Host "ERROR: the PAT still contains the '...' placeholder. Put your REAL token (it starts with github_pat_) in .github-pat or `$env:GITHUB_PAT." -ForegroundColor Red
  exit 1
}

# Documented in the repo README (public auth for your own Vercel connector).
$key = if ($env:CONNECTOR_API_KEY) { $env:CONNECTOR_API_KEY } else { 'ebc9973a4109f439485a7e562656eed428e9164733a90f8d' }

$tpl = Get-Content config.template.json -Raw
$out = $tpl.Replace('__GITHUB_PAT__', $pat).Replace('__CONNECTOR_API_KEY__', $key)
$null = $out | ConvertFrom-Json   # validate JSON before writing
[System.IO.File]::WriteAllText((Join-Path $PWD '.generated-config.json'), $out)  # UTF-8 no BOM

if ($env:DRY_RUN -eq '1') {
  Write-Host "OK: .generated-config.json generated and valid. Contents (secrets masked):"
  Write-Host ($out -replace 'Bearer [^"]+', 'Bearer ***')
  exit 0
}

$transport = if ($args.Count -gt 0) { $args[0] } else { 'streamableHttp' }
$ep = switch ($transport) { 'sse' { '/sse' } 'ws' { '/message' } default { '/mcp' } }
Write-Host "Starting MCP SuperAssistant proxy on http://localhost:3006 (transport: $transport)"
Write-Host "In the browser extension, connect the sidebar to: http://localhost:3006$ep"
npx -y @srbhptl39/mcp-superassistant-proxy@latest --config .generated-config.json --outputTransport $transport --port 3006
