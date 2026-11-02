// verify:command-encode (260910 신설 — 하드웨어 연동 지시서 §7 · 261102 정본 바이트 대조로 교체)
//
// **로봇 없이 「하드웨어가 알아듣는지」를 증명한다.**
//
// 전에는 하드웨어가 잰 **길이**(ping 31 · scan_mission 79 바이트)만 견줬다. 길이는 필드
// 번호·와이어 타입이 바뀌어도 우연히 맞을 수 있다. 이제는 **바이트 하나하나**를 견준다:
//
//   정본 바이트  hardware/schema/golden/physical_command.golden.json
//               — 말단이 디코드에 쓰는 정본 스키마(hardware/schema/physical_command.proto)와
//                 하드웨어의 생성 코드(physical_command_pb2)로 파이썬이 인코딩한 hex.
//                 `python -I scripts/check_contracts.py` 가 그 파일이 정본과 맞는지 따로 본다.
//
// 1. 우리가 **보내는** 것(command · cancel_request)은 protocol.js 로 인코딩한 바이트가 정본 hex 와
//    **똑같아야** 한다. `encodeCommand` 로 만든 ping · scan_mission 도 같은 hex 여야 한다.
// 2. 우리가 **받는** 것(acceptance · status · result · cancel_response · capability)은 정본 hex 를
//    protocol.js 로 디코드했을 때 원래 값이 그대로 나와야 한다.
// 3. 하드웨어가 잰 길이(31 · 79)는 그대로 둔다 — 정본 hex 의 길이가 그 수치와 같은지도 본다.

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const repoRoot = join(root, '..', '..');
const GOLDEN = join(repoRoot, 'hardware', 'schema', 'golden', 'physical_command.golden.json');
const { physical } = await import(pathToFileURL(join(root, 'src', 'physical', 'protocol.js')).href);
const { encodeCommand, PING_BYTES, SCAN_REFERENCE_BYTES } = await import(
  pathToFileURL(join(root, 'src', 'physical', 'encode.ts')).href
);

const failures = [];
const controls = [];
const hex = (bytes) => Buffer.from(bytes).toString('hex');
const fromHex = (value) => Uint8Array.from(Buffer.from(value, 'hex'));

/** 하드웨어가 잰 수치. */
const REFERENCE = { ping: 31, scanForward1: 79 };
/** 우리가 보내는 봉투 종류 — 바이트까지 같아야 한다. */
const DOWNLINK = new Set(['command', 'cancel_request']);
/** 맵 칸(부모 봉투 종류 → 칸) — 그 안의 키는 필드 이름이 아니라 값이라 camelCase 로 바꾸지 않는다. */
const MAP_FIELDS = { command: 'parameters', result: 'result' };
const toCamel = (k) => k.replace(/_([a-z])/g, (_, c) => c.toUpperCase());

const golden = JSON.parse(readFileSync(GOLDEN, 'utf8'));
const cases = new Map(golden.cases.map((c) => [c.name, c]));

/** proto 필드 이름(snake_case) → protobufjs 정적 모듈의 이름(camelCase). 맵 안의 키는 그대로. */
function camel(envelope) {
  return Object.fromEntries(Object.entries(envelope).map(([kind, body]) => [toCamel(kind), Object.fromEntries(
    Object.entries(body).map(([k, v]) => [toCamel(k), k === MAP_FIELDS[kind] || v === null || typeof v !== 'object' || Array.isArray(v)
      ? v
      : Object.fromEntries(Object.entries(v).map(([kk, vv]) => [toCamel(kk), vv]))]),
  )]));
}

/** proto3 기본값(false · 0 · '' · [])은 와이어에 안 실린다 — 비교에서 뺀다. */
function dropDefaults(value) {
  if (Array.isArray(value)) return value.length ? value.map(dropDefaults) : undefined;
  if (value === null || typeof value !== 'object') return value === false || value === 0 || value === '' ? undefined : value;
  const out = {};
  for (const [k, v] of Object.entries(value)) {
    const d = dropDefaults(v);
    if (d !== undefined) out[k] = d;
  }
  return out;
}

/** 디코드 결과를 정본 메시지와 같은 모양으로 — 기본값 칸은 정본 JSON 에서 빠져 있다. */
function plain(message) {
  return JSON.parse(JSON.stringify(physical.PhysicalCommandEnvelope.toObject(message, {
    enums: String, longs: String, defaults: false,
  })));
}

function sameJson(a, b) {
  const sort = (v) => (Array.isArray(v) ? v.map(sort)
    : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, sort(v[k])])) : v);
  return JSON.stringify(sort(a)) === JSON.stringify(sort(b));
}

// ── 1·2. 정본 바이트 전부 ────────────────────────────────────────────────────
for (const c of golden.cases) {
  const kind = Object.keys(c.message)[0];
  const expected = camel(c.message);
  // 받는 쪽: 정본 hex 를 디코드하면 원래 값이 나와야 한다.
  const decoded = physical.PhysicalCommandEnvelope.decode(fromHex(c.hex));
  const err = physical.PhysicalCommandEnvelope.verify(decoded);
  if (err) failures.push(`${c.name}: 정본 바이트가 protocol.js 검증에 걸린다 — ${err}`);
  if (decoded.body !== toCamel(kind)) failures.push(`${c.name}: oneof body 가 ${decoded.body} — ${toCamel(kind)} 여야 한다`);
  const got = plain(decoded);
  if (!sameJson(dropDefaults(got), dropDefaults(expected))) {
    failures.push(`${c.name}: 디코드 값이 정본과 다르다\n    우리: ${JSON.stringify(got)}\n    정본: ${JSON.stringify(expected)}`);
  }
  // 보내는 쪽: 같은 값을 인코딩하면 바이트가 똑같아야 한다.
  if (DOWNLINK.has(kind)) {
    const ours = hex(physical.PhysicalCommandEnvelope.encode(physical.PhysicalCommandEnvelope.fromObject(expected)).finish());
    if (ours !== c.hex) failures.push(`${c.name}: 인코딩 바이트가 정본과 다르다\n    우리: ${ours}\n    정본: ${c.hex}`);
  }
}

// ── 1'. 화면이 실제로 쓰는 `encodeCommand` 도 같은 바이트인가 ─────────────────
{
  const ping = cases.get('ping');
  const scan = cases.get('scan_mission');
  if (!ping || !scan) failures.push('정본 파일에 ping · scan_mission 이 없다');
  else {
    const id = ping.message.command.command_id;
    const ours = hex(encodeCommand({ commandId: id, action: 'ping' }));
    if (ours !== ping.hex) failures.push(`encodeCommand(ping) 가 정본과 다르다\n    우리: ${ours}\n    정본: ${ping.hex}`);
    // 일부러 이름순이 아닌 순서로 넘긴다 — encodeCommand 가 정렬해야 정본과 같다.
    const scanOurs = hex(encodeCommand({ commandId: id, action: 'scan_mission', parameters: { steps: 8, forward_m: 1.0 } }));
    if (scanOurs !== scan.hex) failures.push(`encodeCommand(scan_mission) 가 정본과 다르다\n    우리: ${scanOurs}\n    정본: ${scan.hex}`);
  }
}

// ── 3. 하드웨어가 잰 길이 ────────────────────────────────────────────────────
{
  const lengthOf = (name) => (cases.get(name)?.hex.length ?? 0) / 2;
  if (lengthOf('ping') !== REFERENCE.ping) failures.push(`정본 ping 이 ${lengthOf('ping')}바이트 — 하드웨어가 잰 ${REFERENCE.ping}`);
  if (lengthOf('scan_mission') !== REFERENCE.scanForward1) {
    failures.push(`정본 scan_mission 이 ${lengthOf('scan_mission')}바이트 — 하드웨어가 잰 ${REFERENCE.scanForward1}`);
  }
  if (PING_BYTES !== REFERENCE.ping) failures.push(`PING_BYTES 상수가 ${PING_BYTES} — ${REFERENCE.ping} 이어야 한다`);
  if (SCAN_REFERENCE_BYTES !== REFERENCE.scanForward1) {
    failures.push(`SCAN_REFERENCE_BYTES 상수가 ${SCAN_REFERENCE_BYTES} — ${REFERENCE.scanForward1} 이어야 한다`);
  }
}

// ── 4. move_forward 왕복 · target 은 하드웨어 id ─────────────────────────────
{
  const decoded = physical.PhysicalCommandEnvelope.decode(
    encodeCommand({ commandId: 'cmd-00000001', action: 'move_forward', parameters: { distance_m: 4.2 } }),
  );
  if (Math.abs((decoded.command?.parameters?.distance_m ?? 0) - 4.2) > 1e-9) {
    failures.push(`distance_m 왕복이 깨졌다 — ${decoded.command?.parameters?.distance_m}`);
  }
  for (const [action, parameters] of [['ping', undefined], ['scan_mission', { steps: 8, forward_m: 0 }]]) {
    const d = physical.PhysicalCommandEnvelope.decode(encodeCommand({ commandId: 'cmd-00000001', action, parameters }));
    if (d.command?.target !== 'go1-001') failures.push(`${action}: target 이 ${d.command?.target} — 하드웨어는 go1-001 을 쓴다`);
  }
}

// ── 대조군 — 틀린 인코딩이 바이트로 잡히는가 ────────────────────────────────
function control(name, hit) {
  if (!hit) failures.push(`대조군 실패: ${name} — 변조 사본이 잡히지 않았다`);
  controls.push(name);
}
{
  const scan = cases.get('scan_mission');
  const id = scan.message.command.command_id;
  // forward_m=0 은 길이가 같다(double 고정폭) — 길이 대조로는 못 잡던 것을 바이트로 잡는다.
  const zero = hex(encodeCommand({ commandId: id, action: 'scan_mission', parameters: { steps: 8, forward_m: 0 } }));
  control('forward_m=0 (길이는 같고 바이트는 다르다)', zero.length === scan.hex.length && zero !== scan.hex);
  const wrongTarget = hex(physical.PhysicalCommandEnvelope.encode(physical.PhysicalCommandEnvelope.create({
    command: { commandId: id, target: 'robot-01', action: 'ping' },
  })).finish());
  control('target 을 robot-01 로 쓴 사본', wrongTarget !== cases.get('ping').hex);
  // traceparent(필드 6)를 빼면 정본과 달라야 한다 — 낡은 사본 스키마가 바로 이 모양이었다.
  const traced = camel(cases.get('move_forward_traced').message);
  delete traced.command.traceparent;
  const untraced = hex(physical.PhysicalCommandEnvelope.encode(physical.PhysicalCommandEnvelope.fromObject(traced)).finish());
  control('traceparent 가 빠진 사본', untraced !== cases.get('move_forward_traced').hex);
}

// ── 결과 ─────────────────────────────────────────────────────────────────────
if (failures.length) {
  console.error(`❌ verify:command-encode\n- ${failures.join('\n- ')}`);
  process.exit(1);
}
console.log(`✅ 정본 바이트 ${golden.cases.length}건 — 보내는 것은 바이트까지 같고, 받는 것은 값이 그대로 나온다`);
console.log(`✅ encodeCommand(ping) ${REFERENCE.ping}바이트 · encodeCommand(scan_mission) ${REFERENCE.scanForward1}바이트 — 정본 hex 와 같다`);
console.log(`✅ 대조군 ${controls.length}건 전부 검출 — ${controls.join(' · ')}`);
