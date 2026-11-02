param([switch]$SkipControlBuild)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Create .venv and install requirements.studio-build.txt first.' }
$localCargo = Join-Path $taskRoot '.artifacts/toolchain/cargo'
$localRustup = Join-Path $taskRoot '.artifacts/toolchain/rustup'
if (Test-Path -LiteralPath (Join-Path $localCargo 'bin/cargo.exe')) {
    $env:CARGO_HOME = $localCargo
    $env:RUSTUP_HOME = $localRustup
    $env:PATH = (Join-Path $localCargo 'bin') + ';' + $env:PATH
}
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) { throw 'Install Rust with the x86_64-pc-windows-msvc toolchain first.' }
$env:CARGO_TARGET_DIR = Join-Path $taskRoot '.artifacts/windows-build/target'
Push-Location $taskRoot
try {
    if (-not $SkipControlBuild) {
        & $taskPython scripts/desktop/build_studio.py --control-only
        if ($LASTEXITCODE -ne 0) { throw 'Control packaging failed.' }
    }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    Push-Location (Join-Path $taskRoot 'apps/desktop')
    try {
        & node (Join-Path $taskRoot 'node_modules/@tauri-apps/cli/tauri.js') build --bundles nsis --ci
        if ($LASTEXITCODE -ne 0) { throw 'Windows desktop packaging failed.' }
    } finally { Pop-Location }
    $version = (Get-Content -LiteralPath (Join-Path $taskRoot 'package.json') -Raw | ConvertFrom-Json).version
    $installer = Get-ChildItem -LiteralPath (Join-Path $env:CARGO_TARGET_DIR 'release/bundle/nsis') -Filter '*-setup.exe' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $installer) { throw 'No NSIS installer was produced.' }
    $output = Join-Path $taskRoot 'dist/windows'
    New-Item -ItemType Directory -Force -Path $output | Out-Null
    $destination = Join-Path $output "AiLab-$version-windows-x64-setup.exe"
    Copy-Item -LiteralPath $installer.FullName -Destination $destination -Force
    $hash = Get-FileHash -LiteralPath $destination -Algorithm SHA256
    "$($hash.Hash.ToLower())  $([IO.Path]::GetFileName($destination))" | Set-Content -LiteralPath (Join-Path $output 'SHA256SUMS.txt') -Encoding ascii
    Write-Output "Installer: $destination"
} finally { Pop-Location }
