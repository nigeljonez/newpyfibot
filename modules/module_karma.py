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
        if u == 0:
            c.execute('delete from karma where word=?', t)
            conn.commit()
            return bot.say(channel, "%s no longer has karma and is garbage collected"  % (karma[0].encode('utf-8', 'replace')))
        else:
            q = (u,karma[0].lower(),)
            c.execute('update karma set karma = ? where word=?', q)
    else:
        u = k
        q = (karma[0].lower(),u,)
        c.execute('insert into karma (word, karma) VALUES (?,?)',q)
    
    conn.commit()
        
  
    return bot.say(channel, "%s now has %s karma"  % (karma[0].encode('utf-8', 'replace'), u))


def handle_privmsg(bot, user, reply, msg):
    """Grab karma changes from the messages and handle them"""

    m = re.findall('((?u)[\w.`\']+)(\+\+|\-\-)', msg.decode('utf-8'))
    if len(m) == 0 or len(m) >= 5: return None

    for k in m:
        do_karma(bot, user, reply, k)

    return

def handle_action(bot, user, reply, msg):
    """Grab karma changes from the messages and handle them"""

    m = re.findall('((?u)[\w.`\']+)(\+\+|\-\-)', msg.decode('utf-8'))    
    if len(m) == 0 or len(m) >= 5: return None

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

""" By request of eric, .rank = .karma """
def command_rank(bot, user, channel, args):
    return command_karma(bot, user, channel, args)

def command_srank(bot, user, channel, args):
    """ .srank <substring> """
    item = args.split()[0].decode("utf-8")

    conn = sqlite3.connect('karma.db')
    c = conn.cursor()
    t = item.lower()
    c.execute('select word,karma from karma where word like ? order by karma asc', ("%" + item + "%",))
    res = c.fetchall()
    if not len(res):
        return bot.say(channel, unicode("No matches for '*%s*'" % item).encode("utf-8"))
    max_len = 150
    ranks = []

    while len(res):
      new_rank = "%s (%d)" % res.pop()
      if len(", ".join(ranks)) + len(new_rank) < max_len:
        ranks.append(new_rank)
      else:
        break
      
    message = ", ".join(ranks)

    if len(res):
      message = message + " (%d omitted)" % len(res)

    return bot.say(channel, message.encode("utf-8"))



def command_topkarma(bot, user, channel, args):
    """.topkarma"""
    conn = sqlite3.connect('karma.db')
    c = conn.cursor()
    c.execute('select * from karma order by karma desc limit 5')

    for row in c:
        bot.say(channel, "Top 5: %s has %s karma" % (str(row[1]), row[2]))

    return
