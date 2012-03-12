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


class VersionCompareTest(unittest.TestCase):
    def _get_FUT(self):
        from aurifere.pkgbuild import version_is_greater
        return version_is_greater

    def test_classic_dotted_version_equals(self):
        self.assertFalse(self._get_FUT()('2.12.4-5', '2.12.4-5'))

    def test_classic_dotted_version_greater(self):
        self.assertTrue(self._get_FUT()('2.0.2-1', '2.0.1-2'))

    def test_classic_dotted_version_lesser(self):
        self.assertFalse(self._get_FUT()('2.0.1-2', '2.0.2-1'))

    def test_ugly_version_numbers(self):
        self.assertTrue(self._get_FUT()('1.0.27.206_r0-1', '1.0.27.206-1'))
