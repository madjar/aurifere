"""Aurifere

Usage:
  aurifere [-v] install <package>...
  aurifere [-v] update

Options:
  -h --help     Show this screen.
  -v --verbose

"""
from docopt import docopt
import colorama
from .install import Install
from .repository import default_repository


def comma_separated_package_list(pkgs):
    return ', '.join(hl(p.name) for p in pkgs)


def hl(text):
    return colorama.Style.BRIGHT + text + colorama.Style.RESET_ALL


def review_package(install, package):
    print('Reviewing {} {}. Last reviewed version was {}'.format(
        hl(package.name),
        hl(package.version()),
        hl(package._git.tag_for_ref('reviewed'))
    ))
    if package in install.dependencies:
        print('This package is required by {}'
        .format(comma_separated_package_list(install.dependencies[package])))
    input('About to show diff ...')
    package._git._git('diff', 'reviewed', '--color')
    if argh.confirm('Validate review for {} '.format(hl(package.name)),
                    default=True):
        package.validate_review()
    else:
        # TODO : maybe we can be a little more diplomatic
        print("Too bad, I'm gonna crash !")


def review_and_install(installer):
    if not installer.to_install:
        print('Nothing to do')
        return

    installer.fetch_all()

    pacman_dependencies = installer.pacman_dependencies()
    packages_to_review = installer.packages_to_review()

    print('Packages to build and install : {}'
    .format(comma_separated_package_list(installer.to_install)))

    if pacman_dependencies:
        print('Packages installed from pacman as dependencies :')
        for package, from_ in pacman_dependencies.items():
            print('{} from {}'.format(hl(package),
                                      hl(comma_separated_package_list(from_))))

    if packages_to_review:
        print('Packages to review : {}'
        .format(comma_separated_package_list(packages_to_review)))

    if not argh.confirm('Do you confirm', default=True):
        return

    for package in packages_to_review:
        review_package(installer, package)

    installer.install()


def update():
    installer = Install(default_repository())
    installer.update_aur()


def main():
    arguments = docopt(__doc__)

    if arguments['--verbose']:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    installer = Install(default_repository())

    if arguments['install']:
        installer.add_packages(arguments['<package>'])
    if arguments['update']:
        installer.update_aur()

    review_and_install(installer)

if __name__ == '__main__':
    main()
