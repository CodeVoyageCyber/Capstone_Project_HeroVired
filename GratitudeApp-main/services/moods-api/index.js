const express = require("express");
const bodyParser = require("body-parser");
const cors = require("cors");
const grpc = require("@grpc/grpc-js");
const protoLoader = require("@grpc/proto-loader");
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

const MOODS_SERVICE_ADDR = process.env.MOODS_SERVICE_ADDR || "moods-service-cluster-ip-service:50052";
const moodsClient = new moodsProto.Moods(MOODS_SERVICE_ADDR, grpc.credentials.createInsecure());

const app = express();
app.use(cors());
app.use(bodyParser.json());

app.get("/healthz", (req, res) => res.send({ ok: true }));

const listMoods = (req, res) => {
  const limit = Math.min(100, parseInt(req.query.limit || "30", 10) || 30);
  moodsClient.ListMoods({ limit }, (err, result) => {
    if (err) return res.status(500).send({ error: err.message });
    res.send({ rows: result.moods || [] });
  });
};

app.get("/moods/all", listMoods);
app.get("/all", listMoods);

const createMood = (req, res) => {
  const payload = {
    mood: (req.body && req.body.mood) || "",
    note: (req.body && req.body.note) || "",
  };
  moodsClient.CreateMood(payload, (err, mood) => {
    if (err) {
      const status = err.code === grpc.status.INVALID_ARGUMENT ? 400 : 500;
      return res.status(status).send({ ok: false, error: err.message });
    }
    res.send({ ok: true, mood });
  });
};

app.post("/moods", createMood);
app.post("/", createMood);

const PORT = process.env.PORT || 5002;
app.listen(PORT, () => console.log(`Moods API listening on :${PORT}`));
