const grpc = require("@grpc/grpc-js");
const protoLoader = require("@grpc/proto-loader");
const { Pool } = require("pg");
const path = require("path");

const PROTO_PATH = path.join(__dirname, "protos", "entries.proto");
const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});
const entriesProto = grpc.loadPackageDefinition(packageDefinition).entries;

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
  } finally {
    client.release();
  }
}

const serviceImpl = {
  async CreateEntry(call, callback) {
    try {
      const raw = (call.request.text || "").trim();
      if (!raw) return callback({ code: grpc.status.INVALID_ARGUMENT, message: "text is required" });
      if (raw.length > 200) return callback({ code: grpc.status.INVALID_ARGUMENT, message: "max 200 chars" });

      const result = await pool.query("INSERT INTO entries(text) VALUES($1) RETURNING id, text, created_at", [raw]);
      const row = result.rows[0];
      callback(null, {
        id: row.id,
        text: row.text,
        created_at: row.created_at.toISOString(),
      });
    } catch (e) {
      callback({ code: grpc.status.INTERNAL, message: "db error" });
    }
  },

  async ListEntries(call, callback) {
    try {
      const limit = Math.max(1, Math.min(200, call.request.limit || 50));
      const result = await pool.query(
        "SELECT id, text, created_at FROM entries ORDER BY created_at DESC LIMIT $1",
        [limit]
      );
      const entries = result.rows.map((r) => ({ id: r.id, text: r.text, created_at: r.created_at.toISOString() }));
      callback(null, { entries });
    } catch (e) {
      callback({ code: grpc.status.INTERNAL, message: "db error" });
    }
  },
};

async function main() {
  await ensureTables();
  const server = new grpc.Server();
  server.addService(entriesProto.Entries.service, serviceImpl);
  const host = process.env.HOST || "0.0.0.0";
  const port = process.env.PORT || "50051";
  const addr = `${host}:${port}`;
  server.bindAsync(addr, grpc.ServerCredentials.createInsecure(), (err) => {
    if (err) throw err;
    server.start();
    console.log(`EntriesService listening on ${addr}`);
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
