#!/bin/sh

set -e  # make sure to abort on error
set -x  # echo commands

icon=$1

pyinstaller FontraPakMain.py \
	--windowed \
	-y \
	--collect-all fontra \
	--collect-all fontra_rcjk \
	--name "Fontra Pak" \
	--osx-bundle-identifier xyz.fontra.fontra-pak \
	--icon $icon
