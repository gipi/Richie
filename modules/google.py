#!/usr/bin/env python

"""I'm feeling lucky"""

import urllib
import urllib2
from include.utils import Base, Module, Error
from include.useragent import UserAgent
from urlparse import urljoin
import re
import logging as log

__version__ = '0.2'
__author__ = 'cj_ <cjones@gruntle.org>'
__license__ = 'GPL'

class NonRedirectResponse(Error):
    """Raised when google doesn't return a redirect"""


class Response(Base):

    def __init__(self, data=''):
        self.data = data

    def read(self, *args, **kwargs):
        return self.data


class NoRedirects(urllib2.HTTPRedirectHandler):
    """Override auto-follow of redirects"""

    def redirect_request(self, *args, **kwargs):
        pass


class NoErrors(urllib2.HTTPDefaultErrorHandler):    
    """Don't allow urllib to throw an error on 30x code"""

    def http_error_default(self, req, fp, code, msg, headers): 
        return Response(data=dict(headers.items())['location'])


class Google(Base):
    baseurl = 'http://www.google.com/'
    search = urljoin(baseurl, '/search')
    luckyopts = {'hl': 'en', 'btnI': 'I', 'aq': 'f', 'safe': 'off'}

    def __init__(self):
        self.ua = UserAgent(handlers=[NoRedirects, NoErrors])

    def lucky(self, query):
        opts = dict(self.luckyopts.items())
        opts['q'] = query
        result = self.ua.openurl(self.search, opts=opts,
                referer=self.baseurl, size=1024)
        if not result.startswith('http'):
            raise NonRedirectResponse
        return '%s = %s' % (query, result)


class Main(Module):
    pattern = re.compile('^\s*google\s+(.*?)\s*$')
    require_addressing = True
    help = "google <query> - i'm feeling lucky"

    def __init__(self, *args, **kwargs):
        self.google = Google()

    def response(self, nick, args, **kwargs):
        try:
            query = args[0]
            return '%s: %s' % (nick, self.google.lucky(query))
        except Exception, e:
            log.warn('error in %s: %s' % (self.__module__, e))
            log.exception(e)
            return '%s: Not so lucky today..' % nick


if __name__ == '__main__':
    from include.utils import test_module
    test_module(Main)
