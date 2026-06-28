# Bundle MSVC CRT, UCRT and verify goosed.exe DLL dependencies for self-contained MSI.
param(
    [Parameter(Mandatory = $true)]
    [string]$DestDir,

    [Parameter(Mandatory = $true)]
    [string]$GoosedExe
)

$ErrorActionPreference = 'Stop'

function Resolve-VsWherePath {
    $candidate = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path -LiteralPath $candidate)) {
        throw "vswhere.exe not found at $candidate"
    }
    return $candidate
}

function Resolve-VisualStudioInstallPath {
    $vswhere = Resolve-VsWherePath
    $installPath = & $vswhere -latest -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $installPath) {
        throw 'Visual Studio installation with VC tools not found'
    }
    return $installPath.Trim()
}

function Resolve-MsvcCrtDirectory {
    param([string]$VsInstallPath)
    $redistRoot = Join-Path $VsInstallPath 'VC\Redist\MSVC'
    if (-not (Test-Path -LiteralPath $redistRoot)) {
        throw "MSVC redist root missing: $redistRoot"
    }

    $crtCandidates = @()
    foreach ($versionDir in Get-ChildItem -LiteralPath $redistRoot -Directory) {
        $x64Root = Join-Path $versionDir.FullName 'x64'
        if (-not (Test-Path -LiteralPath $x64Root)) {
            continue
        }
        foreach ($crtDir in Get-ChildItem -LiteralPath $x64Root -Directory -Filter 'Microsoft.VC*.CRT') {
            $crtCandidates += [PSCustomObject]@{
                VersionDir = $versionDir.Name
                CrtDir = $crtDir.FullName
                CrtName = $crtDir.Name
            }
        }
    }

    if ($crtCandidates.Count -eq 0) {
        $layout = Get-ChildItem -LiteralPath $redistRoot -Recurse -Directory -Filter 'Microsoft.VC*.CRT' |
            ForEach-Object { $_.FullName }
        $layoutHint = if ($layout) { ($layout -join '; ') } else { 'none' }
        throw "No Microsoft.VC*.CRT directory under $redistRoot (found: $layoutHint)"
    }

    $selected = $crtCandidates |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.CrtDir 'vcruntime140.dll') } |
        Sort-Object { [version]($_.VersionDir -replace '^v', '') } -Descending |
        Select-Object -First 1

    if (-not $selected) {
        $searched = ($crtCandidates | ForEach-Object { $_.CrtDir }) -join '; '
        throw "No MSVC CRT directory with vcruntime140.dll. Candidates: $searched"
    }

    Write-Host "Using MSVC CRT: $($selected.CrtDir) ($($selected.CrtName), redist $($selected.VersionDir))"
    return $selected.CrtDir
}

function Resolve-UcrtDirectory {
    $kitsRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\Redist'
    if (-not (Test-Path -LiteralPath $kitsRoot)) {
        throw "Windows Kits redist root missing: $kitsRoot"
    }
    $versionDir = Get-ChildItem -LiteralPath $kitsRoot -Directory |
        Where-Object { $_.Name -match '^10\.0\.' } |
        Sort-Object { [version]$_.Name } -Descending |
        Select-Object -First 1
    if (-not $versionDir) {
        throw "No Windows SDK redist version under $kitsRoot"
    }
    $ucrtDir = Join-Path $versionDir.FullName 'ucrt\DLLs\x64'
    if (-not (Test-Path -LiteralPath $ucrtDir)) {
        throw "UCRT directory missing: $ucrtDir"
    }
    return $ucrtDir
}

function Resolve-DumpbinPath {
    param([string]$VsInstallPath)
    $toolsRoot = Join-Path $VsInstallPath 'VC\Tools\MSVC'
    $toolsVersion = Get-ChildItem -LiteralPath $toolsRoot -Directory |
        Sort-Object Name -Descending |
        Select-Object -First 1
    if (-not $toolsVersion) {
        throw "MSVC tools version directory missing under $toolsRoot"
    }
    $dumpbin = Join-Path $toolsVersion.FullName 'bin\Hostx64\x64\dumpbin.exe'
    if (-not (Test-Path -LiteralPath $dumpbin)) {
        throw "dumpbin.exe not found at $dumpbin"
    }
    return $dumpbin
}

function Copy-DllDirectory {
    param(
        [string]$SourceDir,
        [string]$Label
    )
    $copied = 0
    Get-ChildItem -LiteralPath $SourceDir -Filter '*.dll' -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $DestDir $_.Name) -Force
        $copied += 1
    }
    Write-Host "Copied $copied DLL(s) from $Label ($SourceDir)"
}

function Test-SystemDllName {
    param([string]$DllName)
    $normalized = $DllName.ToLowerInvariant()
    if ($normalized.StartsWith('api-ms-win-')) {
        return $true
    }
    if ($normalized.StartsWith('ext-ms-win-')) {
        return $true
    }
    $systemDlls = @(
        'kernel32.dll',
        'user32.dll',
        'advapi32.dll',
        'shell32.dll',
        'ole32.dll',
        'oleaut32.dll',
        'ws2_32.dll',
        'bcrypt.dll',
        'crypt32.dll',
        'secur32.dll',
        'ncrypt.dll',
        'iphlpapi.dll',
        'shlwapi.dll',
        'userenv.dll',
        'winhttp.dll',
        'gdi32.dll',
        'combase.dll',
        'rpcrt4.dll',
        'msvcrt.dll',
        'ntdll.dll',
        'psapi.dll',
        'version.dll',
        'setupapi.dll',
        'cfgmgr32.dll',
        'powrprof.dll',
        'dbghelp.dll',
        'imm32.dll',
        'winmm.dll',
        'dnsapi.dll',
        'normaliz.dll',
        'wtsapi32.dll',
        'profapi.dll',
        'sspicli.dll',
        'cryptbase.dll',
        'bcryptprimitives.dll',
        'kernelbase.dll',
        'windows.storage.dll',
        'shcore.dll',
        'uxtheme.dll',
        'dwmapi.dll'
    )
    return $systemDlls -contains $normalized
}

function Assert-GoosedDependenciesBundled {
    param(
        [string]$DumpbinPath,
        [string]$BinaryPath,
        [string]$BundleDir
    )
    $output = & $DumpbinPath /nologo /dependents $BinaryPath
    if ($LASTEXITCODE -ne 0) {
        throw "dumpbin failed for $BinaryPath with exit code $LASTEXITCODE"
    }

    $missing = New-Object System.Collections.Generic.List[string]
    foreach ($line in $output) {
        $trimmed = $line.Trim()
        if (-not $trimmed.EndsWith('.dll', [System.StringComparison]::OrdinalIgnoreCase)) {
            continue
        }
        if (Test-SystemDllName -DllName $trimmed) {
            continue
        }
        $candidate = Join-Path $BundleDir $trimmed
        if (-not (Test-Path -LiteralPath $candidate)) {
            $missing.Add($trimmed)
        }
    }

    if ($missing.Count -gt 0) {
        $missingList = ($missing | Sort-Object) -join ', '
        throw "goosed.exe dependencies missing in $BundleDir`: $missingList"
    }

    Write-Host "dumpbin dependency gate passed for $BinaryPath"
}

if (-not (Test-Path -LiteralPath $GoosedExe)) {
    throw "goosed.exe missing: $GoosedExe"
}
if (-not (Test-Path -LiteralPath $DestDir)) {
    New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
}

$vsInstallPath = Resolve-VisualStudioInstallPath
$msvcCrtDir = Resolve-MsvcCrtDirectory -VsInstallPath $vsInstallPath
$ucrtDir = Resolve-UcrtDirectory
$dumpbinPath = Resolve-DumpbinPath -VsInstallPath $vsInstallPath

Copy-DllDirectory -SourceDir $msvcCrtDir -Label 'MSVC CRT'
Copy-DllDirectory -SourceDir $ucrtDir -Label 'UCRT'

$requiredBundled = @(
    'vcruntime140.dll',
    'vcruntime140_1.dll',
    'msvcp140.dll',
    'ucrtbase.dll'
)
foreach ($requiredName in $requiredBundled) {
    $requiredPath = Join-Path $DestDir $requiredName
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required bundled runtime DLL missing after copy: $requiredName"
    }
}

Assert-GoosedDependenciesBundled -DumpbinPath $dumpbinPath -BinaryPath $GoosedExe -BundleDir $DestDir

$bundledDllCount = (Get-ChildItem -LiteralPath $DestDir -Filter '*.dll' -File).Count
Write-Host "Windows runtime bundle complete: $bundledDllCount DLL(s) in $DestDir"
