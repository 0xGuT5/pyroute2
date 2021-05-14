#!/usr/bin/env python
import subprocess

version_module = 'pyroute2.core/pr2modules/config/version.py'
version_file = 'VERSION'


def get_project_version():
    '''
    Get the project version
    '''
    try:
        version = (subprocess
                   .check_output(('git', 'describe'))
                   .decode('utf-8')
                   .strip()
                   .split('-'))
    except subprocess.CalledProcessError:
        version = ['unknown']

    if len(version) > 1:
        version = '{version[0]}.post{version[1]}'.format(**locals())
    else:
        version = version[0]
    return version


if __name__ == '__main__':
    version = get_project_version()
    with open(version_module, 'w') as f:
        f.write('__version__ = "%s"\n' % version)
    with open(version_file, 'w') as f:
        f.write('%s\n' % version)
