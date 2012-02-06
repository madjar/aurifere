"""Interface to pacman."""
import pyalpm
import pycman.config

handle = pycman.config.init_with_config("/etc/pacman.conf")
db = handle.get_localdb()


def get_package_version(pkg):
    """Returns the version of an installed package."""
    return db.get_pkg(pkg).version


def get_sync_packages():
    """Returns a set containing all the packages in the sync database.
    The result is cached."""
    # TODO cache
    syncpkgs = set()
    for syncdb in handle.get_syncdbs():
        syncpkgs |= set(p.name for p in syncdb.pkgcache)
    return syncpkgs


def get_foreign_packages():
    """Returns all the foreign packages installed on the system (packages not
    available in any sync database)."""
    syncpkgs = get_sync_packages()
    return [p.name for p in db.pkgcache if not p.name in syncpkgs]


def get_satisfier_in_syncdb(pkg):
    """Returns the name of a package satisfying dependency_name"""
#    local_result = pyalpm.find_satisfier(db.pkgcache, pkg)
#    if local_result:
#        return local_result.name
    for syncdb in handle.get_syncdbs():
        result = pyalpm.find_satisfier(syncdb.pkgcache, pkg)
        if result:
            return result.name


def installed(pkg):
    return pyalpm.find_satisfier(db.pkgcache, pkg)
