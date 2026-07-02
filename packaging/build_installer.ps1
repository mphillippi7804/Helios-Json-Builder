$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
$appName = "Helios Interface Editor"
$sourceDir = Join-Path $projectDir "app"
$artifactDir = Join-Path $projectDir "artifacts"
$entryScript = Join-Path $sourceDir "$appName.py"
$iconPath = Join-Path $sourceDir "assets\Helios Interface Editor.ico"
$distDir = Join-Path $artifactDir "dist"
$buildDir = Join-Path $artifactDir "build"
$issPath = Join-Path $scriptDir "$appName.iss"

function Resolve-IsccPath {
    $pathCommand = Get-Command iscc -ErrorAction SilentlyContinue
    if ($pathCommand) {
        return $pathCommand.Source
    }

    $registryPaths = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )

    foreach ($registryPath in $registryPaths) {
        $installLocation = Get-ItemProperty $registryPath -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like "Inno Setup*" } |
            Select-Object -First 1 -ExpandProperty InstallLocation

        if (-not $installLocation) {
            continue
        }

        $candidate = Join-Path $installLocation "ISCC.exe"
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $commonPaths = @(
        "C:\Users\$env:USERNAME\AppData\Local\Programs\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )

    foreach ($candidate in $commonPaths) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

if (-not (Test-Path $entryScript)) {
    throw "Entry script not found: $entryScript"
}

python -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller..."
    python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller installation failed."
    }
}

New-Item -ItemType Directory -Force -Path $distDir, $buildDir *> $null

$pyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", $appName,
    "--distpath", $distDir,
    "--workpath", $buildDir,
    "--specpath", $scriptDir
)

if (Test-Path $iconPath) {
    $pyInstallerArgs += @("--icon", $iconPath, "--add-data", "$iconPath;.")
}

$pyInstallerArgs += $entryScript

Write-Host "Building executable..."
python @pyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$iscc = Resolve-IsccPath
if (-not $iscc) {
    Write-Warning "Inno Setup compiler (iscc) was not found. The executable build succeeded, but the installer was not created. Install Inno Setup, then rerun this script."
    exit 0
}

if (-not (Test-Path $issPath)) {
    throw "Installer script not found: $issPath"
}

Write-Host "Building installer..."
& $iscc $issPath
if ($LASTEXITCODE -ne 0) {
    throw "Installer build failed."
}

Write-Host "Build complete. Installer available at $(Join-Path $projectDir 'HeliosInterfaceEditorSetup.exe')"