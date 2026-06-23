@echo off
:: Ov3rLoRd -- Launcher Python 3.12
:: Usage :
::   run.bat --media-type anime --universe "evangelion battle asuka"
::   run.bat --media-type anime --universe "evangelion battle asuka" --no-qc
::   run.bat --bible --media-type anime --universe "evangelion battle asuka"
::   run.bat --no-qc --media-type anime --universe "evangelion battle asuka" --batch 3
py -3.12 maestro.py %*
