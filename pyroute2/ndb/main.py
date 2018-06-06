#
# NDB is NOT a production but a proof-of-concept
#
# It is intended to become IPDB version 2.0 that can handle
# thousands of network objects -- something that IPDB can not
# due to memory consupmtion
#
#
# Proposed design:
#
# 0. multiple event sources -- IPRoute (Linux), RTMSocket (BSD), etc
# 1. the main loop dispatches incoming events to plugins
# 2. plugins store serialized events as records in an internal DB (SQL)
# 3. plugins provide an API to access records as Python objects
# 4. objects are spawned only on demand
# 5. plugins provide transactional API to change objects + OS reflection
import json
import sqlite3
import logging
import threading
from socket import AF_INET
from socket import AF_INET6
from pyroute2 import IPRoute
from pyroute2.ndb import dbschema
from pyroute2.common import AF_MPLS
try:
    import queue
except ImportError:
    import Queue as queue


def target_adapter(value):
    return json.dumps(value)


sqlite3.register_adapter(list, target_adapter)


class ShutdownException(Exception):
    pass


class NDB(object):

    def __init__(self, nl=None, db_uri=':memory:'):

        self.db = None
        self.dbschema = None
        self._dbm_thread = None
        self._dbm_ready = threading.Event()
        self._global_lock = threading.Lock()
        self._event_queue = queue.Queue()
        self._nl = nl
        self._db_uri = db_uri
        self._src_threads = []
        self._dbm_ready.clear()
        self._dbm_thread = threading.Thread(target=self.__dbm__,
                                            name='NDB main loop')
        self._dbm_thread.start()
        self._dbm_ready.wait()

    def close(self):
        with self._global_lock:
            if self.db:
                self._event_queue.put(('localhost', (ShutdownException(), )))
                for src in self._src_threads:
                    src.nl.close()
                    src.join()
                self._dbm_thread.join()
                self.db.commit()
                self.db.close()

    def __initdb__(self):
        with self._global_lock:
            #
            # stop running sources, if any
            for src in self._src_threads:
                src.nl.close()
                src.join()
                self._src_threads = []
            #
            # start event sockets
            if self._nl is None:
                ipr = IPRoute()
                self.nl = {'localhost': ipr}
            elif isinstance(self._nl, dict):
                self.nl = dict([(x[0], x[1].clone()) for x
                                in self._nl.items()])
            else:
                self.nl = {'localhost': self._nl.clone()}
            for target in self.nl:
                self.nl[target].get_timeout = 300
                self.nl[target].bind(async_cache=True)
            #
            # close the current db
            if self.db:
                self.db.commit()
                self.db.close()
            #
            # ACHTUNG!
            # check_same_thread=False
            #
            # Do NOT write into the DB from ANY other thread
            # than self._dbm_thread!
            #
            self.db = sqlite3.connect(self._db_uri, check_same_thread=False)
            if self.dbschema:
                self.dbschema.db = self.db
            #
            # initial load
            evq = self._event_queue
            for (target, channel) in tuple(self.nl.items()):
                evq.put((target, channel.get_links(nlm_generator=True)))
                evq.put((target, channel.get_neighbours(nlm_generator=True)))
                evq.put((target, channel.get_routes(nlm_generator=True,
                                                    family=AF_INET)))
                evq.put((target, channel.get_routes(nlm_generator=True,
                                                    family=AF_INET6)))
                evq.put((target, channel.get_routes(nlm_generator=True,
                                                    family=AF_MPLS)))
                evq.put((target, channel.get_addr(nlm_generator=True)))
            #
            # start source threads
            for (target, channel) in tuple(self.nl.items()):

                def t(event_queue, target, channel):
                    while True:
                        msg = tuple(channel.get())
                        if msg[0]['header']['error'] and \
                                msg[0]['header']['error'].code == 104:
                                    return
                        event_queue.put((target, msg))

                th = threading.Thread(target=t,
                                      args=(self._event_queue,
                                            target,
                                            channel),
                                      name='NDB event source: %s' % (target))
                th.nl = channel
                th.start()
                self._src_threads.append(th)
            evq.put(('localhost', (self._dbm_ready, ), ))

    def __dbm__(self):

        # init the events map
        event_map = {type(self._dbm_ready): [lambda t, x: x.set()]}
        event_queue = self._event_queue

        def default_handler(target, event):
            if isinstance(event, Exception):
                raise event
            logging.warning('unsupported event ignored: %s' % type(event))

        self.__initdb__()

        self.dbschema = dbschema.init(self.db, id(threading.current_thread()))
        for (event, handler) in self.dbschema.event_map.items():
            if event not in event_map:
                event_map[event] = []
            event_map[event].append(handler)

        while True:
            target, events = event_queue.get()
            for event in events:
                handlers = event_map.get(event.__class__, [default_handler, ])
                for handler in handlers:
                    try:
                        handler(target, event)
                    except ShutdownException:
                        return
                    except:
                        import traceback
                        traceback.print_exc()
