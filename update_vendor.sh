#!/bin/sh

cd aurifere/vendor

# python3-aur
curl  $(curl http://xyne.archlinux.ca/projects/python3-aur/pkgbuild/PKGBUILD |grep tar.xz |grep -v sig) | tar xJv
mv python3-aur*/AUR/ .
rm -rf python3-aur*

# docopt
wget https://raw.github.com/docopt/docopt/master/docopt.py -O docopt.py

# colorama
curl $(curl https://pypi.python.org/pypi/colorama | grep -Eo "https:\/\/.*gz#") | tar xzv
mv colorama-*/colorama .
rm -rf colorama-*
