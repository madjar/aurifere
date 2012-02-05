import plac
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
    package._git._git('diff', 'reviewed')
    if input('Validate review for {}? (y|n) '.format(hl(package.name))) == 'y':
        package.validate_review()
    else:
        # TODO : maybe we can be a little more diplomatic
        print("Too bad, I'm gonna crash !")


def install(*pkgs):
    i = Install(default_repository())
    i.add_packages(pkgs)
    pacman_dependencies = i.pacman_dependencies()
    packages_to_review = i.packages_to_review()

    print('Packages to build and install : {}'
    .format(comma_separated_package_list(i.to_install)))

    if pacman_dependencies:
        print('Packages installed from pacman as dependencies :')
        for package, from_ in pacman_dependencies.items():
            print('{} from {}'.format(hl(package),
                                      hl(comma_separated_package_list(from_))))

    if packages_to_review:
        print('Packages to review : {}'
            .format(comma_separated_package_list(packages_to_review)))

    if input('Do you confirm (y|n)') != 'y':
        return

    i.fetch_all()
    for package in packages_to_review:
        review_package(i, package)

    i.install()


def main():
    plac.call(install)


if __name__ == '__main__':
    main()
