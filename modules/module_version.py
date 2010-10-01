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
    if git.__version__ > '0.2.0':
        githead = gitrepo.iter_commits().next()
        date = time.ctime(githead.committed_date)
    else:
        githead = gitrepo.commits()[0]
        date = time.asctime(githead.committed_date)
    author = githead.author.name
    bot.say(channel, 'Currently running git commit %s (%s @ %s)' % (str(githead)[:8], author, date))
