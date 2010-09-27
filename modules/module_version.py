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
    githead = gitrepo.commits()[0]
    bot.say(channel, 'Currently running git commit %s (%s @ %s)' % (githead.id[:8], githead.author.name, time.asctime(githead.committed_date)))
