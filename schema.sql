CREATE TABLE karma (id INTEGER PRIMARY KEY UNIQUE, word TEXT, karma INT, user TEXT);
CREATE TABLE karmalog (id INTEGER PRIMARY KEY UNIQUE, word TEXT, user TEXT, lasttime INT);
