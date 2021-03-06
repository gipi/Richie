#!/usr/bin/env python

"""Handles authentication in Madcow"""

from utils import Base, Error
from random import randint
import sha
from base64 import b64encode, b64decode

__version__ = '0.2'
__author__ = 'cj_ <cjones@gruntle.org>'
__license__ = 'GPL'
__copyright__ = 'Copyright (C) 2007-2008 Christopher Jones'
__all__ = ['UserNotFound', 'IllegalUserName', 'AuthLib']

class UserNotFound(Error):
    pass


class IllegalUserName(Error):
    pass


class AuthLib(Base):

    def __init__(self, path):
        self.path = path

    def get_passwd(self):
        try:
            fo = open(self.path)
            try:
                data = fo.read()
            finally:
                fo.close()
        except:
            data = ''
        passwd = {}
        for line in data.splitlines():
            line = line.strip()
            if not len(line):
                continue
            username, password, flags = line.split(':')
            passwd[username] = {'password': password, 'flags': flags}
        return passwd

    def write_passwd(self, passwd):
        data = []
        for user, user_data in passwd.items():
            line = ':'.join([user, user_data['password'], user_data['flags']])
            data.append(line)
        data = '\n'.join(data) + '\n'
        fo = open(self.path, 'wb')
        try:
            fo.write(data)
        finally:
            fo.close()

    def change_flags(self, user, flags):
        passwd = self.get_passwd()
        if not passwd.has_key(user):
            raise UserNotFound
        passwd[user]['flags'] = flags
        self.write_passwd(passwd)

    def change_password(self, user, plain):
        passwd = self.get_passwd()
        if not passwd.has_key(user):
            raise UserNotFound
        passwd[user]['password'] = self.encrypt(plain)
        self.write_passwd(passwd)

    def add_user(self, user, plain, flags=''):
        if ':' in user:
            raise IllegalUserName, 'usernames cannot have : in them'
        if plain == None:
            password = '*'
        else:
            password = self.encrypt(plain)
        passwd = self.get_passwd()
        passwd[user] = {'password': password, 'flags': flags}
        self.write_passwd(passwd)

    def delete_user(self, user):
        passwd = self.get_passwd()
        if not passwd.has_key(user):
            raise UserNotFound, user
        del passwd[user]
        self.write_passwd(passwd)

    def check_user(self, user, plain):
        passwd = self.get_passwd()
        if not passwd.has_key(user):
            raise UserNotFound, user
        return self.check(passwd[user]['password'], plain)

    def user_exists(self, user):
        passwd = self.get_passwd()
        return passwd.has_key(user)

    def get_flags(self, user):
        passwd = self.get_passwd()
        if not passwd.has_key(user):
            raise UserNotFound, user
        return passwd[user]['flags']

    def encrypt(self, plain):
        digest, salt = self.get_digest(plain)
        return b64encode(salt + digest)

    def get_digest(self, plain, salt=None):
        if salt is None:
            salt = ''.join([chr(randint(0, 255)) for i in range(4)])
        return sha.new(salt + plain).digest(), salt

    def check(self, encrypted, plain):
        if encrypted == '*':
            return False
        salted = b64decode(encrypted)
        salt, digest = salted[:4], salted[4:]
        return digest == self.get_digest(plain, salt)[0]

