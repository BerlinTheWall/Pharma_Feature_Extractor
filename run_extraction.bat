@echo off
REM ===================================================================
REM  Unattended full-corpus extraction launcher (Windows + local Ollama)
REM
REM  Restarts the pipeline automatically if it dies. Safe to do, because
REM  every finished PDF is checkpointed: a restart resumes, it does not
REM  redo work.
REM
REM  Usage:  run_extraction.bat ["path\to\Product monograph"]
REM ===================================================================

setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

REM --- Settings ------------------------------------------------------
if "%~1"=="" (
    set "TARGET=..\..\Received Monographs\Product monograph"
) else (
    set "TARGET=%~1"
)
set "OUTPUT_DIR=%~dp0output"
set "MAX_RESTARTS=100"
set "RESTART_WAIT=60"

REM UTF-8 so the emoji progress output survives redirection to the log.
set "PYTHONIOENCODING=utf-8"
REM Unbuffered, so the log is current if you tail it from another machine.
set "PYTHONUNBUFFERED=1"

REM Local Ollama. Change the model here to run a comparison sweep.
set "PHARMA_EXTRACTOR_BASE_URL=http://localhost:11434/v1"
set "PHARMA_EXTRACTOR_API_KEY=ollama"
set "PHARMA_EXTRACTOR_MODEL=mistral"
REM No hosted rate limit to respect when the model is local.
set "PHARMA_EXTRACTOR_SAFE_DELAY=0"

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "DT=%%I"
set "STAMP=!DT:~0,8!_!DT:~8,6!"
set "LOG=%OUTPUT_DIR%\run_!STAMP!.log"

echo Target folder : %TARGET%
echo Output folder : %OUTPUT_DIR%
echo Log file      : !LOG!
echo Model         : %PHARMA_EXTRACTOR_MODEL% @ %PHARMA_EXTRACTOR_BASE_URL%
echo.

REM --- Keep the machine awake for the whole run ----------------------
powercfg /change standby-timeout-ac 0 >nul 2>&1
powercfg /change hibernate-timeout-ac 0 >nul 2>&1
powercfg /change disk-timeout-ac 0 >nul 2>&1

REM --- Supervised run loop -------------------------------------------
set /a attempt=0

:runloop
set /a attempt+=1
echo [%date% %time%] === attempt !attempt! of %MAX_RESTARTS% === >> "!LOG!"
python run.py "%TARGET%" -o "%OUTPUT_DIR%" >> "!LOG!" 2>&1
set "EXITCODE=!errorlevel!"

if "!EXITCODE!"=="0" goto done
if "!EXITCODE!"=="130" goto interrupted
if !attempt! GEQ %MAX_RESTARTS% goto giveup

echo [%date% %time%] exited with code !EXITCODE! - restarting in %RESTART_WAIT%s >> "!LOG!"
echo Exited with code !EXITCODE!. Restarting in %RESTART_WAIT%s (resumes from checkpoint)...
timeout /t %RESTART_WAIT% /nobreak >nul
goto runloop

:interrupted
echo [%date% %time%] stopped by user >> "!LOG!"
echo Stopped by user. Rerun this script to resume.
goto end

:giveup
echo [%date% %time%] giving up after !attempt! attempts >> "!LOG!"
echo Gave up after !attempt! attempts. See !LOG!
goto end

:done
echo [%date% %time%] completed successfully >> "!LOG!"
echo.
echo Done. Results: %OUTPUT_DIR%
goto end

:end
endlocal
