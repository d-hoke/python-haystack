#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2011 Loic Jaquemet loic.jaquemet+python@gmail.com
#

"""This module holds several useful function helpers"""

__author__ = "Loic Jaquemet loic.jaquemet+python@gmail.com"

import logging
import os
import struct
from struct import pack
from struct import unpack

# never import ctypes globally

log = logging.getLogger('utils')


def formatAddress(addr):
    import ctypes
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        return b'0x%016x' % addr
    else:
        return b'0x%08x' % addr


def unpackWord(bytes, endianess='@'):
    import ctypes
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        return struct.unpack('%sQ' % endianess, bytes)[0]
    else:
        return struct.unpack('%sI' % endianess, bytes)[0]


def is_address_local(obj, structType=None):
    """
    Costly , checks if obj is mapped to local memory space.
    Returns the memory mapping if found.
    False, otherwise.
    """
    addr = get_pointee_address(obj)
    if addr == 0:
        return False

    class P:
        pid = os.getpid()
        # we need that for the machine arch read.

        def readBytes(self, addr, size):
            import ctypes
            return ctypes.string_at(addr, size)

    # loading dependencies
    from haystack.mappings.process import readProcessMappings
    mappings = readProcessMappings(P())  # memory_mapping
    ret = mappings.is_valid_address(obj, structType)
    return ret


def get_pointee_address(obj):
    """
    Returns the address of the struct pointed by the obj, or null if invalid.

    :param obj: a pointer.
    """
    import ctypes
    # check for homebrew POINTER
    if hasattr(obj, '_sub_addr_'):
        # print 'obj._sub_addr_', hex(obj._sub_addr_)
        return obj._sub_addr_
    elif isinstance(obj, int) or isinstance(obj, long):
        # basictype pointers are created as int.
        return obj
    elif not bool(obj):
        return 0
    elif ctypes.is_function_type(type(obj)):
        return ctypes.cast(obj, ctypes.c_void_p).value
    elif ctypes.is_pointer_type(type(obj)):
        return ctypes.cast(obj, ctypes.c_void_p).value
        # check for null pointers
        # if bool(obj):
        if not hasattr(obj, 'contents'):
            return 0
        # print '** NOT MY HAYSTACK POINTER'
        return ctypes.addressof(obj.contents)
    else:
        return 0


def container_of(memberaddr, typ, membername):
    """
    From a pointer to a member, returns the parent struct.
    Returns the instance of typ(), in which the member "membername' is really.
    Useful in some Kernel linked list which used members as prec,next pointers.

    :param memberadd: the address of membername.
    :param typ: the type of the containing structure.
    :param membername: the membername.

    Stolen from linux kernel headers.
         const typeof( ((typ *)0)->member ) *__mptr = (ptr);
        (type *)( (char *)__mptr - offsetof(type,member) );})
    """
    return typ.from_address(memberaddr - offsetof(typ, membername))


def offsetof(typ, membername):
    """
    Returns the offset of a member in a structure.

    :param typ: the structure type.
    :param membername: the membername in that structure.
    """
    return getattr(typ, membername).offset


def ctypes_to_python_array(array):
    """Converts an array of undetermined Basic Ctypes class to a python array,
    by guessing it's type from it's class name.

    This is a bad example of introspection.
    """
    import ctypes
    if isinstance(array, str):
        # special case for c_char[]
        return array
    if not ctypes.is_array_of_basic_instance(array):
        raise TypeError('NOT-AN-Basic-Type-ARRAY')
    if array._type_ in [ctypes.c_int, ctypes.c_uint, ctypes.c_long,
                        ctypes.c_ulong, ctypes.c_ubyte, ctypes.c_byte]:
        return [long(el) for el in array]
    if array._type_ in [ctypes.c_float, ctypes.c_double, ctypes.c_longdouble]:
        return [float(el) for el in array]
    sb = ''.join([pack(array._type_._type_, el) for el in array])
    return sb


def array2bytes(array):
    """Converts an array of undetermined Basic Ctypes class to a byte string,
    by guessing it's type from it's class name.

    This is a bad example of introspection.
    """
    import ctypes
    if isinstance(array, str):
        # special case for c_char[]
        return array
    if ctypes.is_array_of_basic_instance(array):
        sb = b''.join([pack(array._type_._type_, el) for el in array])
        return sb
    else:
        c_size = ctypes.sizeof(array)
        a2 = (ctypes.c_ubyte * c_size).from_address(ctypes.addressof(array))
        sb = b''.join([pack('B', el) for el in a2])
        return sb


def bytes2array(bytes, typ):
    """Converts a bytestring in a ctypes array of typ() elements."""
    import ctypes
    typLen = ctypes.sizeof(typ)
    if len(bytes) % typLen != 0:
        raise ValueError('thoses bytes are not an array of %s' % (typ))
    arrayLen = len(bytes) / typLen
    array = (typ * arrayLen)()
    if arrayLen == 0:
        return array
    fmt = ctypes.get_pack_format()[typ.__name__]
    import struct
    try:
        for i in range(0, arrayLen):
            array[i] = struct.unpack(
                fmt, bytes[typLen * i:typLen * (i + 1)])[0]
    except struct.error as e:
        log.error('format:%s typLen*i:typLen*(i+1) = %d:%d' %
                  (fmt, typLen * i, typLen * (i + 1)))
        raise e
    return array


def pointer2bytes(attr, nbElement):
    """
    Returns an array from a ctypes POINTER, given the number of elements.

    :param attr: the structure member.
    :param nbElement: the number of element in the array.
    """
    # attr is a pointer and we want to read elementSize of type(attr.contents))
    if not is_address_local(attr):
        return 'POINTER NOT LOCAL'
    firstElementAddr = get_pointee_address(attr)
    array = (type(attr.contents) * nbElement).from_address(firstElementAddr)
    # we have an array type starting at attr.contents[0]
    return array2bytes(array)


def get_subtype(cls):
    """get the subtype of a pointer, array or basic type with haystack quirks."""
    # could use _pointer_type_cache
    if hasattr(cls, '_subtype_'):
        return cls._subtype_
    return cls._type_


try:
    # Python 2
    py_xrange = xrange

    def xrange(start, end, step=1):
        """ stoupid xrange can't handle long ints... """
        end = end - start
        for val in py_xrange(0, end, step):
            yield start + val
        return
except NameError as e:
    # Python 3
    xrange = range
