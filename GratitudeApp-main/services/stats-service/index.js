const grpc = require("@grpc/grpc-js");
const protoLoader = require("@grpc/proto-loader");
const { Pool } = require("pg");
const path = require("path");

const STATS_PROTO = path.join(__dirname, "protos", "stats.proto");
const statsDefinition = protoLoader.loadSync(STATS_PROTO, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});
const statsProto = grpc.loadPackageDefinition(statsDefinition).stats;

const pool = new Pool({
  user: process.env.PGUSER,
  host: process.env.PGHOST,
  database: process.env.PGDATABASE,
  password: process.env.PGPASSWORD,
  port: process.env.PGPORT,
});

async function ensureTables() {
  const client = await pool.connect();
  try {
    await client.query(
      "CREATE TABLE IF NOT EXISTS entries (id SERIAL PRIMARY KEY, text TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW())"
    );
    await client.query(
      "CREATE TABLE IF NOT EXISTS moods (id SERIAL PRIMARY KEY, mood TEXT NOT NULL, note TEXT, created_at TIMESTAMPTZ DEFAULT NOW())"
    );
  } finally {
    client.release();
  }
}

const serviceImpl = {
  async GetOverview(call, callback) {
    try {
      const client = await pool.connect();
      try {
        const totalEntriesRes = await client.query("SELECT COUNT(*) AS count FROM entries");
        const entriesTodayRes = await client.query(
          "SELECT COUNT(*) AS count FROM entries WHERE created_at >= date_trunc('day', now())"
        );
        const last7Res = await client.query(
          `SELECT to_char(date(created_at), 'YYYY-MM-DD') AS day, COUNT(*) AS count
           FROM entries
           WHERE created_at >= now() - interval '6 days'
           GROUP BY day
           ORDER BY day`
        );
        const streakRes = await client.query(
          `SELECT to_char(date(created_at), 'YYYY-MM-DD') AS day
           FROM entries
           GROUP BY day
           ORDER BY day DESC
           LIMIT 60`
        );
        const moodRes = await client.query(
          `SELECT mood, COUNT(*) AS count
           FROM moods
           WHERE created_at >= now() - interval '7 days'
           GROUP BY mood`
        );

        const totalEntries = parseInt(totalEntriesRes.rows[0]?.count || "0", 10);
        const entriesToday = parseInt(entriesTodayRes.rows[0]?.count || "0", 10);
        const last7Days = buildLast7Days(last7Res.rows);
        const streakDays = computeStreak(streakRes.rows.map((row) => row.day));
        const moodTrend = moodRes.rows.map((row) => ({
          mood: row.mood,
          count: parseInt(row.count, 10),
        }));

        callback(null, {
          total_entries: totalEntries,
          entries_today: entriesToday,
          streak_days: streakDays,
          last7_days: last7Days,
          mood_trend: moodTrend,
        });
      } finally {
        client.release();
      }
    } catch (e) {
      console.error("Stats service error", e);
      callback({ code: grpc.status.INTERNAL, message: "stats unavailable" });
    }
  },
};

function buildLast7Days(rows) {
  const map = new Map();
  rows.forEach((row) => {
    map.set(row.day, parseInt(row.count, 10));
  });
  const result = [];
  for (let i = 6; i >= 0; i--) {
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    date.setDate(date.getDate() - i);
    const key = date.toISOString().slice(0, 10);
    result.push({ date: key, count: map.get(key) || 0 });
  }
  return result;
}

function computeStreak(days) {
  if (!days || days.length === 0) return 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  let expected = today;
  let streak = 0;

  for (const dayStr of days) {
    const current = parseDate(dayStr);
    const diff = differenceInDays(current, expected);
    if (streak === 0 && diff > 0) {
      // first record is older than today -> no streak
      break;
    }
    if (diff === 0) {
      streak += 1;
      expected = addDays(expected, -1);
    } else if (diff === 1 && streak === 0) {
      // No entry today but entry yesterday: streak is 0, stop
      break;
    } else {
      break;
    }
  }
  return streak;
}

function parseDate(str) {
  const date = new Date(str + "T00:00:00Z");
  date.setHours(0, 0, 0, 0);
  return date;
}

function differenceInDays(a, b) {
  const ms = a.getTime() - b.getTime();
  return Math.round(ms / (1000 * 60 * 60 * 24));
}

function addDays(date, amount) {
  const copy = new Date(date);
  copy.setDate(copy.getDate() + amount);
  return copy;
}

async function main() {
  await ensureTables();
  const server = new grpc.Server();
  server.addService(statsProto.Stats.service, serviceImpl);
  const host = process.env.HOST || "0.0.0.0";
  const port = process.env.PORT || "50053";
  const addr = `${host}:${port}`;
  server.bindAsync(addr, grpc.ServerCredentials.createInsecure(), (err) => {
    if (err) throw err;
    server.start();
    console.log(`StatsService listening on ${addr}`);
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
