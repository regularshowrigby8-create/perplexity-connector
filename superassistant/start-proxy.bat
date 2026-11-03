@echo off
rem Windows launcher for the MCP SuperAssistant proxy.
rem Usage:  start-proxy.bat          (Streamable HTTP on http://localhost:3006/mcp)
rem         start-proxy.bat sse      (SSE on /sse)      start-proxy.bat ws  (WS on /message)
rem Token comes from $env:GITHUB_PAT or .github-pat in this folder (git-ignored).
powershell -ExecutionPolicy Bypass -File "%~dp0start-proxy.ps1" %*
