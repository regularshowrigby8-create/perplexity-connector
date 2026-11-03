# set-token.ps1 - save your GitHub PAT to .github-pat from the CLIPBOARD.
# The token is never typed, never printed, never stored in shell history or chat.
# Usage:  copy the token (Ctrl+C), then run:  .\set-token.bat
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
# Accept the whole clipboard and EXTRACT the token from it, so copying a whole chat
# line (or any surrounding text) still works. Falls back to $env:GITHUB_PAT.
$raw = @(Get-Clipboard) -join "`n"
if ($raw -match 'github_pat_[A-Za-z0-9_]{30,}') { $t = $Matches[0] }
elseif ($env:GITHUB_PAT -match 'github_pat_[A-Za-z0-9_]{30,}') { $t = $Matches[0] }
else { $t = $raw.Trim().TrimStart([char]0xFEFF) }
$t = $t.Trim().TrimStart([char]0xFEFF)
if ($t -notmatch '^github_pat_[A-Za-z0-9_]{30,}$') {
  Write-Host "ERROR: no fine-grained PAT (github_pat_...) found on the clipboard." -ForegroundColor Red
  Write-Host "Copy the token (or any text containing it) and rerun, OR edit the file directly:"
  Write-Host "  notepad .github-pat     -> paste the token -> save"
  exit 1
}
[System.IO.File]::WriteAllText((Join-Path $PWD '.github-pat'), $t)   # UTF-8 no BOM; .github-pat is git-ignored
Write-Host "OK: PAT saved to .github-pat (git-ignored). The token itself is NOT printed here."
Write-Host "Use it:  .\start-proxy.bat        (restart the proxy after changing the token)"
Write-Host "Rotate later: revoke the old token at github.com/settings/tokens, make a new one, copy it, run .\set-token.bat again."
