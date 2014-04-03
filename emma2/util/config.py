'''
The Emma2 configuration module reads several config files to build its final
set of settings. It searches for the file 'emma2.cfg' in several locations with
different priorities:
1. $CWD/emma2.cfg
2. /etc/emma2.cfg
3. ~/emma2.cfg
4. $PYTHONPATH/Emma2/emma2.cfg (always taken as default configuration file)

The default values are stored in later file to ensure these values are always
defined. This is preferred over hardcoding them somewhere in the python code.

Created on 31.03.2014

@author: marscher
'''
import ConfigParser
import os
import pkg_resources

__all__ = ['configParser', 'used_filenames', 'AttribStore']

configParser = None

class AttribStore(dict):
    def __getattr__(self, name):
        return self[name]

    def __setattr__(self, name, value):
        self[name] = value

def readConfiguration():
    global configParser, used_filenames
    """ this filenames are being tried to read to obtain basic configuration values 
        for the logging system."""
        
    # use these files to extend/overwrite the config.
    # Last red files always overwrites existing values!
    cfg = 'emma2.cfg'
    filenames = [cfg, # config in current dir
                '/etc/' + cfg, # config in global installation
                os.path.join(os.path.expanduser('~' + os.path.sep), cfg), # config in user dir
                ]
    
    # read defaults from default_emma2_conf first.
    defParser = ConfigParser.RawConfigParser()
    default_emma2_conf = \
        os.path.abspath(pkg_resources.resource_filename('emma2', os.path.join('..', 'emma2.cfg')))
    
    try:
        with open(default_emma2_conf) as f:
            defParser.readfp(f, default_emma2_conf)
    except EnvironmentError as e:
        print("FATAL ERROR: could not read default configuration file %s\n%s"
              % (default_emma2_conf, e))
        import sys
        sys.exit(-1)
    
    # store values of defParser in configParser with sections
    configParser = ConfigParser.SafeConfigParser()
    for section in defParser.sections():
        configParser.add_section(section)
        for item in defParser.items(section):
            configParser.set(section, item[0], item[1])
            
    """ this is a list of used configuration filenames during parsing the configuration"""
    used_filenames = configParser.read(filenames)

readConfiguration()