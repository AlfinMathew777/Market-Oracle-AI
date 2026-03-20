/**
 * AussieIntel AIS Relay — Port Hedland vessel tracker
 *
 * Standalone Node.js service (separate Render Background Worker).
 * Connects to AISStream WebSocket, accumulates vessels in Port Hedland
 * bounding box, and writes a snapshot to Upstash Redis every 30 seconds.
 *
 * FastAPI reads from Redis key 'ais:port-hedland:v1' — zero WebSocket code
 * in the Python backend.
 */

const WebSocket = require('ws');
const https = require('https');
const url = require('url');

const UPSTASH_URL   = process.env.UPSTASH_REDIS_REST_URL;
const UPSTASH_TOKEN = process.env.UPSTASH_REDIS_REST_TOKEN;
const AIS_KEY       = process.env.AISSTREAM_API_KEY;

if (!AIS_KEY)       { console.error('AISSTREAM_API_KEY not set'); process.exit(1); }
if (!UPSTASH_URL)   { console.error('UPSTASH_REDIS_REST_URL not set'); process.exit(1); }
if (!UPSTASH_TOKEN) { console.error('UPSTASH_REDIS_REST_TOKEN not set'); process.exit(1); }

// Port Hedland bounding box — world's largest iron ore export port
const BBOX = [[-21.0, 117.5], [-19.5, 119.5]];   // [[minLat,minLon],[maxLat,maxLon]]

// Vessel type codes: 70–89 = cargo, 70–79 = cargo sub-types, 80–89 = tanker
const BULK_CARRIER_TYPES = new Set([70, 71, 72, 73, 74, 75, 76, 77, 78, 79]);

const vessels = new Map();  // mmsi → vessel object
let connected = false;
let reconnectDelay = 5000;

// ── Redis write ───────────────────────────────────────────────────────────────

function writeToRedis() {
  if (!connected && vessels.size === 0) return;

  const vesselList = [...vessels.values()];
  const bulkCarriers = vesselList.filter(v => BULK_CARRIER_TYPES.has(v.shipType));

  const snapshot = {
    vessels:           vesselList,
    vessel_count:      vesselList.length,
    bulk_carrier_count: bulkCarriers.length,
    congestion_level:  getCongestionLevel(bulkCarriers.length),
    connected,
    updatedAt:         Date.now(),
    status:            connected ? 'live' : 'reconnecting',
    data_source:       'ais_relay',
  };

  const body = JSON.stringify([
    ['SET', 'ais:port-hedland:v1', JSON.stringify(snapshot), 'EX', 120],
    ['SET', 'ais:relay:heartbeat',  '1',                      'EX', 600],
    ['SET', 'seed-meta:ais:port-hedland:v1',
      JSON.stringify({ fetchedAt: Date.now(), key: 'ais:port-hedland:v1' }),
      'EX', 240],
  ]);

  const parsed = new url.URL(UPSTASH_URL + '/pipeline');
  const options = {
    hostname: parsed.hostname,
    path:     parsed.pathname,
    method:   'POST',
    headers: {
      'Authorization':  `Bearer ${UPSTASH_TOKEN}`,
      'Content-Type':   'application/json',
      'Content-Length': Buffer.byteLength(body),
    },
  };

  const req = https.request(options, (res) => {
    if (res.statusCode !== 200) {
      console.warn(`Redis write returned ${res.statusCode}`);
    }
  });
  req.on('error', (e) => console.error('Redis write error:', e.message));
  req.write(body);
  req.end();
}

function getCongestionLevel(bulkCount) {
  if (bulkCount >= 20) return 'HIGH';
  if (bulkCount >= 10) return 'MEDIUM';
  return 'LOW';
}

// ── AISStream WebSocket ───────────────────────────────────────────────────────

function connect() {
  const ws = new WebSocket('wss://stream.aisstream.io/v0/stream');

  ws.on('open', () => {
    connected = true;
    reconnectDelay = 5000;
    console.log(`[AIS Relay] Connected to AISStream — monitoring Port Hedland`);
    ws.send(JSON.stringify({
      APIKey: AIS_KEY,
      BoundingBoxes: [BBOX],
      FilterMessageTypes: ['PositionReport'],
    }));
  });

  ws.on('message', (raw) => {
    try {
      const msg = JSON.parse(raw);
      if (msg.MessageType !== 'PositionReport') return;

      const meta  = msg.MetaData || {};
      const pos   = (msg.Message || {}).PositionReport || {};
      const mmsi  = meta.MMSI;
      if (!mmsi) return;

      vessels.set(mmsi, {
        mmsi,
        name:      (meta.ShipName || '').trim() || `Vessel-${mmsi}`,
        lat:       pos.Latitude,
        lon:       pos.Longitude,
        speed:     pos.SpeedOverGround,
        course:    pos.CourseOverGround,
        shipType:  meta.ShipType || 0,
        timestamp: Date.now(),
      });
    } catch (e) {
      console.warn('[AIS Relay] Parse error:', e.message);
    }
  });

  ws.on('close', (code) => {
    connected = false;
    console.log(`[AIS Relay] Disconnected (${code}) — reconnecting in ${reconnectDelay / 1000}s`);
    setTimeout(() => {
      reconnectDelay = Math.min(reconnectDelay * 2, 60000);
      connect();
    }, reconnectDelay);
  });

  ws.on('error', (e) => {
    console.error('[AIS Relay] WebSocket error:', e.message);
    ws.terminate();
  });
}

// Prune vessels older than 30 minutes (they've left the area)
function pruneStaleVessels() {
  const cutoff = Date.now() - 30 * 60 * 1000;
  for (const [mmsi, v] of vessels) {
    if (v.timestamp < cutoff) vessels.delete(mmsi);
  }
}

// ── Start ─────────────────────────────────────────────────────────────────────

connect();
setInterval(writeToRedis,     30 * 1000);   // write snapshot every 30s
setInterval(pruneStaleVessels, 5 * 60 * 1000); // prune stale vessels every 5 min

console.log('[AIS Relay] Started — writing to Redis every 30s');
