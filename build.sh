#!/bin/sh

set -e  # make sure to abort on error
set -x  # echo commands

pyinstaller FontraPakMain.py --windowed -y --collect-all fontra --collect-all fontra_rcjk --name "Fontra Pak"
