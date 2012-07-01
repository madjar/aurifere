import logging
import os
import subprocess
from aurifere.pacman import installed
from aurifere.pkgbuild import version_is_greater
from .git import Git
from .pkgbuild import PKGBUILD


logger = logging.getLogger(__name__)


class NoPKGBUILDException(Exception):
    pass


class WorkingDirNotCleanException(Exception):
    pass


class NotReviewedException(Exception):
    pass


class Package:
    def __init__(self, name, repository):
        self.name = name
        self._repository = repository
        self.dir = os.path.join(repository.dir, name)
        self._git = Git(self.dir)
        self._pkgbuild = None

        if not os.path.exists(self.dir):
            self._git.init()
            self._git._git('branch', 'upstream')
            self._git.tag('reviewed')
            self._git.tag('empty')

        # To avoid losing anything, we refuse to work on unclean working dir
        modified_files = self._git.status()
        if modified_files:
            raise WorkingDirNotCleanException(self.name, modified_files)

        if not os.path.exists(os.path.join(self.dir, "PKGBUILD")):
            self.update_from_upstream()
            self.apply_modifications()

    def __repr__(self):
        return '<{}("{}")>'.format(type(self).__name__, self.name)

    def pkgbuild(self):
        """Returns a PKGBUILD object for this package."""
        # TODO change the way the cache is handled, because of the multiple branches
        if not self._pkgbuild:
            pkgbuild_path = os.path.join(self.dir, 'PKGBUILD')
            if not os.path.exists(pkgbuild_path):
                raise NoPKGBUILDException(self.name, pkgbuild_path)
            self._pkgbuild = PKGBUILD(pkgbuild_path)
        return self._pkgbuild

    def version(self):
        """Returns the version of the package in the repository."""
        return self.pkgbuild().version()

    def upstream_version(self):
        return None

    def upgrade_available(self):
        pkg = installed(self.name)
        upstream_version = self.upstream_version()
        return (pkg and upstream_version and
                version_is_greater(upstream_version, pkg.version))

    def update_from_upstream(self):
        self._git.switch_branch('upstream')
        new_version = self._fetch_upstream()
        if new_version:
            self._git.commit_all(new_version)
            self._git.tag(new_version)
        self._git.switch_branch('master')

    def _fetch_upstream(self):
        """Fetches the package from upstream.
        Returns the version number if there's a new version."""
        pass

    def apply_modifications(self):
        # TODO merge modifications
        self._git._git('reset', '--hard', 'upstream', '--quiet')

    def review_needed(self):
        return self._git.ref('reviewed') != self._git.ref('master')

    def validate_review(self):
        self._git.tag('reviewed', force=True)

    # TODO : methods to help the review

    def build_and_install(self):
        if self.review_needed():
            raise NotReviewedException()

        try:
            subprocess.check_call(['makepkg', '--clean', '--syncdeps', '--install',
                               '--noconfirm'],
            cwd=self.dir)
        finally:
            self._git.clean()

            if self._git.status():
                logger.warn('Package %s had to be cleaned after build. '+
                    'This is probably a devel package. This will be handled'+
                    'in a future version', self.name)
                self._git._git('reset', '--hard', '--quiet')

    def mark_as_dependency(self):
        subprocess.check_call(['sudo', 'pacman', '--database', '--asdeps',
                               self.name])
