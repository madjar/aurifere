"""PKGBUILD parsing"""
import hashlib
import os
import shelve
import subprocess
import ast
import logging
import itertools
import atexit
from aurifere.common import DATA_DIR


logger = logging.getLogger(__name__)


_pkgbuild_cache = shelve.open(os.path.join(DATA_DIR, 'pkgbuild_cache.db'))
atexit.register(_pkgbuild_cache.close)


class PKGBUILD:
    """PKGBUILD parser."""
    def __init__(self, path):
        self.path = path
        self._parse()

    def _parse(self):
        """Parses the PKGBUILD file."""
        # Parsing code stolen and adapted from https://github.com/sebnow/aur2/

        h = hashlib.md5(open(self.path, 'rb').read()).hexdigest()
        if h in _pkgbuild_cache:
            self.content = _pkgbuild_cache[h]
            return

        logger.debug('Parsing %s', self.path)
        script_dir = os.path.abspath(os.path.dirname(__file__))
        output = subprocess.check_output([os.path.join(script_dir,
                                                       'parsepkgbuild.sh'),
                                          'PKGBUILD'],
            cwd=os.path.dirname(self.path))

        self.content = ast.literal_eval(output.decode())

        _pkgbuild_cache[h] = self.content

    def __getitem__(self, key):
        return self.content.__getitem__(key)

    def version(self):
        """Returns the version of the package in the PKGBUILD."""
        return '{}-{}'.format(self['version'], self['release'])

    def all_depends(self):
        """Returns a list of all the packages needed to build the PKGBUILD."""
        # TODO : sale
        for dep in itertools.chain(self['depends'], self['makedepends']):
            yield dep.translate({60: '=', 62: '='}).split('=')[0]


def try_int(x):
    try:
        return int(x)
    except ValueError:
        return x

def version_is_greater(v1, v2):
    major1, minor1 = v1.split('-')
    major2, minor2 = v2.split('-')
    vtuple1 = tuple(map(try_int, major1.split('.')))
    vtuple2 = tuple(map(try_int, major2.split('.')))
    if vtuple1 > vtuple2:
        return True
    elif  vtuple1 < vtuple2:
        return False
    else:
        if minor1 > minor2:
            return True
        else:
            return False

