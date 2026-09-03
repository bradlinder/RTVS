@echo off
setlocal
cd /d "%~dp0"
python RadioTVSegmenter.py %*
endlocal
