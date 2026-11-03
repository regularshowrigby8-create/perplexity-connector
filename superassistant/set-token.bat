@echo off
rem Saves the GitHub PAT from the clipboard into .github-pat (git-ignored).
rem Usage: copy the token (Ctrl+C), then run:  set-token.bat
powershell -ExecutionPolicy Bypass -File "%~dp0set-token.ps1"
