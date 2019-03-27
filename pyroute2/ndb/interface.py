import weakref
from pyroute2.ndb.rtnl_object import RTNL_Object
from pyroute2.common import basestring
from pyroute2.netlink.rtnl.ifinfmsg import ifinfmsg


class Interface(RTNL_Object):

    table = 'interfaces'
    msg_class = ifinfmsg
    api = 'link'
    key_extra_fields = ['IFLA_IFNAME']
    summary = '''
              SELECT
                  a.f_target, a.f_tflags, a.f_index, a.f_IFLA_IFNAME,
                  a.f_IFLA_ADDRESS, a.f_flags
              FROM
                  interfaces AS a
              '''
    table_alias = 'a'
    summary_header = ('target', 'flags', 'index', 'ifname', 'lladdr', 'flags')

    def __init__(self, *argv, **kwarg):
        kwarg['iclass'] = ifinfmsg
        self.event_map = {ifinfmsg: "load_rtnlmsg"}
        dict.__setitem__(self, 'flags', 0)
        dict.__setitem__(self, 'state', 'unknown')
        if isinstance(argv[1], dict) and argv[1].get('create'):
            if 'ifname' not in argv[1]:
                raise Exception('specify at least ifname')
        super(Interface, self).__init__(*argv, **kwarg)
        self.ipaddr = (self
                       .view
                       .ndb
                       ._get_view('addresses',
                                  match_src=[weakref.proxy(self),
                                             {'index':
                                              self.get('index', 0)}],
                                  match_pairs={'index': 'index'}))
        self.ports = (self
                      .view
                      .ndb
                      ._get_view('interfaces',
                                 match_src=[weakref.proxy(self),
                                            {'index':
                                             self.get('index', 0)}],
                                 match_pairs={'master': 'index'}))
        self.routes = (self
                       .view
                       .ndb
                       ._get_view('routes',
                                  match_src=[weakref.proxy(self),
                                             {'index':
                                              self.get('index', 0)}],
                                  match_pairs={'oif': 'index'}))
        self.neighbours = (self
                           .view
                           .ndb
                           ._get_view('neighbours',
                                      match_src=[weakref.proxy(self),
                                                 {'index':
                                                  self.get('index', 0)}],
                                      match_pairs={'ifindex': 'index'}))

    def complete_key(self, key):
        if isinstance(key, dict):
            ret_key = key
        else:
            ret_key = {'target': 'localhost'}

        if isinstance(key, basestring):
            ret_key['ifname'] = key
        elif isinstance(key, int):
            ret_key['index'] = key

        return super(Interface, self).complete_key(ret_key)

    def snapshot(self, ctxid=None):
        with self.schema.db_lock:
            # 1. make own snapshot
            snp = super(Interface, self).snapshot(ctxid=ctxid)
            # 2. collect dependencies and store in self.snapshot_deps
            for spec in (self
                         .schema
                         .get('interfaces', {'IFLA_MASTER': self['index']})):
                # bridge ports
                link = type(self)(self.view, spec)
                snp.snapshot_deps.append((link, link.snapshot()))
            for spec in (self
                         .schema
                         .get('interfaces', {'IFLA_LINK': self['index']})):
                # vlans
                link = Vlan(self.view, spec)
                snp.snapshot_deps.append((link, link.snapshot()))
            # return the root node
            return snp

    def make_req(self, prime):
        req = super(Interface, self).make_req(prime)
        if self.state == 'system':  # --> link('set', ...)
            req['master'] = self['master']
        return req

    def load_sql(self, *argv, **kwarg):
        super(Interface, self).load_sql(*argv, **kwarg)
        self.load_value('state', 'up' if self['flags'] & 1 else 'down')

    def load_rtnl(self, *argv, **kwarg):
        super(Interface, self).load_rtnl(*argv, **kwarg)
        self.load_value('state', 'up' if self['flags'] & 1 else 'down')


class Bridge(Interface):

    table = 'bridge'
    utable = 'interfaces'
    summary = '''
              SELECT
                  f_target, f_index, f_IFLA_IFNAME,
                  f_IFLA_ADDRESS, f_IFLA_BR_STP_STATE,
                  f_IFLA_BR_VLAN_FILTERING
              FROM
                  bridge
              '''
    summary_header = ('target', 'index', 'ifname',
                      'lladdr', 'stp', 'vlan_filtering')


class Vlan(Interface):

    table = 'vlan'
    utable = 'interfaces'
    summary = '''
              SELECT
                  f_target, f_index, f_IFLA_IFNAME,
                  f_IFLA_ADDRESS, f_IFLA_LINK, f_IFLA_VLAN_ID
              FROM
                  vlan
              '''
    summary_header = ('target', 'index', 'ifname',
                      'lladdr', 'master', 'vlan')
