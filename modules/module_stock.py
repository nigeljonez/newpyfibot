import urllib2
import csv

def command_stock(bot, user, channel, args):
    """.stock <ticker>"""
    ticker = args.split()[0]
    if ticker:
        res = csv.reader(urllib2.urlopen("http://download.finance.yahoo.com/d/quotes.csv?s=%s&f=sl1d1t1c1p2&e=.csv" % (ticker)).readlines()).next()
        if len(res) > 1:
            return bot.say(channel, "Market Data from Yahoo (at %s %s exchange time) %s %s %s (%s)" % (res[2], res[3], res[0], res[1], res[4], res[5]))
