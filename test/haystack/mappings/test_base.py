#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests haystack.utils ."""

from __future__ import print_function

import logging
import mmap
import os
import struct
import unittest

from haystack import listmodel
from haystack import target
from haystack.mappings.base import AMemoryMapping
from haystack.mappings.process import make_local_memory_handler
from haystack.mappings import folder
from test.haystack import SrcTests

log = logging.getLogger('test_memory_mapping')


class TestMmapHack(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_mmap_hack64(self):
        my_target = target.TargetPlatform.make_target_linux_64()
        my_ctypes = my_target.get_target_ctypes()
        my_utils = my_target.get_target_ctypes_utils()

        real_ctypes_long = my_ctypes.get_real_ctypes_member('c_ulong')
        fname = os.path.normpath(os.path.abspath(__file__))
        fin = open(fname, 'rb')
        local_mmap_bytebuffer = mmap.mmap(fin.fileno(), 1024, access=mmap.ACCESS_READ)
        # yeap, that right, I'm stealing the pointer value. DEAL WITH IT.
        heapmap = struct.unpack('L', real_ctypes_long.from_address(id(local_mmap_bytebuffer) +
                                                                     2 * (my_ctypes.sizeof(real_ctypes_long))))[0]
        log.debug('MMAP HACK: heapmap: 0x%0.8x' % heapmap)
        handler = make_local_memory_handler(force=True)
        ret = [m for m in handler.get_mappings() if heapmap in m]
        if len(ret) == 0:
            for m in handler.get_mappings():
                print(m)
        # heapmap is a pointer value in local memory
        self.assertEqual(len(ret), 1)
        # heapmap is a pointer value to this executable?
        self.assertEqual(ret[0].pathname, fname)

        self.assertIn('CTypesProxy-8:8:16', str(my_ctypes))
        fin.close()
        fin = None

    def test_mmap_hack32(self):
        my_target = target.TargetPlatform.make_target_linux_32()
        my_ctypes = my_target.get_target_ctypes()
        my_utils = my_target.get_target_ctypes_utils()

        real_ctypes_long = my_ctypes.get_real_ctypes_member('c_ulong')
        fname = os.path.normpath(os.path.abspath(__file__))
        fin = open(fname, 'rb')
        local_mmap_bytebuffer = mmap.mmap(fin.fileno(), 1024, access=mmap.ACCESS_READ)
        # yeap, that right, I'm stealing the pointer value. DEAL WITH IT.
        heapmap = struct.unpack('L', real_ctypes_long.from_address(id(local_mmap_bytebuffer) +
                                                                     2 * (my_ctypes.sizeof(real_ctypes_long))))[0]
        log.debug('MMAP HACK: heapmap: 0x%0.8x', heapmap)
        maps = make_local_memory_handler(force=True)
        # print 'MMAP HACK: heapmap: 0x%0.8x' % heapmap
        # for m in maps:
        #    print m
        ret = [m for m in maps if heapmap in m]
        # heapmap is a pointer value in local memory
        self.assertEqual(len(ret), 1)
        # heapmap is a pointer value to this executable?
        self.assertEqual(ret[0].pathname, fname)
        self.assertIn('CTypesProxy-4:4:12', str(my_ctypes))
        fin.close()
        fin = None


class TestMappingsLinux(SrcTests):

    @classmethod
    def setUpClass(cls):
        cls.memory_handler = folder.load('test/dumps/ssh/ssh.1')

    @classmethod
    def tearDownClass(cls):
        cls.memory_handler.reset_mappings()
        cls.memory_handler = None

    def test_get_mapping(self):
        self.assertEqual(len(self.memory_handler._get_mapping('[heap]')), 1)
        self.assertEqual(len(self.memory_handler._get_mapping('None')), 9)

    def test_get_mapping_for_address(self):
        finder = self.memory_handler.get_heap_finder()
        walker = finder.list_heap_walkers()[0]
        self.assertEqual(walker.get_heap_address(), self.memory_handler.get_mapping_for_address(0xb84e02d3).start)

    def test_contains(self):
        for m in self.memory_handler:
            self.assertTrue(m.start in self.memory_handler)
            self.assertTrue((m.end - 1) in self.memory_handler)

    def test_len(self):
        self.assertEqual(len(self.memory_handler), 70)

    def test_getitem(self):
        self.assertTrue(isinstance(self.memory_handler[0], AMemoryMapping))
        self.assertTrue(
            isinstance(self.memory_handler[len(self.memory_handler) - 1], AMemoryMapping))
        with self.assertRaises(IndexError):
            self.memory_handler[0x0005c000]

    def test_iter(self):
        mps = [m for m in self.memory_handler]
        mps2 = [m for m in self.memory_handler.get_mappings()]
        self.assertEqual(mps, mps2)

    def test_setitem(self):
        with self.assertRaises(NotImplementedError):
            self.memory_handler[0x0005c000] = 1

    def test_get_os_name(self):
        x = self.memory_handler.get_target_platform().get_os_name()
        self.assertEqual(x, 'linux')

    def test_get_cpu_bits(self):
        x = self.memory_handler.get_target_platform().get_cpu_bits()
        self.assertEqual(x, 32)


class TestMappingsLinuxAddresses32(SrcTests):

    @classmethod
    def setUpClass(cls):
        cls.memory_handler = folder.load('test/src/test-ctypes5.32.dump')
        cls.my_target = cls.memory_handler.get_target_platform()
        cls.my_ctypes = cls.my_target.get_target_ctypes()
        cls.my_utils = cls.my_target.get_target_ctypes_utils()
        cls.my_model = cls.memory_handler.get_model()
        cls.ctypes5_gen32 = cls.my_model.import_module("test.src.ctypes5_gen32")
        cls.validator = listmodel.ListModel(cls.memory_handler, None)

    def setUp(self):
        self._load_offsets_values('test/src/test-ctypes5.32.dump')

    @classmethod
    def tearDownClass(cls):
        cls.memory_handler = None
        cls.my_target = None
        cls.my_ctypes = None
        cls.my_utils = None
        cls.my_model = None
        cls.ctypes5_gen32 = None
        pass

    def test_is_valid_address(self):
        offset = self.offsets['struct_d'][0]
        m = self.memory_handler.get_mapping_for_address(offset)
        d = m.read_struct(offset, self.ctypes5_gen32.struct_d)
        ret = self.validator.load_members(d, 10)

        self.assertTrue(self.memory_handler.is_valid_address(d.a))
        self.assertTrue(self.memory_handler.is_valid_address(d.b))
        self.assertTrue(self.memory_handler.is_valid_address(d.d))
        self.assertTrue(self.memory_handler.is_valid_address(d.h))
        pass

    def test_is_valid_address_value(self):

        offset = self.offsets['struct_d'][0]
        m = self.memory_handler.get_mapping_for_address(offset)
        d = m.read_struct(offset, self.ctypes5_gen32.struct_d)
        ret = self.validator.load_members(d, 10)

        self.assertTrue(self.memory_handler.is_valid_address(d.a.value))
        self.assertTrue(self.memory_handler.is_valid_address(d.b.value))
        self.assertTrue(self.memory_handler.is_valid_address(d.d.value))
        self.assertTrue(self.memory_handler.is_valid_address(d.h.value))
        pass


class TestMappingsWin32(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.memory_handler = folder.load('test/dumps/putty/putty.1.dump')
        cls.my_target = cls.memory_handler.get_target_platform()
        cls.my_ctypes = cls.my_target.get_target_ctypes()
        cls.my_utils = cls.my_target.get_target_ctypes_utils()

    @classmethod
    def tearDownClass(cls):
        cls.memory_handler.reset_mappings()
        cls.memory_handler = None
        cls.my_target = None
        cls.my_ctypes = None
        cls.my_utils = None

    def test_get_mapping(self):
        # FIXME: remove
        with self.assertRaises(IndexError):
            self.assertEqual(len(self.memory_handler._get_mapping('[heap]')), 1)
        self.assertEqual(len(self.memory_handler._get_mapping('None')), 71)

    def test_get_mapping_for_address(self):
        m = self.memory_handler.get_mapping_for_address(0x005c0000)
        self.assertNotEquals(m, False)
        self.assertEqual(m.start, 0x005c0000)
        self.assertEqual(m.end, 0x00619000)

    def test_contains(self):
        for m in self.memory_handler:
            self.assertTrue(m.start in self.memory_handler)
            self.assertTrue((m.end - 1) in self.memory_handler)

    def test_len(self):
        self.assertEqual(len(self.memory_handler), 403)

    def test_getitem(self):
        self.assertTrue(isinstance(self.memory_handler[0], AMemoryMapping))
        self.assertTrue(
            isinstance(self.memory_handler[len(self.memory_handler) - 1], AMemoryMapping))
        with self.assertRaises(IndexError):
            self.memory_handler[0x0005c000]

    def test_iter(self):
        mps = [m for m in self.memory_handler]
        mps2 = [m for m in self.memory_handler.get_mappings()]
        self.assertEqual(mps, mps2)

    def test_setitem(self):
        with self.assertRaises(NotImplementedError):
            self.memory_handler[0x0005c000] = 1

    def test_get_os_name(self):
        x = self.memory_handler.get_target_platform().get_os_name()
        self.assertEqual(x, 'win7')

    def test_get_cpu_bits(self):
        x = self.memory_handler.get_target_platform().get_cpu_bits()
        self.assertEqual(x, 32)



class TestReferenceBook(unittest.TestCase):

    """Test the reference book."""

    def setUp(self):
        self.memory_handler = folder.load('test/src/test-ctypes6.32.dump')

    def tearDown(self):
        self.memory_handler.reset_mappings()
        self.memory_handler = None

    def test_keepRef(self):
        self.assertEqual(len(self.memory_handler.getRefByAddr(0xcafecafe)), 0)
        self.assertEqual(len(self.memory_handler.getRefByAddr(0xdeadbeef)), 0)

        # same address, same type
        self.memory_handler.keepRef(1, int, 0xcafecafe)
        self.memory_handler.keepRef(2, int, 0xcafecafe)
        self.memory_handler.keepRef(3, int, 0xcafecafe)
        me = self.memory_handler.getRefByAddr(0xcafecafe)
        # only one ref ( the first)
        self.assertEqual(len(me), 1)

        # different type, same address
        self.memory_handler.keepRef('4', str, 0xcafecafe)
        me = self.memory_handler.getRefByAddr(0xcafecafe)
        # multiple refs
        self.assertEqual(len(me), 2)
        return

    def test_hasRef(self):
        self.assertEqual(len(self.memory_handler.getRefByAddr(0xcafecafe)), 0)
        self.assertEqual(len(self.memory_handler.getRefByAddr(0xdeadbeef)), 0)

        # same address, different types
        self.memory_handler.keepRef(1, int, 0xcafecafe)
        self.memory_handler.keepRef(2, float, 0xcafecafe)
        self.memory_handler.keepRef(3, str, 0xcafecafe)

        self.assertTrue(self.memory_handler.hasRef(int, 0xcafecafe))
        self.assertTrue(self.memory_handler.hasRef(float, 0xcafecafe))
        self.assertTrue(self.memory_handler.hasRef(str, 0xcafecafe))
        self.assertFalse(self.memory_handler.hasRef(int, 0xdeadbeef))
        me = self.memory_handler.getRefByAddr(0xcafecafe)
        # multiple refs
        self.assertEqual(len(me), 3)

    def test_getRef(self):
        self.assertEqual(len(self.memory_handler.getRefByAddr(0xcafecafe)), 0)
        self.assertEqual(len(self.memory_handler.getRefByAddr(0xdeadbeef)), 0)
        self.memory_handler.keepRef(1, int, 0xcafecafe)
        self.memory_handler.keepRef(2, float, 0xcafecafe)

        self.assertEqual(self.memory_handler.getRef(int, 0xcafecafe), 1)
        self.assertEqual(self.memory_handler.getRef(float, 0xcafecafe), 2)
        self.assertIsNone(self.memory_handler.getRef(str, 0xcafecafe))
        self.assertIsNone(self.memory_handler.getRef(str, 0xdeadbeef))
        self.assertIsNone(self.memory_handler.getRef(int, 0xdeadbeef))

    def test_delRef(self):
        self.assertEqual(len(self.memory_handler.getRefByAddr(0xcafecafe)), 0)
        self.assertEqual(len(self.memory_handler.getRefByAddr(0xdeadbeef)), 0)

        self.memory_handler.keepRef(1, int, 0xcafecafe)
        self.memory_handler.keepRef(2, float, 0xcafecafe)
        self.memory_handler.keepRef(3, str, 0xcafecafe)

        self.assertTrue(self.memory_handler.hasRef(int, 0xcafecafe))
        self.assertTrue(self.memory_handler.hasRef(float, 0xcafecafe))
        self.assertTrue(self.memory_handler.hasRef(str, 0xcafecafe))
        # del one type
        self.memory_handler.delRef(str, 0xcafecafe)
        self.assertTrue(self.memory_handler.hasRef(int, 0xcafecafe))
        self.assertTrue(self.memory_handler.hasRef(float, 0xcafecafe))
        self.assertFalse(self.memory_handler.hasRef(str, 0xcafecafe))
        # try harder, same type, same result
        self.memory_handler.delRef(str, 0xcafecafe)
        self.assertTrue(self.memory_handler.hasRef(int, 0xcafecafe))
        self.assertTrue(self.memory_handler.hasRef(float, 0xcafecafe))
        self.assertFalse(self.memory_handler.hasRef(str, 0xcafecafe))

        self.memory_handler.delRef(int, 0xcafecafe)
        self.assertFalse(self.memory_handler.hasRef(int, 0xcafecafe))
        self.assertTrue(self.memory_handler.hasRef(float, 0xcafecafe))
        self.assertFalse(self.memory_handler.hasRef(str, 0xcafecafe))

        self.memory_handler.delRef(float, 0xcafecafe)
        self.assertFalse(self.memory_handler.hasRef(int, 0xcafecafe))
        self.assertFalse(self.memory_handler.hasRef(float, 0xcafecafe))
        self.assertFalse(self.memory_handler.hasRef(str, 0xcafecafe))


if __name__ == '__main__':
    # logging.basicConfig(level=logging.DEBUG)
    logging.basicConfig(level=logging.INFO)
    # logging.getLogger('memory_mapping').setLevel(logging.DEBUG)
    # logging.getLogger('basicmodel').setLevel(logging.INFO)
    # logging.getLogger('model').setLevel(logging.INFO)
    # logging.getLogger('listmodel').setLevel(logging.INFO)
    unittest.main(verbosity=2)
