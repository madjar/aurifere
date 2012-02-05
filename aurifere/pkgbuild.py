"""PKGBUILD parsing"""
import os
import subprocess
import ast
import logging
import itertools


logger = logging.getLogger(__name__)


class PKGBUILD:
    """PKGBUILD parser. Very dumb, output may contains nonsense"""
    def __init__(self, path):
        self.path = path
        self._parse()

    def _parse(self):
        """Parses the PKGBUILD file."""
        # Parsing code stolen and adapted from https://github.com/sebnow/aur2/
        logger.debug('Parsing %s', self.path)
        script_dir = os.path.dirname(__file__)
        if not script_dir:
            script_dir = os.path.abspath(script_dir)
        output = subprocess.check_output([os.path.join(script_dir,
                                                       'parsepkgbuild.sh'),
                                          'PKGBUILD'],
            cwd=os.path.dirname(self.path))

        self.content = ast.literal_eval(output.decode())

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
