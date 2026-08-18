@echo off
rem Launch the GoPro accelerometer player.
rem Usage:
rem   run.bat                        - default root (./Samples), pick files via the "Обзор" button
rem   run.bat "D:\GoPro\Jump1"       - open a specific folder of .MP4 files
rem   drag a folder onto this file   - same as passing it as the argument
cd /d "%~dp0"
if "%~1"=="" (
  echo Launching GoPro accelerometer player...
  echo Tip: pass a folder with .MP4 files, e.g.  run.bat "D:\GoPro\Jump1"
  echo      or drag a folder onto this file.
  python -m gopro_accel
) else (
  python -m gopro_accel --root "%~1"
)
