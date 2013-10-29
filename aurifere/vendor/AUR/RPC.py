#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (C) 2009,2010,2011,2012  Xyne
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# (version 2) as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.


"""
Retrieve data from the AUR via the RPC interface:

  https://aur.archlinux.org/rpc.php

Threads are used to speed up retrieval. Results are cached in an SQLite3
database to avoid redundant queries when practical.
"""

# TODO
# Consider making HTTPS optional. Check if HTTPS verifies certificates.

import argparse
import datetime
import json
import logging
import os
import queue
import sqlite3
import threading
import time
import types
import urllib.parse
import urllib.request
import sys
import xdg.BaseDirectory

DEFAULT_TTL = 15 * 60
TIME_FMT = '%Y-%m-%d %H:%M:%S'


################################################################################
# AUR
################################################################################

AUR_URL = 'https://aur.archlinux.org'
# AUR_URL = 'https://aur-dev.archlinux.org'
RPC_URL = AUR_URL + '/rpc.php'

def insert_full_urls(pkgs):
  """
  Replace partial URLS with full URLS for each passed package.
  """
  if pkgs:
    for pkg in pkgs:
      try:
        pkg['URLPath'] = AUR_URL + pkg['URLPath']
      except KeyError:
        pass
      yield pkg


class AURError(Exception):
  """
  Exception raised by AUR objects.
  """

  def __init__(self, msg, error=None):
    self.msg = msg
    self.error = error


def aur_query(typ, arg):
  """
  Query the AUR RPC interface.
  """
  url = RPC_URL + '?type=' + urllib.parse.quote(typ) + '&arg=' + urllib.parse.quote(arg)
  return _aur_query(typ, url)


def aur_multiquery(typ, args):
  """
  Query the AUR RPC interface.
  """
  url = RPC_URL + '?type=' + urllib.parse.quote(typ)
  for arg in args:
    url += '&arg[]=' + urllib.parse.quote(arg)
  return _aur_query(typ, url)


def _aur_query(typ, url):
  """
  Internal function.
  """
  try:
    with urllib.request.urlopen(url) as f:
      response = json.loads( f.read().decode('utf-8') )
  except urllib.error.HTTPError as e:
    return None, str(e)
  logging.debug(url)
  logging.debug(json.dumps(response, indent='  ', sort_keys=True))
  try:
    rtyp = response['type']
    if rtyp == typ:
      if response['resultcount'] == 0:
        reason = 'no results found'
      else:
        reason = None
      return response['results'], reason
    elif rtyp == 'error':
      return None, "RPC error {}".format(response['results'])
    else:
      return None, "Unexpected RPC return type {}".format(rtyp)
  except KeyError:
    return None, "unexpected RPC error"



def AURRetriever(request_queue, response_queue):
  """
  Worker thread target function for retrieving data from the AUR.
  """

  while True:
    typ, arg = request_queue.get()
    results = aur_query(typ, arg)
    response_queue.put(results)
    request_queue.task_done()



class AUR(object):
  """
  Interact with the Arch Linux User Repository (AUR)

  Data retrieved via the RPC interface is cached temporarily in an SQLite3
  database to avoid unnecessary remote calls.
  """

  INFO_TABLE = ('info', (
    ('Name',           'TEXT'),
    ('Version',        'TEXT'),
    ('Description',    'TEXT'),
    ('URL',            'TEXT'),
    ('URLPath',        'TEXT'),
    ('Maintainer',     'TEXT'),
    ('License',        'TEXT'),
    ('NumVotes',       'INTEGER'),
    ('FirstSubmitted', 'INTEGER'),
    ('LastModified',   'INTEGER'),
    ('OutOfDate',      'INTEGER'),
    ('ID',             'INTEGER'),
    ('CategoryID',     'INTEGER'),
  ))
  SEARCH_TABLE = ('search', (
    ('Query', 'TEXT'),
    ('IDs',   'TEXT'),
  ))
  MSEARCH_TABLE = ('msearch', (
    ('Maintainer', 'TEXT'),
  ))
  TIMESTAMP_COLUMN = ('_timestamp', 'timestamp')

  def __init__(self, database=None, ttl=DEFAULT_TTL, threads=1, clean=True, log_func=None):
    """
    Initialize the AUR object.

    database:
      SQLite3 database path. Use ":memory:" to avoid creating a cache file.
      default: $XDG_CACHE_HOME/AUR/RPC.sqlite3

    ttl:
      Time to live, i.e. how long to cache individual results in the database.

    threads:
      Number of threads to use when retrieving data from the AUR.
      default: 1

    clean:
      Clean the database to remove old entries and ensure integrity.

    log_func:
      A custom log method. It mush accept an instance of AUR and the text message.
    """

    if not database:
      cache_dir = xdg.BaseDirectory.save_cache_path('AUR')
      database = os.path.join(cache_dir, 'RPC.sqlite3')

    try:
      self.conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
    except sqlite3.OperationalError as e:
      if database != ':memory:':
        pdir = os.path.abspath(os.path.dirname(database))
        if not os.path.isdir(pdir):
          os.makedirs(pdir, exist_ok=True)
          self.conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        else:
          self.die('failed to establish database connection [{:s}]'.format())
      else:
        raise e
    self.cursor = self.conn.cursor()
    self.ttl = ttl

    if log_func:
      self.chlog(log_func)

    if clean:
      self.db_clean()
    else:
      self.db_initialize()

    if threads < 1:
      threads = 1
    self.threads = threads

    if self.threads > 1:
      self.threads_initialize()




  ##############################################################################
  # Threading
  ##############################################################################

  # This can probably be removed once the AUR supports multiple arguments per
  # query.

  def threads_initialize(self):
    """
    Initialize AURRetriever threads.
    """

    self.request_queue = queue.Queue()
    self.response_queue = queue.Queue()

    for i in range(self.threads):
      t = threading.Thread(target=AURRetriever, args=(self.request_queue, self.response_queue))
      t.daemon = True
      t.start()



  ##############################################################################
  # Logging Functions
  ##############################################################################
  def log(self, msg):
    """
    Log messages.

    Override this with the chlog method.
    """
    logging.info(msg)

  def chlog(self, func):
    """
    Change the log function.
    """
    self.log = types.MethodType(func, self)

  def warn(self, msg):
    """
    Log warnings.

    Override this with the chwarn method.
    """
    logging.warning(msg)

  def chwarn(self, func):
    """
    Change the warn function.
    """
    self.warn = types.MethodType(func, self)

  def die(self, msg, error=None):
    """
    Log errors and raise an AURError.
    """
    logging.error(msg)
    raise AURError(msg, error)



  ##############################################################################
  # Database Functions
  ##############################################################################

  def db_execute(self, query, args=None):
    """
    Execute the SQL query with optional arguments.
    """
    c = self.cursor
    try:
      if args:
        c.execute(query, args)
        logging.debug(query)
        logging.debug(str(args))
      else:
        c.execute(query)
        logging.debug(query)
      self.conn.commit()
      return c
    except sqlite3.OperationalError as e:
      self.die("sqlite3.OperationalError {:s} (query: {:s})".format(e, query), error=e)



  def db_executemany(self, query, args=[]):
    """
    Execute the SQL query once for each list of arguments.
    """

    c = self.cursor
    try:
      c.executemany(query, args)
      self.conn.commit()
      logging.debug(query)
      for a in args:
        logging.debug(str(a))
      return c
    except sqlite3.OperationalError as e:
      self.die(str(e), error=e)



  def db_initialize(self):
    """
    Initialize the database by creating the info table if necessary.
    """

    for table in self.INFO_TABLE, self.SEARCH_TABLE, self.MSEARCH_TABLE:
      name = table[0]
      primary_col = table[1][0]
      other_cols = table[1][1:]

      query = 'CREATE TABLE IF NOT EXISTS "{}" ('.format(name)
      query += '"{0[0]}" {0[1]} PRIMARY KEY'.format(primary_col)
      for col in other_cols:
        query += ',"{0[0]}" {0[1]}'.format(col)
      query += ',"{0[0]}" {0[1]}'.format(self.TIMESTAMP_COLUMN)
      query += ')'
      self.db_execute(query)



  def db_insert_info(self, pkgs):
    """
    Insert package data into the info table.
    """
    if pkgs:
      table, cols = self.INFO_TABLE
      cols += (self.TIMESTAMP_COLUMN,)
      now = datetime.datetime.utcnow()

      qs = ','.join('?' for x in cols)
      query = 'REPLACE INTO "{}" VALUES ({})'.format(table, qs)
      args = [tuple([pkg[k] for k, t in cols[:-1]]) + (now,) for pkg in pkgs]
      self.db_executemany(query, args)



  def db_insert_msearch(self, maintainers):
    """
    Track msearch times.

    Only the times are tracked because the query results contain package info,
    which is inserted in the info table.
    """
    if maintainers:
      query = 'REPLACE INTO "{}" VALUES (?, ?)'.format(self.MSEARCH_TABLE[0])
      now = datetime.datetime.utcnow()
      args = [(m, now) for m in maintainers]
      self.db_executemany(query, args)



  def db_insert_search(self, args):
    """
    Track search results.

    Only the matching package IDs and times are tracked because the query
    results contain package info, which is inserted in the info table.

    "args" should be a list of tuples, with each tuple containing the search
    term in the first position, and a list of matching package IDs in the second
    position, e.g. [(foo, [343, 565, 23443]), (bar, [93, 445])].
    """
    if args:
      query = 'REPLACE INTO "{}" VALUES (?, ?, ?)'.format(self.SEARCH_TABLE[0])
      now = datetime.datetime.utcnow()
      args = [(term, '\n'.join(map(str, ids)), now) for term, ids in args]
      self.db_executemany(query, args)



  # Clean up the database.
  def db_clean(self):
    """
    Clean up the database.

    This will update the columns of the info table if necessary and purge old
    records.
    """
    try:
      c = self.cursor

      # Format: (table, ((name, type), (name, type), ...))
      for table, expected_cols in (self.INFO_TABLE, self.MSEARCH_TABLE, self.SEARCH_TABLE):
        expected_cols += (self.TIMESTAMP_COLUMN,)

        cols = c.execute('PRAGMA table_info("{}")'.format(table)).fetchall()
        if len(expected_cols) == len(cols):
          for (name, typ), meta in zip(expected_cols, cols):
            if name != meta[1] or typ != meta[2]:
              c.execute('DROP TABLE "{}"'.format(table))
              self.log('dropped {}'.format(table))
              break
          else:
            if self.ttl != None and self.ttl >= 0:
              max_ttl = datetime.timedelta(seconds=self.ttl)
              arg = datetime.datetime.utcnow() - max_ttl
              query = 'DELETE FROM "{}" WHERE {}<?'.format(table, self.TIMESTAMP_COLUMN[0])
              deleted = c.execute(query, (arg,)).rowcount
              if deleted > 1:
                self.log('deleted {:d} rows from {}'.format(deleted, table))
              elif deleted == 1:
                self.log('deleted {:d} row from {}'.format(deleted, table))
        elif cols:
          c.execute('DROP TABLE "{}"'.format(table))
          self.log('dropped {}'.format(table))

      # Make sure any dropped tables are recreated.
      self.db_initialize()
      c.execute('VACUUM')
      self.conn.commit()
    except sqlite3.OperationalError as e:
      self.die( str(e) )



  def db_get_packages(self, query, args):
    """
    Return package information from the database.
    """

    c = self.db_execute(query, args)
    for row in c:
      pkg = {}
      for (name, typ), value in zip(self.INFO_TABLE[1], row):
        if None != value:
          if typ == 'INTEGER':
            pkg[name] = int(value)
          else:
            pkg[name] = value
        else:
          pkg[name] = ''
      yield pkg



  def db_get_matching_packages(self, field, matches, check_time=True):
    """
    Return package information where the field matches one of the arguments.

    Expression tree limits are taken into consideration to split queries when
    necessary.
    """
    for where, args in self.db_get_where_clauses(field, matches, check_time=check_time):
      query = 'SELECT * FROM "{}" WHERE {}'.format(self.INFO_TABLE[0], where)
      for pkg in self.db_get_packages(query, args):
        yield pkg



  def db_get_where_clauses(self, field, matches, check_time=True):
    """
    Return WHERE clauses.

    Expression tree limits are taken into consideration to split queries when
    necessary.

    The results are returned as a generator.
    """

    matches = tuple(matches)
    limit = 998
    while matches:
      ors = ','.join(['?' for x in matches[:limit]])
      where = "{} IN ({})".format(field, ors)
      args = matches[:limit]

      if check_time and self.ttl != None and self.ttl >= 0:
        max_ttl = datetime.timedelta(seconds=self.ttl)
        t = datetime.datetime.utcnow() - max_ttl
        where = '"{}" >= ? AND ({})'.format(self.TIMESTAMP_COLUMN[0], where)
        args = (t,) + args

      yield (where, args)

      matches = matches[limit:]


  ##############################################################################
  # AUR RPC
  ##############################################################################

  def aur_format(self, pkg):
    """
    Format package info fields to expected formats.
    """

    for key, typ in self.INFO_TABLE[1]:
      if typ == 'INTEGER':
        try:
          pkg[key] = int(pkg[key])
        except KeyError:
          pass

#     try:
#       pkg['URLPath'] = AUR_URL + pkg['URLPath']
#     except KeyError:
#       pass

    return pkg



  def aur_query(self, typ, args):
    """
    Query the AUR.

    Results are returned using a generator.
    """
    if not args:
      return

    if isinstance(args, str):
      args = (args, )

    # Ensure unique arguments to avoid redundant queries.
    args = set(args)

    # With the advent of multiinfo, all results will not be lists.
    results = []

    if typ == 'multiinfo' or typ == 'info':
      result, msg = aur_multiquery(typ, args)
      if result:
        results = result
        for r in results:
          try:
            args.remove(r['Name'])
          except KeyError:
            pass
        for a in sorted(args):
          self.warn('{} query ({}): no results'.format(typ, a))
      else:
        for a in sorted(args):
          self.warn('{} query ({}): {}'.format(typ, a, msg))

    elif self.threads > 1 and len(args) > 1:
      for arg in args:
        self.request_queue.put((typ, arg))
      for arg in args:
        result, msg = self.response_queue.get()
        self.response_queue.task_done()
        if msg:
          self.warn('{} query ({}): {}'.format(typ, arg, msg))
        if result:
          results.extend(result)
    else:
      for arg in args:
        # Top-level aur_query.
        result, msg = aur_query(typ, arg)
        if msg:
          self.warn('{} query ({}): {}'.format(typ, arg, msg))
        if result:
          results.extend(result)

    for pkg in results:
      yield self.aur_format(pkg)



  def aur_info(self, pkgnames):
    """
    Query AUR for package information.

    Returns a generator of the matching packages.
    """

    return self.aur_query('multiinfo', pkgnames)



  def aur_msearch(self, maintainers):
    """
    Query AUR for packages information by maintainer.

    Returns a generator of the matching packages.
    """

    return self.aur_query('msearch', maintainers)



  def aur_search(self, what):
    """
    Query the AUR for packages matching the search string.

    Returns a generator of the matching packages.
    """

    return self.aur_query('search', what)


  ##############################################################################
  # Accessibility Methods
  ##############################################################################


  def get(self, typ, args):
    """
    Retrieve data.

    typ: the query type

    args: the query arguments

    Cached data will be returned when practical. The order of the results will
    vary and can not be relied on.
    """

    if not args:
      return None

    try:
      args.__iter__
      if isinstance(args,str):
        args = (args,)
    except AttributeError:
      args = (args,)

    arg_set = set(args)

    if typ == 'info' or typ == 'multiinfo':
      # Check the info tables for the packages first.
      found = set()
      pkgs = []
      for pkg in self.db_get_matching_packages(self.INFO_TABLE[1][0][0], arg_set):
        found.add(pkg['Name'])
        pkgs.append(pkg)

      # Retrieve whatever we didn't find from the server.
      not_found = arg_set - found

      if not_found:
        new = []
        for pkg in self.aur_info(not_found):
          if pkg:
            new.append(pkg)
        self.db_insert_info(new)
        return pkgs + new

      else:
        return pkgs



    elif typ == 'msearch':
      cached_maintainers = set()

      # Check the msearch table to see if msearches have been done previously
      # for the given arguments. If they have then we use the pkg info cached
      # in the info table because it will have been updated with the results
      # from the previous msearch.
      #
      # The package info in the table is only updated when the entry is older
      # than the ttl field. If the msearch entry is still valid then so is the
      # package entry. The maintainer field will therefore be present.
      for where, args in self.db_get_where_clauses(self.MSEARCH_TABLE[1][0][0], arg_set):
        query = 'SELECT * FROM "{}" WHERE {}'.format(self.MSEARCH_TABLE[0], where)
        c = self.db_execute(query, args)

        # If we find it then the cached results are still good.
        for row in c:
          cached_maintainers.add(row[0])

      pkgs = []

      # Retrieve cached pkg info if it's still valid.
      # check_time=False to avoid cases where enough time elapses after checking
      # the msearch table and before checking the info table that the info data
      # would be rejected. Without this, we could end up returning incomplete
      # sets for some maintainers. Of course, this may have changed during
      # the caching interval but that is less likely.
      if cached_maintainers:
        for where, args in self.db_get_where_clauses('Maintainer', cached_maintainers, check_time=False):
          query = 'SELECT * FROM "{}" WHERE {}'.format(self.INFO_TABLE[0], where)

          for pkg in self.db_get_packages(query, args):
            pkgs.append(pkg)

      # Retrieve whatever wasn't cached.
      uncached_maintainers = arg_set - cached_maintainers
      retrieved_pkgs = []
      retrieved_maintainers = set()
      for maintainer in uncached_maintainers:
        results = list(self.aur_msearch(maintainer))
        if results:
          retrieved_pkgs.extend(results)
          retrieved_maintainers.add(maintainer)

      self.db_insert_info(retrieved_pkgs)
      self.db_insert_msearch(retrieved_maintainers)

      return pkgs + retrieved_pkgs



    elif typ == 'search':
      # See msearch comments for explanations.
      cached_queries = set()
      ids = set()
      for where, args in self.db_get_where_clauses(self.SEARCH_TABLE[1][0][0], arg_set):
        query = 'SELECT * FROM "{}" WHERE {}'.format(self.SEARCH_TABLE[0], where)
        c = self.db_execute(query, args)

        for row in c:
          cached_queries.add(row[0])
          ids |= set(row[1].split('\n'))

      pkgs = []

      if ids:
        for where, args in self.db_get_where_clauses('ID', ids, check_time=False):
          query = 'SELECT * FROM "{}" WHERE {}'.format(self.INFO_TABLE[0], where)

          for pkg in self.db_get_packages(query, args):
            pkgs.append(pkg)

      # Retrieve whatever wasn't cached.
      uncached_queries = arg_set - cached_queries
      retrieved_pkgs = []
      # Misnomer, but analogous to msearch function above.
      retrieved_terms = []
      for query in uncached_queries:
        matching_pkgs = list(self.aur_search(query))
        retrieved_terms.append((query, [p['ID'] for p in matching_pkgs]))
        retrieved_pkgs.extend(matching_pkgs)

      self.db_insert_info(retrieved_pkgs)
      self.db_insert_search(retrieved_terms)

      return pkgs + retrieved_pkgs



    else:
      return []


  def info(self, args):
    """
    Retrieve package information.
    """
    return self.get('info', args)


  def msearch(self, args):
    """
    Retrieve package information for specific maintainers.
    """
    return self.get('msearch', args)


  def search(self, args):
    """
    Search for packages.
    """
    return self.get('search', args)



def parse_args(args=None):
  """
  Parse command-line arguments.

  If no arguments are passed then arguments are read from sys.argv.
  """
  parser = argparse.ArgumentParser(description='Query the AUR RPC interface.')
  parser.add_argument(
    'args', metavar='<arg>', nargs='+'
  )
  parser.add_argument(
    '-i', '--info', action='store_true',
    help='query package information'
  )
  parser.add_argument(
    '-m', '--msearch', action='store_true',
    help='query package information by maintainer'
  )
  parser.add_argument(
    '-s', '--search', action='store_true',
    help='search the AUR'
  )
  parser.add_argument(
    '--debug', action='store_true',
    help='enable debugging'
  )
  parser.add_argument(
    '--log', metavar='<path>',
    help='log debugging information to <path>'
  )
  parser.add_argument(
    '--ttl', metavar='<minutes>', type=int, default=(DEFAULT_TTL//60),
    help='time-to-live of cached data (default: %(default)s)'
  )
  return parser.parse_args(args)



def print_query(args, typ='search', aur=None):
  """
  Search the AUR and print matching package information.
  """
  if not aur:
    aur = AUR()
  pkgs = list(aur.get(typ, args))
  pkgs.sort(key=lambda p: p['Name'])

  fields = [name for name, typ in aur.INFO_TABLE[1]]
  fields.insert(3, 'AURPage')

  w = max(map(len, fields)) + 1

#   fmt = '%%-%ds\t%%s' % w
  fmt = '{{:<{:d}s}}\t{{!s:<s}}'.format(w)

  for pkg in pkgs:
    pkg['URLPath'] = AUR_URL + pkg['URLPath']
    pkg['AURPage'] = AUR_URL + '/packages.php?ID={:d}'.format(pkg['ID'])
    if pkg['OutOfDate'] > 0:
      pkg['OutOfDate'] = time.strftime(TIME_FMT, time.localtime(pkg['OutOfDate']))
    else:
      pkg['OutOfDate'] = ''
    for foo in ('FirstSubmitted', 'LastModified'):
      pkg[foo] = time.strftime(TIME_FMT, time.localtime(pkg[foo]))
    for f in fields:
      print(fmt.format(f + ':', pkg[f]))
    print()



def main(args=None):
  """
  Parse command-line arguments and print query results to STDOUT.
  """
  args = parse_args(args)


  if args.debug:
    log_level = logging.DEBUG
  else:
    log_level = None
  logging.basicConfig(
    format='%(levelname)s: %(message)s',
    filename=args.log,
    level=log_level
  )

  ttl = max(args.ttl, 0) * 60
  aur = AUR(ttl=ttl, threads=1)
  if args.info:
    print_query(args.args, typ='info', aur=aur)
  elif args.msearch:
    print_query(args.args, typ='msearch', aur=aur)
  else:
    print_query(args.args, typ='search', aur=aur)



def run_main(args=None):
  """
  Run main() with exception handling.
  """
  try:
    main(args)
  except (KeyboardInterrupt, BrokenPipeError):
    pass
  except AURError as e:
    sys.stderr.write('error: {}\n'.format(e.msg))
    sys.exit(1)
  except urllib.error.URLError as e:
    sys.stderr.write('URLError: {}\n'.format(e))
    sys.exit(1)



if __name__ == '__main__':
  run_main()
