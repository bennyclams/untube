#!/bin/bash

# This is used to patch pytube until an official fix is released
mkdir /tmp/patch
cd /tmp/patch
cp $(pip3 show pytube | grep Location: | cut -d ' ' -f2)/pytube/cipher.py .
cp /app/patch.py .
python3 patch.py
cp cipher.py $(pip3 show pytube | grep Location: | cut -d ' ' -f2)/pytube/cipher.py