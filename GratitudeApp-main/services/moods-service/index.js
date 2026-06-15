const grpc = require("@grpc/grpc-js");
const protoLoader = require("@grpc/proto-loader");
const { Pool } = require("pg");
const path = require("path");

const PROTO_PATH = path.join(__dirname, "protos", "moods.proto");
const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});
const moodsProto = grpc.loadPackageDefinition(packageDefinition).moods;

const pool = new Pool({
  user: process.env.PGUSER,
  host: process.env.PGHOST,
  database: process.env.PGDATABASE,
  password: process.env.PGPASSWORD,
  port: process.env.PGPORT,
});

const ALLOWED_MOODS = new Set(["grateful", "happy", "calm", "focused", "stressed", "tired", "energized"]);

async function ensureTables() {
  const client = await pool.connect();
  try {
    await client.query(
      "CREATE TABLE IF NOT EXISTS moods (id SERIAL PRIMARY KEY, mood TEXT NOT NULL, note TEXT, created_at TIMESTAMPTZ DEFAULT NOW())"
    );
  } finally {
    client.release();
  }
}

const serviceImpl = {
  async CreateMood(call, callback) {
    try {
      const mood = (call.request.mood || "").toLowerCase();
      const note = (call.request.note || "").trim().slice(0, 240);
      if (!ALLOWED_MOODS.has(mood)) {
        return callback({ code: grpc.status.INVALID_ARGUMENT, message: "invalid mood" });
      }

      const result = await pool.query(
        "INSERT INTO moods(mood, note) VALUES($1, $2) RETURNING id, mood, note, created_at",
        [mood, note]
      );
      const row = result.rows[0];
      callback(null, {
        id: row.id,
        mood: row.mood,
        note: row.note || "",
        created_at: row.created_at.toISOString(),
      });
    } catch (e) {
      callback({ code: grpc.status.INTERNAL, message: "db error" });
    }
  },

  async ListMoods(call, callback) {
    try {
      const limit = Math.max(1, Math.min(100, call.request.limit || 30));
      const result = await pool.query(
        "SELECT id, mood, note, created_at FROM moods ORDER BY created_at DESC LIMIT $1",
        [limit]
      );
      const moods = result.rows.map((row) => ({
        id: row.id,
        mood: row.mood,
        note: row.note || "",
        created_at: row.created_at.toISOString(),
      }));
      callback(null, { moods });
    } catch (e) {
      callback({ code: grpc.status.INTERNAL, message: "db error" });
    }
  },
};

async function main() {
  await ensureTables();
  const server = new grpc.Server();
  server.addService(moodsProto.Moods.service, serviceImpl);
  const host = process.env.HOST || "0.0.0.0";
  const port = process.env.PORT || "50052";
  const addr = `${host}:${port}`;
  server.bindAsync(addr, grpc.ServerCredentials.createInsecure(), (err) => {
    if (err) throw err;
    server.start();
    console.log(`MoodsService listening on ${addr}`);
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

