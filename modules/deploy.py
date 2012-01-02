#!/usr/bin/env python

"""Module stub"""

from include.utils import Module
import logging as log
import re
import subprocess
import sys
#from include.useragent import geturl   # mimic browser
#from include.utils import stripHTML    # strip HTML/unescape entities

__version__ = '0.1'
__author__ = 'Gianluca Pacchiella <gp@ktln2.org>'
__license__ = 'GPL'
__copyright__ = 'Copyright (C) 2012'
__all__ = []

class Main(Module):
    """
    This module deploies a project and manage the deployment configuration.
    """
    pattern = re.compile(r'^\s*deploy\s+(.*?)\s*$', re.I) # opt params

    enabled = True             # this can be set to false to disable addon
    require_addressing = True  # whether you need to address bot directly
    help = 'deploy <cmd> - deploy/configure a deploied project'
    allow_threading = True     # whether to launch a thread for this module

    def __init__(self, madcow=None):
        self.madcow = madcow # this gives user access to the internal bot

    def exe(self, cmd, user, project):
        """
        Execs a command related to a particular couple project/user.
        """
        # TODO: use configuration file in order to set these paths
        worktree = "/tmp/deploy/%s/%s/" % (project, user)
        gitdir   = "/tmp/repositories/%s/" % (project,)
        cmds = {
                # shows the last commit in the repo
                "last"  : [
                        "git",
                        "--git-dir=%s" % gitdir,
                        "--work-tree=%s" % worktree,
                        "log" ,
                        "-1" ,
                        "--oneline",
                ],
                "co"    : [
                        "git",
                        "--git-dir=%s" % gitdir,
                        "--work-tree=%s" % worktree,
                        "checkout" ,
                        "-f",
                ],
        }

        if cmd not in cmds.keys():
                return "%s: command unknown for deploy" % (cmd,)
        try:
                return subprocess.check_output(cmds[cmd]),
        except subprocess.CalledProcessError, e:
                log.warn('error in %s: %s' % (self.__module__, e))
                log.exception(e)
                return "user: deploy failed"

    def response(self, nick, args, kwargs):
        # this function should return a response or None
        # - args is a list that matches the matched parts of the pattern
        # - kwargs give you access to the details of the request from the bot
        # "deploy last user1/next" -> args = ("last user1/next",)
        command_param = args[0].split(" ")

        command = command_param[0]

        #import pdb;pdb.set_trace()

        if command == "help":
                return """commands available:
        last: shows the last commit
        co:   executes a checkout of the project in your deploy area
        loaddata: loads in the database a passed json
"""

        try:
            return self.exe(command, nick, kwargs["channel"][1:])
        except Exception, e:
            log.warn('error in %s: %s' % (self.__module__, e))
            log.exception(e)
            return '%s: %s' % (nick, e)


if __name__ == '__main__':
    from include.utils import test_module
    test_module(Main)
