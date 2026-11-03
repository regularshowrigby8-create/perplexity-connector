# set-token.ps1 - save your GitHub PAT to .github-pat from the CLIPBOARD.
# The token is never typed, never printed, never stored in shell history or chat.
# Usage:  copy the token (Ctrl+C), then run:  .\set-token.bat
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$t = (Get-Clipboard).Trim()
if ($t -notmatch '^github_pat_[A-Za-z0-9_]{30,}$') {
  Write-Host "ERROR: clipboard does not contain a fine-grained PAT (github_pat_...). Copy the token first, then rerun." -ForegroundColor Red
  exit 1
}
[System.IO.File]::WriteAllText((Join-Path $PWD '.github-pat'), $t)   # UTF-8 no BOM; .github-pat is git-ignored
Write-Host "OK: PAT saved to .github-pat (git-ignored). The token itself is NOT printed here."
Write-Host "Use it:  .\start-proxy.bat        (restart the proxy after changing the token)"
Write-Host "Rotate later: revoke the old token at github.com/settings/tokens, make a new one, copy it, run .\set-token.bat again."
