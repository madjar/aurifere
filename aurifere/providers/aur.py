import logging
import tempfile
import urllib.request
import tarfile
import os
import os.path
import shutil
import atexit
from aurifere.vendor import AUR
from aurifere.common import DATA_DIR
from aurifere.pacman import get_satisfier_in_syncdb
from aurifere.package import NoPKGBUILDException


NOT_IN_AUR_FILENAME = os.path.join(DATA_DIR, 'not_in_aur')
logger = logging.getLogger(__name__)


class _LoggingAUR(AUR.AUR):
    """Subclass of ``AUR.AUR`` with proper logging and not_in_aur caching"""

    logger = logging.getLogger("python3-aur")

    def log(self, msg):
        self.logger.debug(msg)

    def __init__(self):
        super().__init__()
        if os.path.exists(NOT_IN_AUR_FILENAME):
            with open(NOT_IN_AUR_FILENAME) as f:
                self.not_in_aur = set(f.read().split())
        else:
            self.not_in_aur = set()

    def close_cache(self):
        with open(NOT_IN_AUR_FILENAME, 'w') as f:
            f.write('\n'.join(self.not_in_aur))

    def info(self, pkgs):
        if isinstance(pkgs, str):
            pkgs = [pkgs]

        pkgs = {pkg for pkg in pkgs if pkg not in self.not_in_aur}
        result = super().info(pkgs)
        if result:
            for r in result:
                pkgs.remove(r['Name'])

        self.not_in_aur.update(pkgs)
        return result


_aur_object = None


def aur_info(pkgs):
    """Return the AUR information for given packages.
    Initialize the AUR.AUR object if needed."""
    global _aur_object
    if not _aur_object:
        _aur_object = _LoggingAUR()
        atexit.register(_aur_object.close_cache)
    return _aur_object.info(pkgs)


def load_aur_cache(pkgs):
    """Loads all the given packages' AUR info into the cache"""
    aur_info(pkgs)


class NotInAURException(Exception):
    """Raised when the given package is not in AUR."""
    pass


class AurProvider:
    """Represents an AUR package and handles the download."""
    def __init__(self, name, dir):
        if get_satisfier_in_syncdb(name):
            # package in the syncdb, so not in AUR
            raise NotInAURException(name)

        aur_info_result = aur_info(name)
        if not aur_info_result:
            raise NotInAURException(name)
        self.aur_info = aur_info_result[0]
        self.name = name
        self.dir = dir

    def upstream_version(self):
        """Returns the version of the package in AUR."""
        return self.aur_info['Version']

    def _download(self):
        """Downloads and extract the last version of the package from AUR."""
        logger.debug("Downloading package %s", self.name)
        url = self.aur_info['URLPath']

        tarfilename, _ = urllib.request.urlretrieve('http://aur.archlinux.org/'
            + url)

        with tarfile.open(tarfilename) as tar:
            if self.name not in tar.getnames():
                # Probably a split package, like python2-prettytable
                # The tar does not have the usual form, so we extract is somewhere
                # else, then copy the content to the right directory
                with tempfile.TemporaryDirectory() as tmpdir:
                    tar.extractall(tmpdir)
                    tardirs = os.listdir(tmpdir)
                    assert len(tardirs) == 1, 'The tar contained more than one directory'
                    tmppkgdir = os.path.join(tmpdir, tardirs[0])
                    shutil.move(os.path.join(self.dir, '.git'),
                                tmppkgdir)
                    shutil.rmtree(self.dir)
                    shutil.move(tmppkgdir, self.dir)
            else:
                # Extract to the parent dir because the tar contains a
                # dir with the right name
                tar.extractall(os.path.dirname(self.dir))

    def _purge(self):
        """Deletes all files and dirs except .git"""
        files_to_delete = os.listdir(self.dir)
        files_to_delete.remove('.git')
        for filename in files_to_delete:
            filename = os.path.join(self.dir, filename)
            if os.path.isfile(filename):
                os.remove(filename)
            else:
                shutil.rmtree(filename)

    def fetch_upstream(self):
        """Updates the package."""
        self._purge()
        self._download()
        self._pkgbuild = None  # Invalidate the cache
