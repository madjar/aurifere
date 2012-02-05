import os
import unittest

here = os.path.dirname(__file__)


class PkgbuildTest(unittest.TestCase):
    def _get_pkgbuild(self):
        from aurifere.pkgbuild import PKGBUILD
        return PKGBUILD(os.path.join(here, 'fixtures/PKGBUILD'))

    def test_attributes(self):
        p = self._get_pkgbuild()
        self.assertEqual(p['name'], 'pep8')
        self.assertEqual(p['version'], '0.6.1')

    def test_version(self):
        p = self._get_pkgbuild()
        self.assertEqual(p.version(), '0.6.1-3')

    def test_all_depends(self):
        p = self._get_pkgbuild()
        self.assertEqual(list(p.all_depends()),
            ['python2', 'setuptools', 'fakedepend'])
