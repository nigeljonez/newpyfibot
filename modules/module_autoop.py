import sqlite3

def handle_userJoined(bot, user, channel):
    if isAdmin(user):
        nick = getNick(user)
        bot.log("auto-opping %s" % user)
        bot.mode(channel, True, 'o', user=nick)
    else:
        conn = sqlite3.connect('karma.db')
        c = conn.cursor()
        t = (user,)
        # Look for user in DB
        c.execute('select * from autoop where ? glob user', t)
        res = c.fetchone()

        if res == None:
            return

        type = res[2]
        nick = getNick(user)

        if type == 0:
            bot.mode(channel, True, 'o', user=nick)
        elif type == 1:
            bot.mode(channel, True, 'v', user=nick)

