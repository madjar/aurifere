from collections import defaultdict
from .aur import load_aur_cache
from aurifere.aur import NotInAURException
from aurifere.pacman import get_foreign_packages
from .pacman import installed
from .repository import PackageNotInRepositoryException


class Install:
    def __init__(self, repo):
        self.repo = repo
        self.to_install = []
        self.dependencies = defaultdict(list)
        self._pacman_dependencies = defaultdict(list)

    def _update_deps(self, package):
        for dep in package.pkgbuild().all_depends():
            try:
                dep_pkg = self.repo.package(dep)
                self.add_package(dep_pkg, install_before=True)
                self.dependencies[dep_pkg].append(package)
            except PackageNotInRepositoryException:
                self._pacman_dependencies[package].append(dep)

    def add_package(self, pkg, force=False, install_before=False):
        if not force and installed(pkg.name):
            return
        if not pkg in self.to_install:
            if install_before:
                self.to_install.insert(0, pkg)
            else:
                self.to_install.append(pkg)
            self._update_deps(pkg)

    def add_packages(self, pkgs):
        load_aur_cache(pkgs)
        for pkg in pkgs:
            self.add_package(self.repo.package(pkg), force=True)

    def update_aur(self):
        # TODO report packages not un aur
        pkg_names = get_foreign_packages()
        load_aur_cache(pkg_names)
        for pkg_name in pkg_names:
            try:
                pkg = self.repo.package(pkg_name)
                if pkg.upgrade_available():
                    self.add_package(pkg, force=True)
            except PackageNotInRepositoryException:
                continue

    def fetch_all(self):
        for pkg in self.to_install:
            pkg.update_from_upstream()
            pkg.apply_modifications()

    def packages_to_review(self):
        return [pkg for pkg in self.to_install if pkg.review_needed()]

    def pacman_dependencies(self):
        result = defaultdict(list)
        for package, dependencies in self._pacman_dependencies.items():
            for dep in dependencies:
                if not installed(dep):
                    result[dep].append(package)
        return result

    def install(self):
        for pkg in self.to_install:
            pkg.build_and_install()
