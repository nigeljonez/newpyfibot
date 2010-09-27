has_pygit = False

try:
     import git
     has_pygit = True
except:
     print('Error loading python-git')

import time

def command_version(bot, user, channel, args):
    if not has_pygit:
        return bot.say(channel, 'Version unknown')

    gitrepo = git.Repo(".")
    githead = gitrepo.iter_commits().next()
    author = githead.author.name
    date = time.ctime(githead.committed_date)
    bot.say(channel, 'Currently running git commit %s (%s @ %s)' % (str(githead)[:8], author, date))
