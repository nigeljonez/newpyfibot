import re
import sqlite3

def do_karma(bot, user, channel, karma):
    if karma[1] == '++':
        k = 1
    else:
        k = -1

    conn = sqlite3.connect('karma.db')
    c = conn.cursor()
    t = (karma[0].lower(),)
    c.execute('select * from karma where word=?', t)
    res = c.fetchone()

    if res != None:
        u = k + res[2]
        q = (u,karma[0].lower(),)
        c.execute('update karma set karma = ? where word=?', q)
    else:
        u = k
        q = (karma[0].lower(),u,)
        c.execute('insert into karma (word, karma) VALUES (?,?)',q)
    
    conn.commit()
        
  
    return bot.say(channel, "%s now has %s karma" % (karma[0], u))


def handle_privmsg(bot, user, reply, msg):
    """Grab karma changes from the messages and handle them"""

    m = re.findall('([a-zA-Z0-9.]*)(\+\+|\-\-)', msg)
    if len(m) == 0: return None

    for k in m:
        do_karma(bot, user, reply, k)

    return

def handle_action(bot, user, reply, msg):
    """Grab karma changes from the messages and handle them"""

    m = re.findall('([a-zA-Z0-9.]*)(\+\+|\-\-)', msg)
    if len(m) == 0: return None

    for k in m:
        do_karma(bot, user, reply, k)

    return

def command_karma(bot, user, channel, args):
    """.karma <item>"""
    item = args.split()[0]
    conn = sqlite3.connect('karma.db')
    c = conn.cursor()
    t = (item.lower(),)
    c.execute('select * from karma where word=?', t)
    res = c.fetchone()

    if res != None:
        return bot.say(channel, "%s currently has %s karma" % (item, res[2]))
    else:
        return bot.say(channel, "%s has no karma" % (item))

def command_topkarma(bot, user, channel, args):
    """.topkarma"""
    conn = sqlite3.connect('karma.db')
    c = conn.cursor()
    c.execute('select * from karma order by karma desc limit 5')

    for row in c:
        bot.say(channel, "Top 5: %s has %s karma" % (str(row[1]), row[2]))

    return
