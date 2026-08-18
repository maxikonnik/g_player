<#
  Launch the GoPro accelerometer player.
  Usage:
    .\run.ps1                              # default root (./Samples), pick files via "Обзор"
    .\run.ps1 -Root "D:\GoPro\Jump1"       # open a specific folder of .MP4 files
    .\run.ps1 -Root "D:\GoPro\Jump1" -Port 8090
#>
param(
  [string]$Root,
  [int]$Port = 8770
)
Set-Location -LiteralPath $PSScriptRoot
if ($Root) {
  python -m gopro_accel --root $Root --port $Port
} else {
  Write-Host "Tip: .\run.ps1 -Root 'D:\GoPro\Jump1'  (a folder with .MP4 files)"
  python -m gopro_accel --port $Port
}
