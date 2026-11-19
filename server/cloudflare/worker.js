// .NET Launcher friends service for Cloudflare Workers + D1.
// Same HTTP API as ../friends_server.py, so the launcher talks to either one.

const ONLINE_SECONDS = 60;
const CHALLENGE_SECONDS = 300;
const MAX_BODY = 16 * 1024;
const NAME_RE = /^[A-Za-z0-9_]{2,16}$/;
const STATUSES = new Set(["launcher", "playing"]);

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

const now = () => Date.now() / 1000;

function hex(bytes) {
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function randomHex(n) {
  return hex(crypto.getRandomValues(new Uint8Array(n)));
}

function randomToken() {
  const b = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...b)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function json(status, payload) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

function nameOf(body, key = "name") {
  const n = String(body[key] ?? "");
  if (!NAME_RE.test(n)) throw new ApiError(400, "bad name");
  return n;
}

class Api {
  constructor(env) {
    this.db = env.DB;
    this.elyUrl = env.ELY_HAS_JOINED;
  }

  async all(sql, ...args) {
    return (await this.db.prepare(sql).bind(...args).all()).results;
  }

  async run(sql, ...args) {
    await this.db.prepare(sql).bind(...args).run();
  }

  async canon(name) {
    const r = await this.all("SELECT name FROM users WHERE name = ?", name);
    return r.length ? r[0].name : name;
  }

  async areFriends(a, b) {
    return (await this.all("SELECT 1 AS x FROM friends WHERE a = ? AND b = ?", a, b)).length > 0;
  }

  async userFor(token) {
    if (!token) throw new ApiError(401, "no session");
    const r = await this.all("SELECT name FROM sessions WHERE token = ?", token);
    if (!r.length) throw new ApiError(401, "no session");
    return r[0].name;
  }

  async verifyEly(name, serverId) {
    const q = new URLSearchParams({ username: name, serverId });
    try {
      const r = await fetch(`${this.elyUrl}?${q}`);
      if (r.status !== 200) return null;
      const data = await r.json();
      return data && data.name ? data : null;
    } catch {
      return null;
    }
  }

  // ---------- auth ----------
  async challenge() {
    const sid = randomHex(16);
    await this.run("DELETE FROM challenges WHERE created < ?", now() - CHALLENGE_SECONDS);
    await this.run("INSERT INTO challenges VALUES (?, ?)", sid, now());
    return { server_id: sid };
  }

  async verifyLogin(body) {
    const name = nameOf(body);
    const sid = String(body.server_id ?? "");
    const row = await this.all("SELECT created FROM challenges WHERE server_id = ?", sid);
    if (!row.length || now() - row[0].created > CHALLENGE_SECONDS) throw new ApiError(401, "challenge expired");
    await this.run("DELETE FROM challenges WHERE server_id = ?", sid);
    const prof = await this.verifyEly(name, sid);
    if (!prof) throw new ApiError(401, "ely.by did not confirm the player");
    const real = prof.name;
    await this.run(
      "INSERT INTO users (name, uuid) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET uuid = excluded.uuid",
      real, prof.id ?? "");
    const token = randomToken();
    await this.run("INSERT INTO sessions VALUES (?, ?, ?)", token, real, now());
    return { token, name: real };
  }

  // ---------- state ----------
  async state(me) {
    const t = now();
    const rows = await this.all(
      "SELECT u.name, u.last_seen, u.status, u.pack, u.server FROM friends f JOIN users u ON u.name = f.b " +
      "WHERE f.a = ? ORDER BY u.name COLLATE NOCASE", me);
    const friends = rows.map((u) => {
      const online = t - (u.last_seen || 0) < ONLINE_SECONDS;
      return { name: u.name, online, status: online ? u.status : "", pack: online ? u.pack : "",
               server: online ? u.server : "", last_seen: u.last_seen || 0 };
    });
    const incoming = (await this.all("SELECT src FROM requests WHERE dst = ? ORDER BY created", me)).map((r) => r.src);
    const outgoing = [];
    for (const r of await this.all("SELECT dst FROM requests WHERE src = ? ORDER BY created", me)) {
      outgoing.push(await this.canon(r.dst));
    }
    const invites = (await this.all(
      "SELECT src, pack, server, created FROM invites WHERE dst = ? ORDER BY created", me))
      .map((r) => ({ from: r.src, pack: r.pack, server: r.server, created: r.created }));
    return { me, friends, incoming, outgoing, invites };
  }

  async presence(me, body) {
    const status = String(body.status ?? "launcher");
    if (!STATUSES.has(status)) throw new ApiError(400, "bad status");
    await this.run("UPDATE users SET last_seen = ?, status = ?, pack = ?, server = ? WHERE name = ?",
      now(), status, String(body.pack ?? "").slice(0, 64), String(body.server ?? "").slice(0, 128), me);
    return this.state(me);
  }

  // ---------- friends ----------
  async request(me, body) {
    const other = await this.canon(nameOf(body));
    if (other.toLowerCase() === me.toLowerCase()) throw new ApiError(400, "that is you");
    if (await this.areFriends(me, other)) return this.state(me);
    if ((await this.all("SELECT 1 AS x FROM requests WHERE src = ? AND dst = ?", other, me)).length) {
      return this.accept(me, { name: other });
    }
    await this.run("INSERT OR IGNORE INTO requests VALUES (?, ?, ?)", me, other, now());
    return this.state(me);
  }

  async accept(me, body) {
    const other = await this.canon(nameOf(body));
    if (!(await this.all("SELECT 1 AS x FROM requests WHERE src = ? AND dst = ?", other, me)).length) {
      throw new ApiError(404, "no such request");
    }
    await this.run("DELETE FROM requests WHERE (src = ? AND dst = ?) OR (src = ? AND dst = ?)", other, me, me, other);
    await this.run("INSERT OR IGNORE INTO friends VALUES (?, ?)", me, other);
    await this.run("INSERT OR IGNORE INTO friends VALUES (?, ?)", other, me);
    return this.state(me);
  }

  async decline(me, body) {
    await this.run("DELETE FROM requests WHERE src = ? AND dst = ?", nameOf(body), me);
    return this.state(me);
  }

  async remove(me, body) {
    const other = nameOf(body);
    await this.run("DELETE FROM friends WHERE (a = ? AND b = ?) OR (a = ? AND b = ?)", me, other, other, me);
    await this.run("DELETE FROM invites WHERE (src = ? AND dst = ?) OR (src = ? AND dst = ?)", me, other, other, me);
    return this.state(me);
  }

  async invite(me, body) {
    const other = await this.canon(nameOf(body));
    if (!(await this.areFriends(me, other))) throw new ApiError(403, "not friends");
    await this.run("INSERT OR REPLACE INTO invites VALUES (?, ?, ?, ?, ?)", me, other,
      String(body.pack ?? "").slice(0, 64), String(body.server ?? "").slice(0, 128), now());
    return this.state(me);
  }

  async dismiss(me, body) {
    await this.run("DELETE FROM invites WHERE src = ? AND dst = ?", nameOf(body, "from"), me);
    return this.state(me);
  }

  async reset() {
    for (const t of ["users", "sessions", "challenges", "friends", "requests", "invites"]) {
      await this.run(`DELETE FROM ${t}`);
    }
    return { ok: true };
  }
}

const ROUTES = {
  "POST /v1/auth/challenge": ["challenge", false],
  "POST /v1/auth/verify": ["verifyLogin", false],
  "GET /v1/state": ["state", true],
  "POST /v1/presence": ["presence", true],
  "POST /v1/friends/request": ["request", true],
  "POST /v1/friends/accept": ["accept", true],
  "POST /v1/friends/decline": ["decline", true],
  "POST /v1/friends/remove": ["remove", true],
  "POST /v1/invite": ["invite", true],
  "POST /v1/invite/dismiss": ["dismiss", true],
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const key = `${request.method} ${url.pathname}`;
    if (key === "GET /") return json(200, { service: "net-friends", ok: true });
    if (key === "POST /v1/_reset" && env.ALLOW_RESET === "1") return json(200, await new Api(env).reset());
    const route = ROUTES[key];
    if (!route) return json(404, { error: "not found" });
    const [name, needsAuth] = route;
    const api = new Api(env);
    try {
      const raw = await request.text();
      if (raw.length > MAX_BODY) throw new ApiError(413, "too large");
      let body = {};
      if (raw) {
        try {
          body = JSON.parse(raw);
        } catch {
          throw new ApiError(400, "bad json");
        }
      }
      if (typeof body !== "object" || body === null || Array.isArray(body)) throw new ApiError(400, "bad json");
      let result;
      if (needsAuth) {
        const auth = request.headers.get("Authorization") || "";
        const me = await api.userFor(auth.startsWith("Bearer ") ? auth.slice(7) : null);
        result = name === "state" ? await api.state(me) : await api[name](me, body);
      } else {
        result = await api[name](body);
      }
      return json(200, result);
    } catch (e) {
      if (e instanceof ApiError) return json(e.status, { error: e.message });
      return json(500, { error: "internal error" });
    }
  },
};
