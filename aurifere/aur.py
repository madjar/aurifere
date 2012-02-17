import logging
import urllib.request
import tarfile
import os
import shutil
import AUR
from .common import DATA_DIR
from .pacman import get_satisfier_in_syncdb
from .package import Package, NoPKGBUILDException


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

    def __del__(self):
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
    return _aur_object.info(pkgs)


def load_aur_cache(pkgs):
    """Loads all the given packages' AUR info into the cache"""
    aur_info(pkgs)


class NotInAURException(Exception):
    """Raised when the given package is not in AUR."""
    pass


class AurPackage(Package):
    """Represents an AUR package and handles the download."""
    def __init__(self, name, repository):
        logger.debug("Checking that the package %s is in AUR", name)

        if get_satisfier_in_syncdb(name):
            # package in the syncdb, so not in AUR
            raise NotInAURException(name)

        aur_info_result = aur_info(name)
        if not aur_info_result:
            raise NotInAURException(name)
        self.aur_info = aur_info_result[0]
        super().__init__(name, repository)

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
            tar.extractall(self._repository.dir)

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

    def _fetch_upstream(self):
        """Updates the package if needed."""
        try:
            version = self.version()
        except NoPKGBUILDException:
            version = None
        aur_version = self.upstream_version()
        if not version or version != aur_version:
            self._purge()
            self._download()
            self._pkgbuild = None  # Invalidate the cache
            return aur_version
        return None
