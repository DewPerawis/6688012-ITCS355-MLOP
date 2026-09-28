import http from 'k6/http';
import { check } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const latency = new Trend('predict_latency_ms', true);
const failures = new Rate('predict_failures');
const predictions = new Counter('predictions_total');
const status2xx = new Counter('http_status_2xx');
const status429 = new Counter('http_status_429');
const status5xx = new Counter('http_status_5xx');
const statusOther = new Counter('http_status_other');

const vus = Number(__ENV.VUS || 10);
const measuredDuration = __ENV.DURATION || '60s';
const warmupDuration = __ENV.WARMUP || '15s';
const target = __ENV.TARGET || '';
const endpointKey = __ENV.ENDPOINT_KEY || '';

if (!target.startsWith('https://')) {
  throw new Error('TARGET must be a non-empty HTTPS URL');
}
if (!endpointKey) {
  throw new Error('ENDPOINT_KEY must be non-empty');
}

export const options = {
  scenarios: {
    warmup: {
      executor: 'constant-vus', vus, duration: warmupDuration, exec: 'warmup',
    },
    measured: {
      executor: 'constant-vus', vus, duration: measuredDuration,
      startTime: warmupDuration, exec: 'measured',
    },
  },
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  thresholds: {
    predict_latency_ms: ['p(95)<250'],
    predict_failures: ['rate<0.01'],
  },
};

function sampleRow() {
  return {
    temp_c: 78.4,
    vibration_mm_s: 3.1,
    pressure_kpa: 315.2,
    hours_since_service: 4200.0,
    load_pct: 68.0,
    ambient_humidity: 55.0,
    request_context: 'x'.repeat(Number(__ENV.PADDING_BYTES || 0)),
  };
}

function bodyAndCount() {
  if ((__ENV.MODE || 'single') === 'batch') {
    const size = Number(__ENV.BATCH_SIZE || 100);
    return [JSON.stringify({ rows: Array.from({ length: size }, sampleRow) }), size];
  }
  return [JSON.stringify(sampleRow()), 1];
}

function request(recordMetrics) {
  const [body, count] = bodyAndCount();
  const response = http.post(target, body, {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${endpointKey}`,
    },
  });
  if (recordMetrics) {
    if (response.status >= 200 && response.status < 300) status2xx.add(1);
    else if (response.status === 429) status429.add(1);
    else if (response.status >= 500) status5xx.add(1);
    else statusOther.add(1);
    latency.add(response.timings.duration);
    failures.add(response.status !== 200);
    if (response.status === 200) predictions.add(count);
    check(response, {
      'status is 200': (r) => r.status === 200,
      'version in body': (r) => r.status === 200 && r.json('model_version') !== undefined,
    });
  }
}

export function warmup() { request(false); }
export function measured() { request(true); }
