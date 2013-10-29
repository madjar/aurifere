import os
import unittest
import tempfile
from aurifere.repository import Repository


class RepoTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.chmod(self.dir.name, 0o755)  # That's the expected mode
        self.repo = Repository(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_tag_exotic_version(self):
        package = self.repo.package('testpkg', type='manual')
        package._git.tag('1:2.4.7')

    def test_some_aur_package(self):
        package = self.repo.package('aurifere-git')
        self.assertEqual(package.pkgbuild()['name'], 'aurifere-git')
        self.assertEqual(package.version(), package.provider.upstream_version())
