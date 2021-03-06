#!/usr/bin/env python

"""This module looks up area codes and returns the most likely city"""

import re
from include.utils import Module
from include.useragent import geturl
from urlparse import urljoin
import logging as log

class Main(Module):
    pattern = re.compile('^\s*area(?:\s+code)?\s+(\d+)\s*', re.I)
    require_addressing = True
    help = 'area <areacode> - what city does it belong to'
    baseurl = 'http://www.melissadata.com/'
    searchurl = urljoin(baseurl, '/lookups/phonelocation.asp')
    city = re.compile(r'<tr><td><A[^>]+>(.*?)</a></td><td>(.*?)</td><td align=center>\d+</td></tr>')

    def response(self, nick, args, kwargs):
        try:
            geturl(self.baseurl)
            doc = geturl(self.searchurl, opts={'number': args[0]})
            city, state = self.city.search(doc).groups()
            city = ' '.join([x.lower().capitalize() for x in city.split()])
            return '%s: %s = %s, %s' % (nick, args[0], city, state)
        except Exception, e:
            log.warn('error in %s: %s' % (self.__module__, e))
            log.exception(e)
            return "%s: I couldn't look that up for some reason.  D:" % nick


if __name__ == '__main__':
    from include.utils import test_module
    test_module(Main)
