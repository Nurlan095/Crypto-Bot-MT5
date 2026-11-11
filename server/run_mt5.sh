#!/bin/bash
export WINEDEBUG=-all
export WINEPREFIX=/root/.wine
cd /opt/mt5
exec /usr/bin/xvfb-run -a -s "-screen 0 800x600x16" /usr/bin/wine /opt/mt5/terminal64.exe /portable /config:startup.ini
