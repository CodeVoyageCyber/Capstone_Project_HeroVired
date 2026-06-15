const express = require("express");
const cors = require("cors");
const grpc = require("@grpc/grpc-js");
const protoLoader = require("@grpc/proto-loader");
const path = require("path");

const PROTO_PATH = path.join(__dirname, "protos", "stats.proto");
const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});
const statsProto = grpc.loadPackageDefinition(packageDefinition).stats;

const STATS_SERVICE_ADDR = process.env.STATS_SERVICE_ADDR || "stats-service-cluster-ip-service:50053";
const statsClient = new statsProto.Stats(STATS_SERVICE_ADDR, grpc.credentials.createInsecure());

const app = express();
app.use(cors());

app.get("/healthz", (req, res) => res.send({ ok: true }));

const getOverview = (req, res) => {
  statsClient.GetOverview({}, (err, overview) => {
    if (err) return res.status(500).send({ error: err.message });
    res.send({ data: overview });
  });
};

app.get("/stats/overview", getOverview);
app.get("/overview", getOverview);

const PORT = process.env.PORT || 5003;
app.listen(PORT, () => console.log(`Stats API listening on :${PORT}`));
