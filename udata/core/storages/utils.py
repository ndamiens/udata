# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import hashlib
import zlib
import logging

log = logging.getLogger(__name__)


CHUNK_SIZE = 2 ** 16


def hash(file, hasher):
    # filehash = hashlib.md5()
    blk_size_to_read = hasher.block_size * CHUNK_SIZE
    while (True):
        read_data = file.read(blk_size_to_read)
        if not read_data:
            break
        hasher.update(read_data)
    return hasher.hexdigest()


def sha1(file):
    '''Perform a SHA1 digest on file'''
    return hash(file, hashlib.sha1())


def md5(file):
    '''Perform a MD5 digest on a file'''
    return hash(file, hashlib.md5())


def crc32(file):
    '''Perform a CRC digest on a file'''
    value = zlib.crc32(file.read())
    return '%08X' % (value & 0xFFFFFFFF)