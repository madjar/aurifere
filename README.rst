Aurifere
========

Aurifere is an AUR wrapper for lazy people.

Lazy people like me tend to spend less and less time reviewing the packages they install from AUR, which is wrong, because one should always be cautious before running code from the internet on a computer.

With Aurifere, installing packages from AUR is not a pain in the neck any more :

* Aurifere shows you a diff between the last version you installed and the new one ;
* Aurifere enable you to review all the packages at once, and then install them all without bothering you any more.

Installing
----------

.. Aurifere is on AUR ! Just install aurifere__ the usual way.

There is no stable release of Aurifere yet, but if you are feeling adventurous, install `aurifere-git`__ from AUR.

__ http://aur.archlinux.org/packages.php?ID=56754


Usage
-----

Aurifere is quite simple to use.

::

	aurifere install pkgname

Install one or many packages, including their dependencies

::

	aurifere update

Updates all the packages installed from AUR on your system.


Aurifere is only a AUR wrapper and can't replace pacman. What I do is using yaourt to the usual way, and start aurifere when yaourt tells me there is some update.


Explaination
------------

Aurifere creates a git repository for each package, and commit each version downloaded from AUR. This way, we get a free diff !

It may seem overkill to use git, but I aim to support automatic patching of new versions (like when you want to add a compile flag each time you update a package).

I also have a long-term vision of a git-based AUR where creating updated PKGBUILD and variants would be as easy as forking and merging is on github.

Hacking
-------

If you want to hack on Aurifere, clone this repository and do ::

	pip install -e .

That will install an ``aurifere`` command in your ``~/.local/bin`` that points to you clone.

Bug reports and pull requests welcomed !
