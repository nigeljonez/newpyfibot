# -*- coding: utf-8 -*-

"""
Bot core

@author Riku 'Shrike' Lindblad (shrike@addiktit.net)
@copyright Copyright (c) 2004 Riku Lindblad
@license New-Style BSD
"""

# TODO:
# Maintenance task, remove already run items from tasks

# twisted imports
from twisted.words.protocols import irc
from twisted.internet import reactor, protocol, defer, threads
from twisted.python import rebuild

from types import FunctionType

import os, sys
import time
import string
import random
import urllib
import logging
from util import pyfiurl

# user matching
import fnmatch

# line splitting
import textwrap

__pychecker__ = 'unusednames=i, classattr'

log = logging.getLogger("bot")

class CoreCommands(object):
    def command_echo(self, user, channel, args):
        self.say(channel, "%s: %s" % (user, args))

    def command_ping(self, user, channel, args):
        self.say(channel, "%s: My current ping is %.0fms" % (self.factory.getNick(user), self.pingAve*100.0))

    def command_rehash(self, user, channel, args):
        """Reload modules. Usage: rehash [debug]"""

        if self.factory.isAdmin(user):
            try:
                # rebuild core & update
                log.info("rebuilding %r" % self)
                rebuild.updateInstance(self)

                self.factory._loadmodules()

            except Exception, e:
                self.say(channel, "Rehash error: %s" % e)
                log.error("Rehash error: "+e)
            else:
                self.say(channel, "Rehash OK")
                log.info("Rehash OK")

    def say(self, channel, message, length = None):
        """Must be implemented by the inheriting class"""
        raise NotImplementedError

    def command_join(self, user, channel, args):
        """Usage: join <channel>[@network] [password] - Join the specified channel"""

        if not self.factory.isAdmin(user):
            return

        password = None
        # see if we have multiple arguments
        try:
            args, password = args.split(' ', 1)
        except ValueError, e:
            pass
        
        # see if the user specified a network
        try:
            newchannel, network = args.split('@', 1)
        except ValueError, e:
            newchannel, network = args, self.network.alias
        try:
            bot = self.factory.allBots[network]
        except KeyError:
            self.say(channel, "I am not on that network.")
        else:
            log.debug("Attempting to join channel %s", channel)
            if newchannel in bot.network.channels:
                self.say(channel, "I am already in %s on %s." % (newchannel, network))
                log.debug("Already on channel %s" % channel)
                log.debug("Channels I'm on this network: %s" % bot.network.channels)
            else:
                if password:
                    bot.join(newchannel, key=password)
                    log.debug("Joined")
                else:
                    bot.join(newchannel)
                    log.debug("Joined")

    # alias of part
    def command_leave(self, user, channel, args):
        """Usage: leave <channel>[@network] - Leave the specified channel"""
        self.command_part(user, channel, args)
        
    def command_part(self, user, channel, args):
        """Usage: part <channel>[@network] - Leave the specified channel"""

        if not self.factory.isAdmin(user):
            return

        # part what and where?
        try:
            newchannel, network = args.split('@', 1)
        except ValueError, e:
            newchannel, network = args, self.network.alias

        # get the bot instance for this chat network
        try:
            bot = self.factory.allBots[network]
        except KeyError:
            self.say(channel, "I am not on that network.")
        else:
            if newchannel not in bot.network.channels:
                self.say(channel, "I am not in %s on %s." % (newchannel, network))
                self.say(channel, "I am on %s" % bot.network.channels)
            else:
                bot.network.channels.remove(newchannel)
                bot.part(newchannel)
            
    def command_quit(self, user, channel, args):
        """Usage: logoff - Leave this network"""

        if not self.factory.isAdmin(user):
            return

        self.quit("Working as programmed")
        self.hasQuit = 1

    def command_channels(self, user, channel, args):
        """Usage: channels <network> - List channels the bot is on"""
        if not args: 
            self.say(channel, "Please specify a network")
            return
        bot = self.factory.allBots[args]
        self.say(channel, "I am on %s" % self.network.channels)

    def command_help(self, user, channel, cmnd):
        """Get help on all commands or a specific one. Usage: help [<command>]"""

        commands = []
        for module, env in self.factory.ns.items():
            myglobals, mylocals = env
            commands += [(c.replace("command_", ""),ref) for c,ref in mylocals.items() if c.startswith("command_%s" % cmnd)]
        
        # help for a specific command
        if len(cmnd) > 0:
            for cname, ref in commands:
                if cname == cmnd:
                    helptext = ref.__doc__.split("\n", 1)[0]
                    self.say(channel, "Help for %s: %s" % (cmnd, helptext))
                    return
        # generic help
        else:
            commandlist = ", ".join([c for c, ref in commands])
            
            self.say(channel, "Available commands: %s" % commandlist)
                                                                                        
class PyFiBot(irc.IRCClient, CoreCommands):
    """PyFiBot"""

    nickname = "pyfibot"
    realname = "http://code.google.com/p/pyfibot/"

    # send 1 msg per second max
    lineRate = 1
    
    hasQuit = False

    CMDCHAR = "."
    IGNORECHAR = "^"

    # Rolling ping time average
    pingAve = 0.0
        
    def __init__(self, network):
        self.network = network
        self.nickname = self.network.nickname
        self.realname = self.network.realname
        self.password = self.network.password

        # text wrapper to clip overly long answers
        self.tw = textwrap.TextWrapper(width=400, break_long_words=True)
        
        log.info("bot initialized")


    def __repr__(self):
        return 'PyFiBot(%r, %r)' % (self.nickname, self.network.address)

    ###### CORE 

    def printResult(self, msg, info):
        # Don't print results if there is nothing to say (usually non-operation on module)
        if msg:
            log.debug("Result %s %s" % (msg, info))
    
    def printError(self, msg, info):
        log.error("ERROR %s %s" % (msg, info))

    def connectionMade(self):
        irc.IRCClient.connectionMade(self)
        self.repeatingPing(300)
        log.info("connection made")
            
    def connectionLost(self, reason):
        irc.IRCClient.connectionLost(self, reason)
        log.info("connection lost:", reason)
        
    def signedOn(self):
        """Called when bot has succesfully signed on to server."""

        # QNet specific auth & ip hiding
        if self.network.alias == "quakenet":
            log.info("I'm on quakenet, authenticating...")
            self.mode(self.nickname, '+', 'x') # Hide ident
            authname = self.factory.config['networks']['quakenet'].get('authname', None)
            authpass = self.factory.config['networks']['quakenet'].get('authpass', None)
            if not authname or not authpass:
                log.info("authname or authpass not found, authentication aborted")
            else:
                self.say("Q@CServe.quakenet.org", "AUTH %s %s" % (authname, authpass))
                log.info("Auth sent.")
        
        for chan in self.network.channels:
            # defined as a tuple, channel has a key
            if type(chan) == list:
                self.join(chan[0], key=chan[1])
            else:
                self.join(chan)

        log.info("joined %d channel(s): %s" % (len(self.network.channels), ", ".join(self.network.channels)))

    def pong(self, user, secs):
        self.pingAve = ((self.pingAve * 5) + secs) / 6.0

    def repeatingPing(self, delay):
        reactor.callLater(delay, self.repeatingPing, delay)
        self.ping(self.nickname)

    def say(self, channel, message, length = None):
        """Override default say to make replying to private messages easier"""
        # wrap long text into suitable fragments
        msg = self.tw.wrap(message)

        cont = False
        
        for m in msg:
            if cont: m = "..."+m
            if length == None: self.msg(channel, m)
            else: self.msg(channel, m, length)
            cont = True

        return ('botcore.say', channel, message)

    def log(self, message):
        botId = "%s@%s" % (self.nickname, self.network.alias)
        log.info("%s: %s", botId, message)

    ###### COMMUNICATION

    def privmsg(self, user, channel, msg):
        """This will get called when the bot receives a message.
        
        @param user: nick!user@host
        @param channel: Channel where the message originated from
        @param msg: The actual message
        """

        if self.factory.isIgnored(user):
            return


        channel = channel.lower()

        lmsg = msg.lower()
        lnick = self.nickname.lower()
        nickl = len(lnick)
        
        #self.log("<%s|%s> %s" % (self.getNick(user), channel, msg))

        if channel == lnick:
            # Turn private queries into a format we can understand
            if not msg.startswith(self.CMDCHAR):
                msg = self.CMDCHAR + msg
            elif lmsg.startswith(lnick):
                msg = self.CMDCHAR + msg[nickl:].lstrip()
            elif lmsg.startswith(lnick) and len(lmsg) > nickl and lmsg[nickl] in string.punctuation:
                msg = self.CMDCHAR + msg[nickl + 1:].lstrip()
        else:
            # Turn 'nick:' prefixes into self.CMDCHAR prefixes
            if lmsg.startswith(lnick) and len(lmsg) > nickl and lmsg[nickl] in string.punctuation:
                msg = self.CMDCHAR + msg[len(self.nickname) + 1:].lstrip()
                
        reply = (channel == lnick) and user or channel

        if msg.startswith(self.CMDCHAR):
            cmnd = msg[len(self.CMDCHAR):]
            self._command(user, reply, cmnd)

        if not msg.startswith(self.IGNORECHAR):
            # run privmsg handlers
            self._runhandler("privmsg", user, reply, msg)

            # run URL handlers
            urls = pyfiurl.grab(msg)
            if urls:
                for url in urls:
                    self._runhandler("url", user, reply, url, msg)
                                                        
    def _runhandler(self, handler, *args, **kwargs):
        """Run a handler for an event"""
        handler = "handle_%s" % handler
        # module commands
        for module, env in self.factory.ns.items():
            myglobals, mylocals = env
            # find all matching command functions
            handlers = [(h,ref) for h,ref in mylocals.items() if h == handler and type(ref) == FunctionType]

            for hname, func in handlers:
                # defer each handler to a separate thread, assign callbacks to see when they end
                # TODO: Profiling: add time.time() to callback params, calculate difference
                d = threads.deferToThread(func, self, *args, **kwargs)
                d.addCallback(self.printResult, "handler %s completed" % hname)
                d.addErrback(self.printError, "handler %s error" % hname)
            
    def _command(self, user, channel, cmnd):
        """Handles bot commands.

        This function calls the appropriate method for the given command.

        The command methods are formatted as "command_<commandname>"
        """
        # split arguments from the command part        
        try:
            cmnd, args = cmnd.split(" ", 1)
        except ValueError:
            args = ""

        if self.factory.isIgnored(user):
            log.info("command %s called by ignored user %s" % (cmnd, user))
            return

        # core commands
        method = getattr(self, "command_%s" % cmnd, None)
        if method is not None:
            log.info("internal command %s called by %s (%s) on %s" % (cmnd, user, self.factory.isAdmin(user), channel))
            method(user, channel, args)
            return

        # module commands
        for module, env in self.factory.ns.items():
            myglobals, mylocals = env
            # find all matching command functions
            commands = [(c,ref) for c,ref in mylocals.items() if c == "command_%s" % cmnd]

            for cname, command in commands:
                log.info("module command %s called by %s (%s) on %s" % (cname, user, self.factory.isAdmin(user), channel))
                # Defer commands to threads
                d = threads.deferToThread(command, self, user, channel, args)
                d.addCallback(self.printResult, "command %s completed" % cname)
                d.addErrback(self.printError, "command %s error" % cname)

    ### LOW-LEVEL IRC HANDLERS ###

    def irc_JOIN(self, prefix, params):
        """override the twisted version to preserve full userhost info"""
        
        nick = self.factory.getNick(prefix)
        channel = params[-1]

        if nick == self.nickname:
            self.joined(channel)
        else:
            self.userJoined(prefix, channel)

        if nick.lower() != self.nickname.lower():
            pass
        elif channel not in self.network.channels:
            self.network.channels.append(channel)
            self.factory.setNetwork(self.network)

    def irc_PART(self, prefix, params):
        """override the twisted version to preserve full userhost info"""

        nick = self.factory.getNick(prefix)
        channel = params[0]

        if nick == self.nickname:
            self.left(channel)
        else:
            # some clients don't send a part message at all, compensate
            if len(params) == 1: params.append("")
            self.userLeft(prefix, channel, params[1])
        
    def irc_QUIT(self, prefix, params):
        """QUIT-handler.

        Twisted IRCClient doesn't handle this at all.."""

        nick = self.factory.getNick(prefix)
        if nick == self.nickname:
            self.left(channel)
        else:
            self.userLeft(prefix, None, params[0])

    ###### HANDLERS ######

    ## ME
        
    def joined(self, channel):
        """I joined a channel"""
        self._runhandler("joined", channel)
        
    def left(self, channel):
        """I left a channel"""
        self._runhandler("left", channel)

    def noticed(self, user, channel, message):
        """I received a notice"""
        self._runhandler("noticed", user, channel, message)

    def modeChanged(self, user, channel, set, modes, args):
        """Mode changed on user or channel"""
        self._runhandler("modeChanged", user, channel, set, modes, args)
        
    def kickedFrom(self, channel, kicker, message):
        """I was kicked from a channel"""
        self._runhandler("kickedFrom", channel, kicker, message)

    def nickChanged(self, nick):
        """I changed my nick"""
        self._runhandler("nickChanged", nick)

    ## OTHER PEOPLE
    
    def userJoined(self, user, channel):
        """Someone joined"""
        self._runhandler("userJoined", user, channel)

    def userLeft(self, user, channel, message):
        """Someone left"""
        self._runhandler("userLeft", user, channel, message)

    def userKicked(self, kickee, channel, kicker, message):
        """Someone got kicked by someone"""
        self._runhandler("userKicked", kickee, channel, kicker, message)

    def action(self, user, channel, data):
        """An action"""
        self._runhandler("action", user, channel, data)

    def topicUpdated(self, user, channel, topic):
        """Save topic to maindb when it changes"""        
        self._runhandler("topicUpdated", user, channel, topic)

    def userRenamed(self, oldnick, newnick):
        """Someone changed their nick"""
        self._runhandler("userRenamed", oldnick, newnick)

    def receivedMOTD(self, motd):
        """MOTD"""
        self._runhandler("receivedMOTD", motd)

    ## SERVER INFORMATION

    ## Network = Quakenet -> do Q auth
    def isupport(self, options):
        log.info(self.network.alias+" SUPPORTS: "+",".join(options))

    def created(self, when):
        log.info(self.network.alias+" CREATED: "+when)

    def yourHost(self, info):
        log.info(self.network.alias+" YOURHOST: "+info)

    def myInfo(self, servername, version, umodes, cmodes):
        log.info(self.network.alias+" MYINFO: %s %s %s %s" % (servername, version, umodes, cmodes))

    def luserMe(self, info):
        log.info(self.network.alias+" LUSERME: "+info)
