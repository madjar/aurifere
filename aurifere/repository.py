import os
import logging
import shelve
from contextlib import closing
from XyneXDG.BaseDirectory import get_data_home
import atexit
from .aur import AurPackage, NotInAURException
from .package import Package

logger = logging.getLogger(__name__)


class PackageNotInRepositoryException(Exception):
    pass


class Repository:
    def __init__(self, dir):
        self.dir = dir
        if not os.path.isdir(self.dir):
            os.mkdir(self.dir)

        self._open_packages = {}
        self.db = shelve.open(os.path.join(self.dir, 'types.db'))
        atexit.register(self.db.close)

    def __repr__(self):
        return '<Repository("{}")>'.format(self.dir)

    def package(self, name, type="default"):
        if name not in self._open_packages:
            if name in self.db:
                type = self.db[name]
            if type == "aur":
                package = AurPackage(name, self)
            elif type == "manual":
                package = Package(name, self)
            elif type == "default":
                try:
                    package = AurPackage(name, self)
                    type = "aur"
                except NotInAURException as e:
                    raise PackageNotInRepositoryException() from e
            else:
                raise ValueError("Unsupported value for argument type",
                                 type)
            logger.debug('Creating a Package object of type %s', type)
            self.db[name] = type
            self._open_packages[name] = package
        return self._open_packages[name]


def default_repository():
    return Repository(os.path.join(get_data_home(), 'aurifere'))
