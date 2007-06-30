#!/usr/bin/env python

"""
$Id: calc.py,v 1.1.1.1 2007/06/25 23:09:20 cjones Exp $

Use Google as a calculator
"""

import sys
import re
import urllib
import urllib2

# class for this module
class match(object):
	def __init__(self):
		self.enabled = True				# True/False - enabled?
		self.pattern = re.compile('calc\s+(.+)')	# regular expression that needs to be matched
		self.requireAddressing = True			# True/False - require addressing?
		self.thread = True				# True/False - should bot spawn thread?
		self.wrap = True				# True/False - wrap output?
		self.help = 'calc <expression> - pass expression to google calculator'

		self.test  = re.compile('More about (calculator|currency)')
		self.match = re.compile('<h2 class=r>.*?<b>(.*?)<\/b><\/h2>')
		self.strip = re.compile('<[^>]+>')

	# function to generate a response
	def response(self, nick, args):
		try:
			query = ' '.join(args)
			url = 'http://www.google.com/search?' + urllib.urlencode(
					{	'hl'		: 'en',
						'safe'		: 'off',
						'c2coff'	: 1,
						'btnG'		: 'Search',
						'q'		: query	}
					)

			request = urllib2.Request(url)
			request.add_header('User-Agent', 'Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1)')
			opener = urllib2.build_opener()
			doc = opener.open(request).read()

			if self.test.search(doc):
				match = self.match.search(doc)
				if match:
					return '%s: %s' % (nick, self.strip.sub('', match.group(1)))

			return '%s: No results, check your syntax at http://www.google.com/help/calculator.html' % nick

		except Exception, e:
			print >> sys.stderr, 'error in %s: %s' % (self.__module__, e)
			return "%s: I couldn't look that up for some reason.  D:" % nick


# this is just here so we can test the module from the commandline
def main(argv = None):
	if argv is None: argv = sys.argv[1:]
	obj = match()
	print obj.response('testUser', argv)

	return 0

if __name__ == '__main__': sys.exit(main())
