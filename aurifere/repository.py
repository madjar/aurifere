import os
import logging
import shelve
from .aur import AurPackage, NotInAURException
from .common import DATA_DIR
from .package import Package

logger = logging.getLogger(__name__)


class PackageNotInRepositoryException(Exception):
    pass


class Repository:
    def __init__(self, dir):
        self.dir = dir
        os.makedirs(self.dir, exist_ok=True)

        self._open_packages = {}
        self.db = shelve.open(os.path.join(self.dir, 'types.db'))

    def __del__(self):
        self.db.close()

    def __repr__(self):
        return '<Repository("{}")>'.format(self.dir)

    def package(self, name, type="default"):
        if name not in self._open_packages:
            if name in self.db:
                type = self.db[name]
            if type == "aur":
                try:
                    package = AurPackage(name, self)
                except NotInAURException:
                    package = Package(name, self)
                    logger.warn('Package %s used to be in AUR but is not any '
                                'more. You may want to find an alternative. '
                                'To remove this message, delete the folder %s .'
                        %(name, package.dir))
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
            logger.debug('Adding %s of type %s to the repository', name, type)
            self.db[name] = type
            self._open_packages[name] = package
        return self._open_packages[name]
#TODO : treat dev packages separately

def default_repository():
    return Repository(DATA_DIR)
