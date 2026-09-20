#!/bin/bash
cd "$(dirname "$0")"
clear
printf "===============================================\n"
printf " Liquidity MVP · Behavioral + LCR/NSFR Engine\n"
printf "===============================================\n\n"
python3 start_local.py
STATUS=$?
printf "\nLauncher finished with status %s.\n" "$STATUS"
if [ "$STATUS" -ne 0 ]; then
  printf "Review the error above. Press Enter to close.\n"
  read
fi
exit "$STATUS"
