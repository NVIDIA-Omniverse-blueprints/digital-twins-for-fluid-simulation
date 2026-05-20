@echo off

rem SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
rem SPDX-License-Identifier: LicenseRef-NvidiaProprietary
rem
rem NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
rem property and proprietary rights in and to this material, related
rem documentation and any modifications thereto. Any use, reproduction,
rem disclosure or distribution of this material and related documentation
rem without an express license agreement from NVIDIA CORPORATION or
rem  its affiliates is strictly prohibited.

:: Set OMNI_REPO_ROOT early so `repo` bootstrapping can target the repository
:: root when writing out Python dependencies.
:: Use SETLOCAL and ENDLOCAL to constrain these variables to this batch file.
:: Use ENABLEDELAYEDEXPANSION to evaluate the value of PM_PACKAGES_ROOT
:: at execution time.
SETLOCAL ENABLEDELAYEDEXPANSION
set OMNI_REPO_ROOT="%~dp0"

:: Set Packman cache directory early if repo-cache.json is configured
:: so that the Packman Python version is not fetched from the web.
IF NOT EXIST "%~dp0repo-cache.json" goto :RepoCacheEnd

:: Read PM_PACKAGES_ROOT from repo-cache.json and make sure it is an absolute path (assume relative to the script directory).
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "$PM_PACKAGES_ROOT = (Get-Content '%~dp0repo-cache.json' | ConvertFrom-Json).PM_PACKAGES_ROOT; if ([System.IO.Path]::IsPathRooted($PM_PACKAGES_ROOT)) { Write-Output ('absolute;' + $PM_PACKAGES_ROOT) } else { Write-Output ('relative;' + $PM_PACKAGES_ROOT) }"`) do (
    for /f "tokens=1,2 delims=;" %%A in ("%%i") do (
        if /i "%%A" == "relative" (
            set PM_PACKAGES_ROOT=%~dp0%%B
        ) else (
            set PM_PACKAGES_ROOT=%%B
        )
    )
)

:RepoCacheEnd

call "%~dp0tools\packman\python.bat" "%~dp0tools\repoman\repoman.py" %*
if %errorlevel% neq 0 ( goto Error )

:Success
ENDLOCAL
exit /b 0

:Error
ENDLOCAL
exit /b %errorlevel%
