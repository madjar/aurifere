import os
import unittest
import tempfile
from aurifere.repository import Repository
from aurifere.package import Package

class RepoTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.chmod(self.dir.name, 0o755)  # That's the expected mode
        self.repo = Repository(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_tag_exotic_version(self):
        package = Package('testpkg', self.repo)
        package._git.tag('1:2.4.7')
