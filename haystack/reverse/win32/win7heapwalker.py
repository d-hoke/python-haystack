#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2011 Loic Jaquemet loic.jaquemet+python@gmail.com
#

__author__ = "Loic Jaquemet loic.jaquemet+python@gmail.com"

import logging
import sys

import numpy 
from haystack import model
from haystack.reverse import heapwalker
from haystack.reverse.win32 import win7heap

log=logging.getLogger('win7heapwalker')


class Win7HeapWalker(heapwalker.HeapWalker):
  ''' '''
  def _initHeap(self):
    self._allocs = None
    self._heap = self._mapping.readStruct(self._mapping.start+self._offset, win7heap.HEAP)
    if not self._heap.loadMembers(self._mappings, -1):
      raise TypeError('HEAP.loadMembers returned False')

    log.debug('+ Heap @%0.8x size: %d # %s'%(self._mapping.start+self._offset, len(self._mapping), self._mapping) )
    #print '+ Heap @%0.8x size:%d FTH_Type:0x%x maskFlag:0x%x index:0x%x'%(self._mapping.start+self._offset, 
    #              len(self._mapping), self._heap.FrontEndHeapType, self._heap.EncodeFlagMask, self._heap.ProcessHeapsListIndex) 
    return

  def getUserAllocations(self):
    ''' returns all User allocations (addr,size) '''
    if self._allocs is None:
      vallocs = self._getVirtualAllocations()
      chunks = self._getChunks()
      fth_chunks = self._getFrontendChunks()
      # DEBUG : delete replace by iterator on the 3 iterator
      lst = vallocs+chunks+fth_chunks
      myset = set(lst)
      if len(lst) != len(myset):
        log.warning('NON unique referenced chunks found. Please enquire. %d != %d'%(lstlen, setlen) )
      self._allocs = numpy.asarray(sorted(myset))
      # found targetted mappings...
      #print set([ self._mappings.getMmapForAddr(a[0]) for a in self._allocs if a[0] not in self._mapping])
    return self._allocs

  def HEAP(self):
    return self._heap
  
  def _getVirtualAllocations(self):
    allocated = [ block for block in self._heap.iterateListField(self._mappings, 'VirtualAllocdBlocks') ]
    # DEBUG : delete replace by iterator
    log.debug( '\t+ %d vallocated blocks'%( len(allocated) ) )
    for block in allocated: #### BAD should return (vaddr,size)
      log.debug( '\t\t- vallocated commit %x reserve %x @%0.8x'%(block.CommitSize, block.ReserveSize, ctypes.addressof(block)))
    #
    return allocated
  
  def _getChunks(self):
    chunks = [ chunk for chunk in self._heap.getChunks(self._mappings)]
    # DEBUG : delete replace by iterator
    allocsize = sum( [c[1] for c in chunks ])
    log.debug('\t+ %d chunks, for %d bytes'%( len(chunks), allocsize ) )
    #
    for chunk in chunks:
      log.debug( '\t\t- chunk @%0.8x size:%d'%(chunk[0], chunk[1]) )
    return chunks
  
  def _getFrontendChunks(self):
    fth_chunks = [ chunk for chunk in self._heap.getFrontendChunks(self._mappings)]
    # DEBUG : delete replace by iterator
    fth_allocsize = sum( [c[1] for c in fth_chunks ])
    log.debug('\t+ %d frontend chunks, for %d bytes'%( len(fth_chunks), fth_allocsize ) )
    #
    for chunk in fth_chunks:
      log.debug( '\t\t- fth_chunk @%0.8x size:%d'%(chunk[0], chunk[1]) )
    return fth_chunks

  def _getFreeLists(self):
    free_lists = [  ]
    last = 0
    free_lists = [ (freeblock_addr, size) for freeblock_addr, size in self._heap.getFreeLists(self._mappings)]
    free_lists.sort()
    return free_lists
  
  def _get_BlocksIndex(self):
    pass 
    


def getUserAllocations(mappings, heap, filterInUse=False,p1=1,p2=0):
  ''' list user allocations '''
  walker = Win7HeapWalker(mappings, heap, 0)
  for chunk_addr, chunk_size in walker.getUserAllocations():
    yield (chunk_addr, chunk_size)
  raise StopIteration

# TODO : 
#def getAllUserAllocations(mappings):
#def _init_Win7_MemoryMappings_Heaps(mappings):
#  found=[]
#  for mapping in self._mappings:
#    addr = mapping.start
#    heap = mapping.readStruct( addr, HEAP )
#    if addr in map(lambda x:x[0] , self._known_heaps):
#      self.assertTrue(  heap.loadMembers(self._mappings, -1), "We expected a valid hit at @%x"%(addr) )
#      found.append(addr, )
#    else:
#      try:
#        ret = heap.loadMembers(self._mappings, -1)
#        self.assertFalse( ret, "We didnt expected a valid hit at @%x"%(addr) )
#      except ValueError,e:
#        self.assertRaisesRegexp( ValueError, 'error while loading members')
#
#  found.sort()
#
# TODO : change the mappings file ?
#

def isHeap(mappings, mapping):
  """test if a mapping is a heap"""
  # todo check _heap.ProcessHeapsListIndex
  addr = mapping.start
  heap = mapping.readStruct( addr, win7heap.HEAP )
  load = heap.loadMembers(mappings, -1)
  return load

def readHeap(mappings, mapping):
  """ return a heap struct mapped on the mapping"""
  addr = mapping.start
  heap = mapping.readStruct( addr, win7heap.HEAP )
  return heap




