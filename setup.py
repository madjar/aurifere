from setuptools import setup, find_packages

setup(
    name="aurifere",
    version="0.1",
    description="AUR wrapper for lazy people",
    url="https://github.com/madjar/aurifere",
    author="Georges Dubus",
    author_email="georges.dubus@compiletoi.net",
    license="GPLv3",

    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: GNU General Public License (GPL)",
        "Operating System :: POSIX :: Linux",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Systems Administration",
        ],

    packages=find_packages(),
    include_package_data=True,
    entry_points={'console_scripts': ['aurifere = aurifere.cli:main']}
)
