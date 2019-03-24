from pyroute2.ndb.rtnl_object import RTNL_Object
from pyroute2.common import basestring
from pyroute2.netlink.rtnl.ifaddrmsg import ifaddrmsg


class Address(RTNL_Object):

    table = 'addresses'
    api = 'addr'
    summary = '''
              SELECT
                  a.f_target, a.f_tflags,
                  i.f_IFLA_IFNAME, a.f_IFA_ADDRESS, a.f_prefixlen
              FROM
                  addresses AS a
              INNER JOIN
                  interfaces AS i
              ON
                  a.f_index = i.f_index
                  AND a.f_target = i.f_target
              '''
    table_alias = 'a'
    summary_header = ('target', 'flags', 'ifname', 'address', 'mask')
    reverse_update = {'table': 'addresses',
                      'name': 'addresses_f_tflags',
                      'field': 'f_tflags',
                      'sql': '''
                          UPDATE interfaces
                          SET f_tflags = NEW.f_tflags
                          WHERE f_index = NEW.f_index AND
                                f_target = NEW.f_target;
                      '''}

    def __init__(self, *argv, **kwarg):
        kwarg['iclass'] = ifaddrmsg
        self.event_map = {ifaddrmsg: "load_rtnlmsg"}
        super(Address, self).__init__(*argv, **kwarg)

    def complete_key(self, key):
        if isinstance(key, dict):
            ret_key = key
        else:
            ret_key = {'target': 'localhost'}

        if isinstance(key, basestring):
            ret_key['IFA_ADDRESS'], ret_key['prefixlen'] = key.split('/')

        return super(Address, self).complete_key(ret_key)
