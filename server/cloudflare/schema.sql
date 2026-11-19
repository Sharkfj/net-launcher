CREATE TABLE IF NOT EXISTS users (name TEXT PRIMARY KEY COLLATE NOCASE, uuid TEXT, last_seen REAL DEFAULT 0,
                                  status TEXT DEFAULT '', pack TEXT DEFAULT '', server TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, name TEXT, created REAL);
CREATE TABLE IF NOT EXISTS challenges (server_id TEXT PRIMARY KEY, created REAL);
CREATE TABLE IF NOT EXISTS friends (a TEXT COLLATE NOCASE, b TEXT COLLATE NOCASE, PRIMARY KEY (a, b));
CREATE TABLE IF NOT EXISTS requests (src TEXT COLLATE NOCASE, dst TEXT COLLATE NOCASE, created REAL,
                                     PRIMARY KEY (src, dst));
CREATE TABLE IF NOT EXISTS invites (src TEXT COLLATE NOCASE, dst TEXT COLLATE NOCASE, pack TEXT, server TEXT,
                                    created REAL, PRIMARY KEY (src, dst));
