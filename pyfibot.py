#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
A modular python bot based on the twisted matrix irc library

@author Riku 'Shrike' Lindblad (shrike@addiktit.net)
@copyright Copyright (c) 2006 Riku Lindblad
@license New-Style BSD
"""

import re
import sys
import os.path
import time
import urllib
import fnmatch
import HTMLParser
import logging
import logging.handlers

try:
    import psyco
    psyco.full()
except ImportError:
    print "Psyco not found, running unoptimized"

try:
    import yaml
except ImportError:
    print "PyYAML not found, please install from http://pyyaml.org/wiki/PyYAML"
    sys.exit(1)

# twisted imports
try:
    from twisted.words.protocols import irc
    from twisted.internet import reactor, protocol, threads, defer
    from twisted.python import rebuild
except ImportError:
    print "Twisted library not found, please install Twisted from http://twistedmatrix.com/products/download"
    sys.exit(1)

from util import *
from util.BeautifulSoup import BeautifulSoup
from util.BeautifulSoup import UnicodeDammit

# default timeout for socket connections
import socket
socket.setdefaulttimeout(20)

import botcore

log = logging.getLogger('core')


class URLCacheItem(object):
    """URL cache item object, fetches data only when needed"""
    
    def __init__(self, url):
        self.url = url
        self.content = None
        self.headers = None
        self.bs = None
        # maximum size in kB to download
        self.max_size = 2048
        self.fp = None

    def _open(self, url):
        """Returns the raw file pointer to the given URL"""
        if not self.fp:
            urllib._urlopener = BotURLOpener()
            try:
                self.fp = urllib.urlopen(self.url)
            except IOError, e:
                log.warn("IOError when opening url %s" % url)
        return self.fp

    def _checkstatus(self):
        """Check if all data has already been cached and close socket if so"""
        
        if self.content and \
           self.headers and \
           self.bs:
            self.fp.close()

    def getSize(self):
        """Get the content length of URL in kB

        @return None if the server doesn't return a content-length header"""
        if self.getHeaders().has_key('content-length'):
            length = int(self.getHeaders()['content-length'])/1024
            return length
        else:
            return None

    def getContent(self):
        """Get the actual file at the URL

        @return None if the file is too large (over 2MB)"""
        if not self.content:
            f = self._open(self.url)

            size = self.getSize()
            if size > self.max_size:
                log.warn("CONTENT TOO LARGE, WILL NOT FETCH %s %s" % (size, self.url))
                self.content = None
            else:
                if self.checkType():
                    self.content = UnicodeDammit(f.read()).unicode
                else:
                    type = self.getHeaders().getsubtype()
                    log.warn("WRONG CONTENT TYPE, WILL NOT FETCH %s, %s, %s" % (size, type, self.url))

        self._checkstatus()

        return self.content

    def getHeaders(self):
        """Get headers for the URL"""
        
        if not self.headers:
            f = self._open(self.url)
            if f:
                self.headers = f.info()
            else:
                self.headers = {}
        
        self._checkstatus()
        return self.headers

    def checkType(self):
        if self.getHeaders().getsubtype() in ['html', 'xml', 'xhtml+xml', 'atom+xml']:
            return True
        else:
            return False

    def getBS(self):
        """Get a beautifulsoup instance for the URL

        @return None if the url doesn't contain HTML
        """
        
        if not self.bs:
            # only attempt a bs parsing if the content is html, xml or xhtml
            if self.getHeaders().has_key('content-type') and \
            self.getHeaders().getsubtype() in ['html', 'xml', 'xhtml+xml', 'atom+xml']:
                try:
                    bs = BeautifulSoup(markup=self.getContent())
                except HTMLParser.HTMLParseError:
                    log.warn("BS unable to parse content")
                    return None
                self.bs = bs
            else:
                return None
            
        self._checkstatus()
        return self.bs

class BotURLOpener(urllib.FancyURLopener):
    """URL opener that fakes itself as Firefox and ignores all basic auth prompts"""
    
    def __init__(self, *args):
        # Firefox 1.0PR on w2k
        self.version = "Mozilla/5.0 (Windows; U; Windows NT 6.0; en-US) AppleWebKit/534.0 (KHTML, like Gecko) Chrome/6.0.408.1 Safari/534.0"
        urllib.FancyURLopener.__init__(self, *args)

    def prompt_user_passwd(self, host, realm):
        log.info("PASSWORD PROMPT:", host, realm)
        return ('', '')

class Network:
    def __init__(self, root, alias, address, nickname, realname, channels = None):
        self.alias = alias                         # network name
        self.address = address                     # server address
        self.nickname = nickname                   # nick to use
        self.realname = realname                   # nick to use
        self.channels = channels or {}             # channels to join

        # create network specific save directory
        p = os.path.join(root, alias)
        if not os.path.isdir(p):
            os.mkdir(p)

    def __repr__(self):
        return 'Network(%r, %r)' % (self.alias, self.address)

class InstantDisconnectProtocol(protocol.Protocol):
    def connectionMade(self):
        self.transport.loseConnection()

class ThrottledClientFactory(protocol.ClientFactory):
    """Client factory that inserts a slight delay to connecting and reconnecting"""
    
    lostDelay = 10
    failedDelay = 60
    
    def clientConnectionLost(self, connector, reason):
        #print connector
        log.info("connection lost (%s): reconnecting in %d seconds" % (reason, self.lostDelay))
        reactor.callLater(self.lostDelay, connector.connect)
        
    def clientConnectionFailed(self, connector, reason):
        #print connector
        log.info("connection failed (%s): reconnecting in %d seconds" % (reason, self.failedDelay))
        reactor.callLater(self.failedDelay, connector.connect)
                                                                        
class PyFiBotFactory(ThrottledClientFactory):
    """python.fi bot factory"""

    version = "20091115.0"

    protocol = botcore.PyFiBot
    allBots = None
    moduledir = os.path.join(sys.path[0], "modules/")
    startTime = None
    config = None

    def __init__(self, config):
        """Initialize the factory"""

        self.config = config
        self.data = {}
        self.data['networks'] = {}
        self.ns = {}

        # cache url contents for 5 minutes, check for old entries every minute
        self._urlcache = timeoutdict.TimeoutDict(timeout=300, pollinterval=60)

        if not os.path.exists("data"):
            os.mkdir("data")
                        
    def startFactory(self):
        self.allBots = {}
        self.starttime = time.time()

        self._loadmodules()

        ThrottledClientFactory.startFactory(self)

        log.info("factory started")

    def stopFactory(self):

        del self.allBots
        #self.data.close()
        
        ThrottledClientFactory.stopFactory(self)        
        log.info("factory stopped")
        reactor.stop()
        
    def buildProtocol(self, address):
        if re.match("[^a-z]+", address.host):
            log.error("Kludge fix for twisted.words weirdness")
            fqdn = socket.getfqdn(address.host)
            address = (fqdn, address.port)
        else:
            address = (address.host, address.port)

        # do we know how to connect to the given address?
        for n in self.data['networks'].values():
            # a server can have multiple DNS CNAME records (like irc.freenode.net)
            aliases = socket.getaddrinfo(n.address[0], n.address[1], socket.AF_INET, socket.SOCK_STREAM)
            # alias is a tupel: (family, socktype, proto, canonname, sockaddr)
            aliases = [a[4][0] for a in aliases]
            if socket.gethostbyname(address[0]) in aliases:
                break
        else:
            log.info("unknown network address: " + repr(address))
            return InstantDisconnectProtocol()

        p = self.protocol(n)
        self.allBots[n.alias] = p
        p.factory = self
        return p

    def createNetwork(self, address, alias, nickname, realname, channels = None):
        self.setNetwork(Network("data", alias, address, nickname, realname, channels))
                
    def setNetwork(self, net):
        nets = self.data['networks']
        nets[net.alias] = net
        self.data['networks'] = nets

    def clientConnectionLost(self, connector, reason):
        """Connection lost for some reason"""
        log.info("connection to %s lost" % str(connector.getDestination().host))

        # find bot that connects to the address that just disconnected
        for n in self.data['networks'].values():
            dest = connector.getDestination()
            if (dest.host, dest.port) == n.address:
                if self.allBots.has_key(n.alias):
                    # did we quit intentionally?
                    if not self.allBots[n.alias].hasQuit:
                        # nope, reconnect
                        ThrottledClientFactory.clientConnectionLost(self, connector, reason)
                    del self.allBots[n.alias]
                    return
                else:
                    log.info("No active connection to known network %s" % n.address[0])

    def _finalize_modules(self):
        """Call all module finalizers"""
        for module in self._findmodules():
            # if rehashing (module already in namespace), finalize the old instance first
            if self.ns.has_key(module):
                if self.ns[module][0].has_key('finalize'):
                    log.info("finalize - %s" % module)
                    self.ns[module][0]['finalize']()


    def _loadmodules(self):
        """Load all modules"""
        self._finalize_modules()
        
        for module in self._findmodules():

            env = self._getGlobals()
            log.info("load module - %s" % module)
            # Load new version of the module
            execfile(os.path.join(self.moduledir, module), env, env)
            # initialize module
            if env.has_key('init'):
                log.info("initialize module - %s" % module)
                env['init'](self.config)
            
            # add to namespace so we can find it later
            self.ns[module] = (env, env)

    def _findmodules(self):
        """Find all modules"""
        modules = [m for m in os.listdir(self.moduledir) if m.startswith("module_") and m.endswith(".py")]
        return modules

    def _getGlobals(self):
        """Global methods for modules"""
        g = {}

        g['getUrl'] = self.getUrl
        g['getNick'] = self.getNick
        g['isAdmin'] = self.isAdmin
        g['isIgnored'] = self.isIgnored
        return g

    def getUrl(self, url, nocache=False):
        """Gets data, bs and headers for the given url, using the internal cache if necessary"""
        
        if self._urlcache.has_key(url) and not nocache:
            log.info("cache hit : %s" % url)
        else:
            if nocache:
                log.info("cache pass: %s" % url)
            else:
                log.info("cache miss: %s" % url)
            self._urlcache[url] = URLCacheItem(url)
            
        return self._urlcache[url]

    def getNick(self, user):
        """Parses nick from nick!user@host
        
        @type user: string
        @param user: nick!user@host
        
        @return: nick"""
        return user.split('!', 1)[0]

    def isAdmin(self, user):
        """Check if an user has admin privileges.
        
        @return: True or False"""
    
        for pattern in self.config['admins']:
            if fnmatch.fnmatch(user, pattern):
                return True
        
        return False

    def isIgnored(self, user):
        """Check if an user is ignored

        @return: True or False"""

        if self.config.has_key('ignores'):
            for pattern in self.config['ignores']:
                if fnmatch.fnmatch(user, pattern):
                    return True

        return False

def create_example_conf():
    """Create an example configuration file"""
    
    conf = """
    nick: botnick
    realname: https://github.com/nigeljonez/newpyfibot
    bindip: 0.0.0.0

    admins:
      - 'foo!bar@example.com'
    
    ignores:
      - 'bar!foo@example.com'
        
    networks:
      ircnet:
        server: irc.ircnet.com
        channels:
          - mychannel
      quakenet:
        server: irc.quakenet.org
        authname: name
        authpass: password
        channels:
          - (mysecret, password)
    """

    examplefile = 'bot.config.example'
    if os.path.exists(examplefile):
        return False
    else:
        f = file(examplefile, 'w')
        yaml.dump(yaml.load(conf), f, default_flow_style=False)
        f.close()
        return True


def init_logging():
    filename = os.path.join(sys.path[0], 'pyfibot.log')
    # get root logger
    logger = logging.getLogger()
    if False:
        handler = logging.handlers.RotatingFileHandler(filename, maxBytes=5000*1024, backupCount=20)
    else:
        handler = logging.StreamHandler()
    # time format is same format of strftime
    formatter = logging.Formatter('%(asctime)-15s %(levelname)-8s %(name)-11s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

if __name__ == '__main__':

    init_logging()

    sys.path.append(os.path.join(sys.path[0], 'lib'))

    config = os.path.join(sys.path[0], "bot.config")
    
    if os.path.exists(config):
        config = yaml.load(file(config))
    else:
        if create_example_conf():
            print "No config file found, I created an example config (bot.config.example) for you. Please edit it and rename to bot.config."
        else:
            print 'No config file found, there is an example config (bot.config.example) for you. Please edit it and rename to bot.config or delete it to generate a new example config.'
        sys.exit(1)

    if config.has_key('bindip'):
        bindip = config['bindip']
    else:
        bindip = "0.0.0.0"

    factory = PyFiBotFactory(config)
    for network, settings in config['networks'].items():
        # use network specific nick or realname if one has been configured
        if settings.has_key('nick'):
            nick = settings['nick']
        elif config.has_key('nick'):
            nick = config['nick']
        else:
            nick = "pyfibot"

        if settings.has_key('realname'):
            realname = settings['realname']
        elif config.has_key('realname'):
            realname = config['realname']
        else:
            realname = "http://code.google.com/p/pyfibot/"

        # prevent internal confusion with channels
        chanlist = []
        for channel in settings['channels']:
            if channel[0] not in '&#!+^': channel = '#' + channel
            # The following is to get around an annoying yaml/freenode thing w/ ## channels
            chanlist.append(re.sub('\^', '#', channel))

	port = 6667
	try:
	    port = int(settings.get('port'))
	except:
	    pass
        factory.createNetwork((settings['server'], port), network, nick, realname, chanlist)
        reactor.connectTCP(settings['server'], port, factory, bindAddress=(bindip, 0))
        
    reactor.run()
