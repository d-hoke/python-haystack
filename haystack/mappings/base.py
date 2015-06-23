#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Provides basic memory mappings helpers.

Short story, the memory of a process is segmented in several memory
zones called memory mapping,
    exemple: the heap, the stack, mmap(2)-s of files, mmap(2)-ing a
             dynamic library, etc.
Theses memory mapping represent the memory space of a process. Each
mapping hasca start and a end address, which gives boundaries for the
range of valid pointer values.

There are several ways to wraps around a memory mapping, given the precise
scenario you are in. You could need a wrapper for a live process debugging, a
wrapper for a mapping that has been dumps in a file, a wrapper for a mapping
that has been remapped to memory, etc.

Classes:
- MemoryMapping : memory mapping metadata
- ProcessMemoryMapping: memory space from a live process with the possibility to mmap the memspace at any moment.
- LocalMemoryMapping .fromAddress: memorymapping that lives in local space in a ctypes buffer.
- MemoryDumpMemoryMapping .fromFile : memory space from a raw file, with lazy loading capabilities.
- FileBackedMemoryMapping .fromFile : memory space based on a file, with direct read no cache from file.

This code first 150 lines is mostly inspired by python ptrace by Haypo / Victor Skinner.
Its intended to be retrofittable with ptrace's memory mappings.
"""

import logging

# haystack
from haystack import utils
from haystack import config

from haystack.structures import heapwalker

__author__ = "Loic Jaquemet"
__copyright__ = "Copyright (C) 2012 Loic Jaquemet"
__email__ = "loic.jaquemet+python@gmail.com"
__license__ = "GPL"
__maintainer__ = "Loic Jaquemet"
__status__ = "Production"
__credits__ = ["Victor Skinner"]

log = logging.getLogger('base')


class MemoryMapping:

    """
    Just the metadata.

        Attributes:
         - start (int): first byte address
         - end (int): last byte address + 1
         - permissions (str)
         - offset (int): for file, offset in bytes from the file start
         - major_device / minor_device (int): major / minor device number
         - inode (int)
         - pathname (str)
         - _process: weak reference to the process

        Operations:
         - "address in mapping" checks the address is in the mapping.
         - "search(somestring)" returns the offsets of "somestring" in the mapping
         - "mmap" mmap the MemoryMap to local address space
         - "readWord()": read a memory word, from local mmap-ed memory if mmap-ed
         - "readBytes()": read some bytes, from local mmap-ed memory if mmap-ed
         - "readStruct()": read a structure, from local mmap-ed memory if mmap-ed
         - "readArray()": read an array, from local mmap-ed memory if mmap-ed
         - "readCString()": read a C string, from local mmap-ed memory if mmap-ed
         - "str(mapping)" create one string describing the mapping
         - "repr(mapping)" create a string representation of the mapping,
             useful in list contexts
    """

    def __init__(self, start, end, permissions, offset,
                 major_device, minor_device, inode, pathname):
        self.config = None
        self.start = start
        self.end = end
        self.permissions = permissions
        self.offset = offset
        self.major_device = major_device
        self.minor_device = minor_device
        self.inode = inode
        self.pathname = str(pathname)  # fix None

    def init_config(self, config):
        self.config = config
        return

    def __contains__(self, address):
        return self.start <= address < self.end

    def __str__(self):
        text = ' '.join([utils.formatAddress(self.start), utils.formatAddress(self.end), self.permissions,
                         '0x%0.8x' % (self.offset), '%0.2x:%0.2x' % (self.major_device, self.minor_device), '%0.7d' % (self.inode), str(self.pathname)])
        return text

    __repr__ = __str__

    def __len__(self):
        return int(self.end - self.start)

    def search(self, bytestr):
        bytestr_len = len(bytestr)
        buf_len = 64 * 1024
        if buf_len < bytestr_len:
            buf_len = bytestr_len
        remaining = self.end - self.start
        covered = self.start
        while remaining >= bytestr_len:
            if remaining > buf_len:
                requested = buf_len
            else:
                requested = remaining
            data = self.readBytes(covered, requested)
            if data == "":
                break
            offset = data.find(bytestr)
            if (offset == -1):
                skip = requested - bytestr_len + 1
            else:
                yield (covered + offset)
                skip = offset + bytestr_len
            covered += skip
            remaining -= skip
        return

    def readCString(self, address, max_size, chunk_length=256):
        ''' identic to process.readCString '''
        string = []
        size = 0
        truncated = False
        while True:
            done = False
            data = self.readBytes(address, chunk_length)
            if '\0' in data:
                done = True
                data = data[:data.index('\0')]
            if max_size <= size + chunk_length:
                data = data[:(max_size - size)]
                string.append(data)
                truncated = True
                break
            string.append(data)
            if done:
                break
            size += chunk_length
            address += chunk_length
        return ''.join(string), truncated

    def vtop(self, vaddr):
        ret = vaddr - self.start
        if ret < 0 or ret > len(self):
            raise ValueError(
                '%x/%x is not a valid vaddr for me' %
                (vaddr, ret))
        return ret

    def ptov(self, paddr):
        pstart = self.vtop(self.start)
        vaddr = paddr - pstart
        return vaddr

    # ---- to implement if needed
    def readWord(self, address):
        raise NotImplementedError(self)

    def readBytes(self, address, size):
        raise NotImplementedError(self)

    def readStruct(self, address, struct):
        raise NotImplementedError(self)

    def readArray(self, address, basetype, count):
        raise NotImplementedError(self)


class Mappings:

    """List of memory mappings for one process"""

    def __init__(self, lst, name='noname'):
        if lst is None:
            self.mappings = []
        elif not isinstance(lst, list):
            raise TypeError('Please feed me a list')
        else:
            self.mappings = list(lst)
        self.config = None
        self.name = name
        self.__heaps = None
        self.__heap_finder = None
        self.__os_name = None
        self.__cpu_bits = None
        # book register to keep references to ctypes memory buffers
        self.__book = _book()
        # set the word size in this config.
        self.__wordsize = None
        self.__required_maps = []
        # self._init_word_size()

    def get_context(self, addr):
        """Returns the haystack.reverse.context.ReverserContext of this dump.
        """
        assert isinstance(addr, long) or isinstance(addr, int)
        mmap = self.get_mapping_for_address(addr)
        if not mmap:
            raise ValueError
        if hasattr(mmap, '_context'):
            # print '** _context exists'
            return mmap._context
        if mmap not in self.get_heaps():  # addr is not a heap addr,
            found = False
            # or its in a child heap ( win7)
            for h in self.get_heaps():
                if hasattr(h, '_children'):
                    if mmap in h._children:
                        found = True
                        mmap = h
                        break
            if not found:
                raise ValueError
        # we found the heap mmap or its parent
        from haystack.reverse import context
        try:
            ctx = context.ReverserContext.cacheLoad(self)
            # print '** CACHELOADED'
        except IOError as e:
            ctx = context.ReverserContext(self, mmap)
            # print '** newly loaded '
        # cache it
        mmap._context = ctx
        return ctx

    def get_user_allocations(self, heap, filterInUse=True):
        """changed when the dump is loaded"""
        assert isinstance(heap, MemoryMapping)
        if self.__heap_finder is None:
            self.get_heaps()

        walker = self.__heap_finder.get_walker_for_heap(self, heap)
        return walker.get_user_allocations()

    def get_mapping(self, pathname):
        mmap = None
        if len(self.mappings) >= 1:
            mmap = [m for m in self.mappings if m.pathname == pathname]
        if len(mmap) < 1:
            raise IndexError('No mmap of pathname %s' % (pathname))
        return mmap

    def get_mapping_for_address(self, vaddr):
        assert isinstance(vaddr, long) or isinstance(vaddr, int)
        for m in self.mappings:
            if vaddr in m:
                return m
        return False

    def init_config(self, cpu=None, os_name=None):
        """Pre-populate cpu and os_name"""
        if os_name is not None and os_name not in ['linux', 'winxp', 'win7']:
            raise NotImplementedError('OS not implemented: %s' % (os_name))
        if cpu is not None and cpu not in ['32', '64']:
            raise NotImplementedError('CPU bites not implemented: %s' % (cpu))
        self.__os_name = os_name
        self.__cpu_bits = cpu
        # the config init should NOT load heaps as a way to determine the
        # memory dump arch
        # self.get_heaps()
        # but
        os_name = self.get_os_name()
        cpu = self.get_cpu_bits()
        # Change ctypes now
        from haystack import config
        self.config = config.make_config(cpu=cpu, os_name=os_name)
        self._reset_config()

    def get_heap(self):
        """Returns the first Heap"""
        return self.get_heaps()[0]

    def get_heaps(self):
        """Find heap type and returns mappings with heaps"""
        if self.__heaps is None:
            self.__heap_finder = heapwalker.make_heap_walker(self)
            self.__heaps = self.__heap_finder.get_heap_mappings(self)
            # if len(self.__heaps) == 0:
            #    raise RuntimeError("No heap found")
        return self.__heaps

    def _reset_config(self):
        # This is where the config is set for all maps.
        for m in self.mappings:
            m.config = self.config
        return

    def get_stack(self):
        # FIXME wont work.
        stack = self.get_mapping('[stack]')[0]
        return stack

    def append(self, m):
        assert isinstance(m, MemoryMapping)
        self.mappings.append(m)
        if self.config is not None:
            m.config = self.config

    def get_os_name(self):
        if self.__os_name is not None:
            return self.__os_name
        self.__os_name = heapwalker.detect_os(self.mappings)
        return self.__os_name

    def get_cpu_bits(self):
        if self.__cpu_bits is not None:
            return self.__cpu_bits
        self.__cpu_bits = heapwalker.detect_cpu(self.mappings, self.__os_name)
        return self.__cpu_bits

    def is_valid_address(self, obj, structType=None):  # FIXME is valid pointer
        """
        :param obj: the obj to evaluate.
        :param structType: the object's type, so the size could be taken in consideration.

        Returns False if the object address is NULL.
        Returns False if the object address is not in a mapping.

        Returns the mapping in which the object stands otherwise.
        """
        # check for null pointers
        addr = utils.get_pointee_address(obj)
        if addr == 0:
            return False
        return self.is_valid_address_value(addr, structType)

    def is_valid_address_value(self, addr, structType=None):
        """
        :param addr: the address to evaluate.
        :param structType: the object's type, so the size could be taken in consideration.

        Returns False if the object address is NULL.
        Returns False if the object address is not in a mapping.
        Returns False if the object overflows the mapping.

        Returns the mapping in which the address stands otherwise.
        """
        import ctypes
        m = self.get_mapping_for_address(addr)
        log.debug('is_valid_address_value = %x %s' % (addr, m))
        if m:
            if (structType is not None):
                s = ctypes.sizeof(structType)
                if (addr + s) < m.start or (addr + s) > m.end:
                    return False
            return m
        return False

    def __contains__(self, vaddr):
        for m in self.mappings:
            if vaddr in m:
                return True
        return False

    def __len__(self):
        return len(self.mappings)

    def __getitem__(self, i):
        return self.mappings[i]

    def __setitem__(self, i, val):
        raise NotImplementedError()

    def __iter__(self):
        return iter(self.mappings)

    def reset(self):
        """Clean the book"""
        self.__book.refs = dict()

    def getRefs(self):
        """Lists all references to already loaded structs. Useful for debug"""
        return self.__book.refs.items()

    def printRefs(self):
        """Prints all references to already loaded structs. Useful for debug"""
        l = [(typ, obj, addr)
             for ((typ, addr), obj) in self.__book.refs.items()]
        for i in l:
            print(l)

    def printRefsLite(self):
        """Prints all references to already loaded structs. Useful for debug"""
        l = [(typ, addr) for ((typ, addr), obj) in self.__book.refs.items()]
        for i in l:
            print(l)

    def hasRef(self, typ, origAddr):
        """Check if this type has already been loaded at this address"""
        return (typ, origAddr) in self.__book.refs

    def getRef(self, typ, origAddr):
        """Returns the reference to the type previously loaded at this address"""
        if (typ, origAddr) in self.__book.refs:
            return self.__book.getRef(typ, origAddr)
        return None

    def getRefByAddr(self, addr):
        ret = []
        for (typ, origAddr) in self.__book.refs.keys():
            if origAddr == addr:
                ret.append((typ, origAddr, self.__book.refs[(typ, origAddr)]))
        return ret

    def keepRef(self, obj, typ=None, origAddr=None):
        """Keeps a reference for an object of a specific type loaded from a specific
        address.

        Sometypes, your have to cast a c_void_p, You can keep ref in Ctypes object,
           they might be transient (if obj == somepointer.contents)."""
        # TODO, memory leak for different objects of same size, overlapping
        # struct.
        if (typ, origAddr) in self.__book.refs:
            # ADDRESS already in refs
            if origAddr is None:
                origAddr = 'None'
            else:
                origAddr = hex(origAddr)
            if typ is not None:
                log.debug(
                    'ignore keepRef - references already in cache %s/%s' %
                    (typ, origAddr))
            return
        # there is no pre-existing typ().from_address(origAddr)
        self.__book.addRef(obj, typ, origAddr)
        return

    def delRef(self, typ, origAddr):
        """Forget about a Ref."""
        if (typ, origAddr) in self.__book.refs:
            self.__book.delRef(typ, origAddr)
        return


class _book(object):

    """The book registers all registered ctypes modules and keeps
    some pointer refs to buffers allocated in memory mappings.

    # see also ctypes._pointer_type_cache , _reset_cache()
    """

    def __init__(self):
        self.refs = dict()
        pass

    def addRef(self, obj, typ, addr):
        self.refs[(typ, addr)] = obj

    def getRef(self, typ, addr):
        if len(self.refs) > 35000:
            log.warning('the book is full, you should haystack.model.reset()')
        return self.refs[(typ, addr)]

    def delRef(self, typ, addr):
        del self.refs[(typ, addr)]
