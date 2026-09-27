# Use when .venv pandas is blocked by Application Control in some shells.
$env:PYTHONPATH = "$PSScriptRoot\..\src"
& "C:\ProgramData\anaconda3\python.exe" @args
