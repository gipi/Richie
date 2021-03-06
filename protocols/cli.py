import sys
from madcow import Madcow, Request
import os
from include.colorlib import ColorLib
import re
import logging as log
from include.shell import Shell

class ConsoleProtocol(Madcow):
    _new_nick = re.compile(r'^\s*nick\s+(\S+)\s*$', re.I)
    _cli_usage = [
        'quit - quit madcow',
        'history - show history',
        'nick <nick> - change your nick',
        'clear - clear screen'
    ]
    _prompt = '\x1b[1;31m>>>\x1b[0m '
    _clear = '\x1b[H\x1b[J'

    def __init__(self, config=None, dir=None):
        self.colorlib = ColorLib('ansi')
        Madcow.__init__(self, config=config, dir=dir)
        self.user_nick = os.environ['USER']
        self.shell = Shell(polls=[self.check_response_queue])
        self.usageLines += self._cli_usage

    def run(self):
        self.output("type 'help' for a list of commands")
        while self.running:
            self.check_response_queue()
            try:
                input = self.shell.readline(self._prompt)
            except IOError:
                # this happens when you get EINTR from SIGHUP handling
                continue

            if input.lower() == 'quit':
                break

            if input.lower() == 'history':
                print 'history: %s' % repr(self.shell.history)

            if input.lower() == 'clear':
                sys.stdout.write(self._clear)
                continue

            if len(input) > 0:
                req = Request(message=input)
                req.nick = self.user_nick
                req.channel = 'cli'
                req.private = True
                req.addressed = True

                self.checkAddressing(req)

                if req.message.startswith('^'):
                    req.colorize = True
                    req.message = req.message[1:]

                try:
                    self.user_nick = self._new_nick.search(req.message).group(1)
                    self.output('nick changed to: %s' % self.user_nick, req)
                    continue
                except:
                    pass
                self.process_message(req)

    def protocol_output(self, message, req=None):
        if req is not None and req.colorize is True:
            message = self.colorlib.rainbow(message)
        print message


class ProtocolHandler(ConsoleProtocol):
    pass


