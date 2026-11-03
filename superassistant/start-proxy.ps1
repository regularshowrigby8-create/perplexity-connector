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
if (-not $pat -and (Test-Path .github-pat)) { $pat = (Get-Content .github-pat -Raw) }
if (-not $pat -and (Test-Path "$HOME\.config\perplexity-connector\github-pat.txt")) { $pat = (Get-Content "$HOME\.config\perplexity-connector\github-pat.txt" -Raw) }
if ($pat) { $pat = $pat.Trim().TrimStart([char]0xFEFF) }   # strip whitespace/BOM (e.g. from Notepad)
if (-not $pat) {
  Write-Host "ERROR: no GitHub PAT found." -ForegroundColor Red
  Write-Host "  Set it for this window:  `$env:GITHUB_PAT = 'github_pat_...'"
  Write-Host "  or save it in this folder:  echo github_pat_... > .github-pat   (git-ignored)"
  exit 1
}
if ($pat -notmatch '^github_pat_[A-Za-z0-9_]{30,}$') {
  Write-Host "ERROR: '$pat' is not a real fine-grained PAT (must start with github_pat_ and be a long token, no '...' placeholders)." -ForegroundColor Red
  Write-Host "Create one at: github.com -> your avatar -> Settings -> Developer settings -> Personal access tokens -> Fine-grained tokens -> Generate new token"
  exit 1
}

# Pre-flight: ask GitHub if the token is valid (prints only HTTP status + login, never the token)
try {
  $me = Invoke-RestMethod -Uri https://api.github.com/user -Headers @{ Authorization = "Bearer $pat" } -Method Get
  Write-Host "GitHub token OK (HTTP 200, login: $($me.login))."
} catch {
  $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
  Write-Host "ERROR: api.github.com rejected this token (HTTP $code)." -ForegroundColor Red
  Write-Host "Regenerate it (fine-grained, needs 'Metadata: Read-only' + 'Contents: Read and write') and rerun .\set-token.bat."
  exit 1
}

# Documented in the repo README (public auth for your own Vercel connector).
$key = if ($env:CONNECTOR_API_KEY) { $env:CONNECTOR_API_KEY } else { 'ebc9973a4109f439485a7e562656eed428e9164733a90f8d' }

# Generate the config via gen-config.cjs (avoids PS5.1 native-arg quote mangling of
# node -e). Secrets go via env vars, never CLI args (those are visible in the process list).
$env:GEN_GITHUB_PAT = $pat
$env:GEN_CONNECTOR_KEY = $key
node (Join-Path $PSScriptRoot 'gen-config.cjs')
Remove-Item Env:GEN_GITHUB_PAT -ErrorAction SilentlyContinue
Remove-Item Env:GEN_CONNECTOR_KEY -ErrorAction SilentlyContinue

if ($env:DRY_RUN -eq '1') {
  $gen = Get-Content .generated-config.json -Raw
  Write-Host "OK: .generated-config.json generated and valid. Contents (secrets masked):"
  Write-Host ($gen -replace 'Bearer [^"]+', 'Bearer ***')
  exit 0
}

$transport = if ($args.Count -gt 0) { $args[0] } else { 'streamableHttp' }
$ep = switch ($transport) { 'sse' { '/sse' } 'ws' { '/message' } default { '/mcp' } }
Write-Host "Starting MCP SuperAssistant proxy on http://localhost:3006 (transport: $transport)"
Write-Host "In the browser extension, connect the sidebar to: http://localhost:3006$ep"
Write-Host "NOTE: at info level this proxy prints the Authorization header at startup - once connected, run 'cls'; don't screenshot the log. Set PROXY_LOGLEVEL=none to silence. Rotate the PAT when done."
$proxyArgs = @('-y', '@srbhptl39/mcp-superassistant-proxy@latest', '--config', '.generated-config.json', '--outputTransport', $transport, '--port', '3006')
if ($env:PROXY_LOGLEVEL) { $proxyArgs += @('--logLevel', $env:PROXY_LOGLEVEL) }
# Default binds 'localhost' which on Windows may resolve to IPv6 ::1 only (then 127.0.0.1
# fails). Set PROXY_HOST=0.0.0.0 to listen on all interfaces, or 127.0.0.1 for IPv4 loopback.
if ($env:PROXY_HOST) { $proxyArgs += @('--host', $env:PROXY_HOST) }
npx @proxyArgs
