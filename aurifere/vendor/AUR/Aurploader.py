#!/usr/bin/env python3

# Copyright (C) 2012-2013 Xyne
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# (version 2) as published by the Free Software Foundation.
#
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

from argparse import ArgumentParser
from getpass import getpass
from glob import glob
from html.parser import HTMLParser
from http.cookiejar import MozillaCookieJar, LoadError
from subprocess import Popen
from tempfile import TemporaryDirectory
from urllib.parse import urlencode, quote
from urllib.request import build_opener, HTTPCookieProcessor, urlopen
import errno
import json
import os
import sys
import urllib.error
import xdg.BaseDirectory

from AUR.RPC import AUR

AUR_URL = 'https://aur.archlinux.org'
INDEX_URL = AUR_URL + '/index.php'
LOGIN_URL = AUR_URL + '/login/'
PKGSUBMIT_URL = AUR_URL + '/pkgsubmit.php'
RPC_URL = AUR_URL + '/rpc.php'

PACKAGE_ACTIONS = (
  'flag',
  'unflag',
  'vote',
  'unvote',
  'notify',
  'unnotify',
)


def get_default_cookiejar_path():
  """
  Get the default path to the cookie jar.
  """
  cache_dir = xdg.BaseDirectory.save_cache_path('AUR')
  return os.path.join(cache_dir, 'cookiejar.txt')



def load_login_file(fpath):
  """
  Load login name and password from file.
  """
  with open(fpath) as f:
    name = f.readline().rstrip('\n')
    passwd = f.readline().rstrip('\n')
  return name, passwd



class AurploaderError(Exception):
  """
  Exceptions raised by AUR interactions and related functions.
  """
  def __init__(self, msg):
    self.msg = msg

  def __str__(self):
    return self.msg



def prompt_comment(pkginfo):
  """
  Prompt the user for a comment.

  The EDITOR environment variable must be set.
  """
  editor = os.getenv('EDITOR')
  if not editor:
    raise AurploaderError('environment variable "EDITOR" is not set')
  if os.path.isdir('/dev/shm'):
    dpath = '/dev/shm'
  else:
    dpath = None
  with TemporaryDirectory(dir=dpath) as d:
    fpath = os.path.join(d, pkginfo['Name'])
    marker = '###>'
    header = (
      'Enter a comment for {}'.format(pkginfo['Name']),
      'Webpage: {}/packages.php?ID={!s}'.format(AUR_URL, pkginfo['ID']),
      'Lines beginning with "{}" are ignored.'.format(marker),
      'If the rest of the file is empty, no comment will be submitted.',
    )
    with open(fpath, 'w') as f:
      for line in header:
        f.write('{} {}\n'.format(marker, line))
    p = Popen([editor, fpath])
    p.wait()
    comment = ''
    with open(fpath) as f:
      for line in f:
        if line.startswith(marker):
          continue
        comment += line
    return comment.strip()






class pkgsubmitParser(HTMLParser):
  """
  Parser for the pkgsubmit.php page.

  Hidden submit fields such as the token as well as the package categories
  will be retrieved.
  """
  def __init__(self):
    super(self.__class__, self).__init__()
    self.parse_options = False
    self.number = 0
    self.categories = dict()
    self.token = None

  def handle_starttag(self, tag, attrs):
    # Get the hidden token value.
    if tag == 'input':
      a = dict(attrs)
      if a['type'] == 'hidden' and a['name'] == 'token' and a['value']:
        self.token = a['value']

    # Determine package categories from the "select" list.
    elif tag == 'select':
      if ('name', 'category') in attrs:
        self.parse_options = True

    elif self.parse_options and tag == 'option':
      for name, val in attrs:
        if name == 'value':
          self.number = int(val)
          break

  def handle_data(self, data):
    if self.number > 1:
      self.categories[self.number] = data
      self.number = 0



class Aurploader(object):
  """
  A user object for interactive actions.
  """

  def __init__(
    self,
    cookiejar_path=None,
    cookiejar=None,
    token=None,
    categories=None
  ):
    """
    cookiejar: a MozillaCookieJar object

    token: a user token for submitting form data

    categories: package categories
    """

    if cookiejar_path is None:
      cookiejar_path = get_default_cookiejar_path()
    self.cookiejar_path = cookiejar_path

    if cookiejar is None:
      self.cookiejar = MozillaCookieJar()
      self.load_cookies()
    else:
      self.cookiejar = cookiejar

    # TODO
    # Find way to use this with URL opener. (urlopen accepts a capath arg)
    # CA_PATH = '/etc/ssl/certs'
    self.opener = build_opener(HTTPCookieProcessor(self.cookiejar))
    self.token = token
    self.categories = categories

#     self.rpc = AUR(ttl=0, clean=False)
    self.rpc = AUR()



  def get_info(self, pkgname):
    """
    Get package information from the RPC interface.
    """
    for pkg in self.rpc.info(pkgname):
      return pkg


  def parse_pkgsubmit(self):
    """
    Parse the pkgsubmit page.

    This will return package categories along with hidden inputs such as the
    the token. If the returned values are empty then the user is not currently
    logged in, so it doubles as a login check.
    """
    parser = pkgsubmitParser()
    with self.opener.open(PKGSUBMIT_URL) as f:
      parser.feed(f.read().decode())
    if parser.token:
      self.token = parser.token
    self.categories = parser.categories



  def login(self, user=None, passwd=None, login_file=None, remember_me=True):
    """
    Log in to the AUR.
    """
    if login_file is not None:
      user, passwd = load_login_file(login_file)

    if user is None or passwd is None:
      self.rpc.log("logging in to the AUR")

    if user is None:
      user = input('Username: ')

    if passwd is None:
      passwd = getpass()

    data = [
      ('user', user),
      ('passwd', passwd)
    ]

    if remember_me:
      data.append(('remember_me', '1'))

    data = urlencode(data).encode('UTF-8')

    with self.opener.open(LOGIN_URL, data) as f:
      pass



  # python3-AUR could be used to cache the data, but sometimes the data must be
  # fresh, such as when confirming the upload.
  def submit_package_form(
    self, pkginfo, action,
    confirm_delete=False, merge_into=None, comment=None, category=None,
  ):
    """
    Submit a form to the AUR.
    """
    ID = pkginfo['ID']
    url = AUR_URL + '/packages/{}/'.format(pkginfo['Name'])
    # Old form actions, converted to links with AUR 2.0
    do_actions = {
  #     'do_Vote'     : 'Vote',
  #     'do_UnVote'   : 'UnVote',
  #     'do_Notify'   : 'Notify',
  #     'do_UnNotify' : 'UnNotify',
  #     'do_Flag'     : 'Flag Out-of-date',
      'do_Disown'   : 'Disown Packages',
      'do_Delete'   : 'Delete Packages',
      'do_Adopt'    : 'Adopt Packages',
    }
    if action in do_actions:
      url = AUR_URL + '/packages/'
      data = [
        ('IDs[{!s}]'.format(ID), '1'),
        ('ID', ID),
        ('token', self.token),
        (action, do_actions[action])
      ]
      if confirm_delete:
        data.append(('confirm_Delete', '1'))
      if merge_into:
        data.append(('merge_Into', merge_into))

    elif action == 'comment':
      if comment:
        data = (
          ('ID', ID),
          ('token', self.token),
          ('comment', comment)
        )
      else:
        raise AurploaderError("no comment submitted")

    elif action == 'do_ChangeCategory':
      if category:
        data = (
          ('action', 'do_ChangeCategory'),
          ('category_id', category),
          ('token', self.token)
        )
      else:
        raise AurploaderError("no category submitted for do_ChangeCategory")

    elif action == 'do_DeleteComment':
      if category:
        data = (
          ('action', 'do_DeleteComment'),
          ('comment_id', comment_id),
          ('token', self.token),
          ('submit', '1')
        )
      else:
        raise AurploaderError("no category submitted for do_ChangeCategory")


    data = urlencode(data).encode('UTF-8')
    with self.opener.open(url, data) as f:
      pass



  def do_package_action(self, pkginfo, action):
    """
    Perform one of the link-based package actions.

    Use submit_package_form() for form-based actions.
    """
    actions = PACKAGE_ACTIONS

    if action in actions:
      url = AUR_URL + '/packages/{}/{}'.format(pkginfo['Name'], action)
      with self.opener.open(url) as f:
        pass
    else:
      raise AurploaderError("unrecognized action ({})".format(action)
      )


  def prompt_categories(self, name, default_category=None):
    """
    Prompt the user to select a category for the given package.
    """
    if not self.categories:
      raise AurploaderError("no categories")
    if default_category not in self.categories:
      default_category = None
    while True:
      print('Select category for {}'.format(name))
      for n in sorted(self.categories):
        print('  {:2d}) {}'.format(n, self.categories[n]))
      print('Enter "x" to skip this package.')
      if default_category:
        category = input('Category [{}]: '.format(default_category))
      else:
        category = input('Category: ')
      if category.lower() == 'x':
        return None
      elif not category and default_category:
        return default_category
      else:
        try:
          category = int(category)
          if category in self.categories:
            return category
        except ValueError:
          continue



  # Python has had an open request for multipart/form-data since 2008-06-30
  # http://bugs.python.org/issue3244

  # At the time of writing, the latest submitted code does not work and hacking
  # together something that does is just not worth it right now.
  def upload_pkg(self, fpath, category=None, auto_category=False, confirm=True):
    """
    Upload a package to the AUR.
    """
    fname = os.path.basename(fpath)
    pkginfo = None

    try:
      pkg, ext = fname.split('.src.', 1)
      name, ver, rel = pkg.rsplit('-', 2)
    except ValueError:
      raise AurploaderError('unexpected filename format: {}\nexpected <pkgname>-<pkgver>-<pkgrel>.src.<ext>'.format(fname))

    if category not in self.categories:
      category = None
    if category is None:
      pkginfo = self.get_info(name)
      if pkginfo:
        category = int(pkginfo['CategoryID'])

    if category is None or not auto_category:
      category = self.prompt_categories(name, default_category=category)

    # This is not an error. A user may abort the upload by entering "x" at the
    # category prompt.
    if category is None:
      return

    cmd = [
      '/usr/bin/curl',
      '-#',
      '-H', 'Expect:',
      '-b', self.cookiejar_path,
      '-c', self.cookiejar_path,
      '-F', 'category={}'.format(category),
      '-F', 'pfile=@{}'.format(fpath),
      '-F', 'pkgsubmit=1',
      '-F', 'token={}'.format(self.token)
    ]

    cmd.append(PKGSUBMIT_URL)

    self.save_cookies()

    with open(os.devnull, 'w') as null:
      p = Popen(cmd, stdout=null)
      e = p.wait()
      if e != 0:
        raise AurploaderError("curl exited with non-zero status ({:d})".format(e))

    self.load_cookies()

    if confirm:
      expected = '{}-{}'.format(ver, rel)
      ttl = self.rpc.ttl
      self.rpc.ttl = 0
      try:
        pkginfo = self.get_info(name)
      finally:
        self.rpc.ttl = ttl
      if not pkginfo or pkginfo['Version'] != expected:
        raise AurploaderError('failed to confirm upload')

    return pkginfo



  def save_cookies(self, path=None):
    """
    Save cookie jar.
    """
    if path is None:
      path = self.cookiejar_path
    if path is None:
      raise AurploaderError('no cookiejar path given')
    # For Curl compatibility (not sure which one fails to comply with the standard.
    for cookie in self.cookiejar:
      if not cookie.expires:
        cookie.expires = 0
    self.cookiejar.save(path, ignore_discard=True, ignore_expires=True)


  def load_cookies(self, path=None):
    """
    Load cookie jar.
    """
    if path is None:
      path = self.cookiejar_path
    if path is None:
      raise AurploaderError('no cookiejar path given')
    try:
      # For Curl compatibility (not sure which one fails to comply with the standard.
      self.cookiejar.load(path, ignore_discard=True, ignore_expires=True)
      for cookie in self.cookiejar:
        if not cookie.expires:
          cookie.expires = None
    except LoadError:
      pass
    except IOError as e:
      if e.errno != errno.ENOENT:
        raise e



  def initialize(self, user=None, passwd=None, login_file=None, cookiejar_path=None):
    """
    Login if necessary and load categories and token.
    """
    self.load_cookies(cookiejar_path)
    self.parse_pkgsubmit()
    if not self.categories or not self.token:
      self.login(user=user, passwd=passwd, login_file=login_file)
      self.parse_pkgsubmit()
      if not self.categories or not self.token:
        raise AurploaderError('login appears to have failed\n')
      elif cookiejar_path:
        self.save_cookies(cookiejar_path)







class CookieWrapper(object):
  ACTIONS = ('ask', 'keep', 'remove')

  def __init__(self, path=None, action='ask', login_file=None):
    self.action = action
    self.login_file=login_file
    self.aurploader = Aurploader(cookiejar_path=path)


  def __enter__(self):
    """
    Cookie context manager.
    """
    self.aurploader.initialize(login_file=self.login_file)
    return self.aurploader



  def __exit__(self, typ, value, traceback):
    """
    Cookie context manager.
    """
    action = self.action
    path = self.aurploader.cookiejar_path
    if action == 'remove':
      try:
        os.unlink(path)
      except OSError as e:
        if e.errno != errno.ENOENT:
          raise e
    elif action == 'keep':
      self.aurploader.save_cookies()
    elif os.path.exists(path):
      cookie_prompts = (
        'Keep cookie jar? [y/n]',
        'Invalid response. Would you like to keep the cookie jar? [y/n]',
        'Please enter "y" or "n". Would you like to keep the cookie jar? [y/n]',
        'Wtf is wrong with you? Just press "y" or "n". I don\'t even care about the case.',
        'I am not going to ask you again. Do you want to keep the cookie jar or what?'
      )
      for prompt in cookie_prompts:
        ans = input(prompt + ' ').lower()
        if ans == 'y' or ans == 'n':
          break
      else:
        print('Ok, that\'s it, @#$^ your cookies! Have fun logging in again!')
      if ans == 'n':
        os.unlink(path)



def parse_args(args=None):
  parser = ArgumentParser(description='Upload packages to the AUR.')
  parser.add_argument(
    'paths', metavar='<path>', nargs='*',
    help='Arguments are either paths to source archives created with "makepkg --source", or to directories containing such source archives. Simple pattern matching is used to search for "*.src.*". If no paths are given then the current directory is searched.'
  )
  parser.add_argument(
    '-a', '--auto', action='store_true',
    help='Skip the category prompt when a previous category is detected.'
  )
  parser.add_argument(
    '-c', '--cookiejar', metavar='<path>',
    help='Specify the path of the cookie jar. The file follows the Netscape format.'
  )
  parser.add_argument(
    '--comment', action='store_true',
    help='Prompt for a comment for each uploaded package. This option requires that the EDITOR environment variable be set.'
  )
  parser.add_argument(
    '-k', '--keep-cookiejar', dest='keep', action='store_true',
    help='Keep the cookie jar.'
  )
  parser.add_argument(
    '-l', '--login', metavar='<path>',
    help='Read name and password from a file. The first line should contain the name and the second the password.'
  )
  parser.add_argument(
    '-m', '--message', metavar='<message>',
    help='Post a message as a comment. The same message will be used for all packages. Use the --comment option to set per-package comments when uploading multiple packages..'
  )
  parser.add_argument(
    '-n', '--notify', action='store_true',
    help='Receive notifications for each uploaded package.'
  )
  parser.add_argument(
    '-r', '--remove-cookiejar', dest='remove', action='store_true',
    help='Remove the cookie jar.'
  )
  parser.add_argument(
    '-v', '--vote', action='store_true',
    help='Vote for each uploaded package.'
  )
  return parser.parse_args()








def main(args=None):
  args = parse_args(args)

  # Search current directory for source archives if none were specified. This
  # allows e.g. "makepkg --source; aurploader" without explicit arguments.
  if not args.paths:
    pkgs = glob('*.src.*')
  else:
    pkgs = []
    for path in args.paths:
      if os.path.isdir(path):
        ps = glob(os.path.join(path, '*.src.*'))
        if ps:
          pkgs.extend(ps)
        else:
          raise AurploaderError('no source package found in directory ({})'.format(path))
      else:
        pkgs.append(path)

  if args.remove:
    action = 'remove'
  elif args.keep:
    action = 'keep'
  else:
    action = 'ask'

  with CookieWrapper(path=args.cookiejar, action=action, login_file=args.login) as aurploader:
    for pkg in pkgs:
      print('Uploading {}'.format(pkg))
      pkginfo = aurploader.upload_pkg(pkg, auto_category=args.auto, confirm=True)
      if pkginfo:
        if args.vote:
          aurploader.do_package_action(pkginfo, 'vote')
        if args.notify:
          aurploader.do_package_action(pkginfo, 'notify')
        comment = None
        if args.comment:
          comment = prompt_comment(pkginfo)
        elif args.message:
          comment = args.message
        if comment:
          aurploader.submit_package_form(pkginfo, 'comment', comment=comment)
      print()



def run_main(args=None):
  """
  Run main() with exception handling.
  """
  try:
    main(args)
  except (KeyboardInterrupt, BrokenPipeError):
    pass
  except AurploaderError as e:
    sys.stderr.write('error: {}\n'.format(e.msg))
    sys.exit(1)
  except urllib.error.URLError as e:
    sys.stderr.write('URLError: {}\n'.format(e))
    sys.exit(1)


if __name__ == '__main__':
  run_main()
