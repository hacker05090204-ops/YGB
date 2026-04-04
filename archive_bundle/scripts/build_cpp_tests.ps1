[CmdletBinding()]
param(
    [switch]$SkipCoverage
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$nativeDir = Join-Path $root "native"
$objDir = Join-Path $root "obj"
$exePath = Join-Path $root "run_cpp_tests.exe"
$coveragePath = Join-Path $root "coverage_cpp.json"
$wrapperNames = @(
    "tw_precision_monitor",
    "tw_drift_monitor",
    "tw_freeze_invalidator",
    "tw_shadow_merge_validator",
    "tw_dataset_entropy",
    "tw_curriculum_scheduler",
    "tw_cross_device_validator",
    "tw_hunt_precision",
    "tw_hunt_duplicate",
    "tw_hunt_scope"
)

function Get-Compiler {
    foreach ($name in @("cl.exe", "g++.exe", "clang++.exe", "g++", "clang++")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) {
            $kind = if ($cmd.Name -ieq "cl.exe") { "msvc" } else { "gnu" }
            return @{
                Name = $cmd.Name
                Path = $cmd.Source
                Kind = $kind
            }
        }
    }

    return $null
}

function Get-WrapperPaths {
    return $wrapperNames | ForEach-Object { Join-Path $nativeDir ("test_wrappers\" + $_ + ".cpp") }
}

function Get-DependencyPaths {
    $paths = [System.Collections.Generic.List[string]]::new()
    [void]$paths.Add((Join-Path $nativeDir "run_cpp_tests.cpp"))

    foreach ($wrapperPath in Get-WrapperPaths) {
        [void]$paths.Add($wrapperPath)
        foreach ($line in Get-Content $wrapperPath) {
            if ($line -match '^\s*#include\s+"(\.\./[^"]+)"') {
                $full = [System.IO.Path]::GetFullPath((Join-Path (Split-Path $wrapperPath -Parent) $Matches[1]))
                if (Test-Path $full) {
                    [void]$paths.Add($full)
                }
            }
        }
    }

    return $paths | Sort-Object -Unique
}

function Get-StalePrebuiltInputs {
    if (-not (Test-Path $exePath)) {
        return @()
    }

    $exe = Get-Item $exePath
    return @(Get-DependencyPaths | ForEach-Object { Get-Item $_ } | Where-Object {
        $_.LastWriteTimeUtc -gt $exe.LastWriteTimeUtc
    })
}

function Invoke-GnuBuild {
    param([string]$CompilerPath)

    New-Item -ItemType Directory -Force -Path $objDir | Out-Null
    $objectPaths = @()
    $commonArgs = @("-std=c++17", "-O0", "--coverage", "-fprofile-arcs", "-ftest-coverage")

    Write-Host "=== Building C++ test suite ==="
    foreach ($wrapperName in $wrapperNames) {
        $source = Join-Path $nativeDir ("test_wrappers\" + $wrapperName + ".cpp")
        $object = Join-Path $objDir ($wrapperName + ".o")
        $objectPaths += $object
        Write-Host ("  Compiling " + $wrapperName + "...")
        & $CompilerPath @commonArgs "-c" $source "-o" $object
        if ($LASTEXITCODE -ne 0) {
            throw "Failed compiling $wrapperName with $CompilerPath"
        }
    }

    Write-Host "  Linking..."
    & $CompilerPath @commonArgs (Join-Path $nativeDir "run_cpp_tests.cpp") @objectPaths "-o" $exePath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed linking C++ test suite with $CompilerPath"
    }

    return $true
}

function Invoke-MsvcBuild {
    param([string]$CompilerPath)

    New-Item -ItemType Directory -Force -Path $objDir | Out-Null
    $objectPaths = @()

    Write-Host "=== Building C++ test suite ==="
    foreach ($wrapperName in $wrapperNames) {
        $source = Join-Path $nativeDir ("test_wrappers\" + $wrapperName + ".cpp")
        $object = Join-Path $objDir ($wrapperName + ".obj")
        $objectPaths += $object
        Write-Host ("  Compiling " + $wrapperName + "...")
        & $CompilerPath "/nologo" "/std:c++17" "/EHsc" "/Od" "/c" $source "/Fo$object"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed compiling $wrapperName with $CompilerPath"
        }
    }

    Write-Host "  Linking..."
    & $CompilerPath "/nologo" "/std:c++17" "/EHsc" "/Od" (Join-Path $nativeDir "run_cpp_tests.cpp") @objectPaths "/Fe$exePath"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed linking C++ test suite with $CompilerPath"
    }

    return $true
}

function Invoke-CoverageIfAvailable {
    param([string]$CompilerKind)

    if ($SkipCoverage) {
        Write-Host "Coverage skipped by request."
        return
    }

    if ($CompilerKind -ne "gnu") {
        Write-Warning "Coverage generation is only enabled for GNU-style toolchains in this script."
        return
    }

    $gcovCmd = Get-Command "gcov" -ErrorAction SilentlyContinue | Select-Object -First 1
    $gcovrCmd = Get-Command "gcovr" -ErrorAction SilentlyContinue | Select-Object -First 1

    if (-not $gcovCmd -or -not $gcovrCmd) {
        Write-Warning "gcov/gcovr not available; skipping coverage report generation."
        return
    }

    Write-Host ""
    Write-Host "=== C++ Coverage Report ==="
    & $gcovrCmd.Source "-r" $root "--filter" ($nativeDir + [System.IO.Path]::DirectorySeparatorChar) `
        "--exclude" (Join-Path $nativeDir "test_wrappers") `
        "--exclude" (Join-Path $nativeDir "run_cpp_tests.cpp") `
        "--json" $coveragePath `
        "--print-summary"
    if ($LASTEXITCODE -ne 0) {
        throw "gcovr coverage generation failed"
    }
}

$compiler = Get-Compiler
$usedCompilerKind = "prebuilt"

if ($compiler) {
    Write-Host ("Using compiler: " + $compiler.Name + " (" + $compiler.Kind + ")")
    if ($compiler.Kind -eq "msvc") {
        Invoke-MsvcBuild -CompilerPath $compiler.Path | Out-Null
    } else {
        Invoke-GnuBuild -CompilerPath $compiler.Path | Out-Null
    }
    $usedCompilerKind = $compiler.Kind
} elseif (Test-Path $exePath) {
    $staleInputs = @(Get-StalePrebuiltInputs)
    Write-Warning "No supported compiler found. Falling back to the checked-in run_cpp_tests.exe."
    if ($staleInputs.Count -gt 0) {
        Write-Warning "Prebuilt native test binary may be stale relative to local sources."
        $staleInputs | Select-Object -First 5 | ForEach-Object {
            Write-Warning ("  newer source: " + $_.FullName)
        }
    }
} else {
    throw "No supported compiler found and no prebuilt test binary is available."
}

Write-Host "=== Running C++ self-tests ==="
& $exePath
$testExit = $LASTEXITCODE

if ($testExit -ne 0) {
    exit $testExit
}

Invoke-CoverageIfAvailable -CompilerKind $usedCompilerKind
exit $testExit
