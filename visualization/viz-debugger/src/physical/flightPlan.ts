/**
 * src/physical/flightPlan.ts (261014 신설 — 드론 비행 제어 탭)
 *
 * **pi3 의 `test_sar_rtk.py` 에 넘길 비행 설정.** 화면이 비행 코드를 새로 짜지 않는다 — 이미 실기체에서 날아 본
 * 그 스크립트를 pi3 실행기가 명령줄 옵션으로 띄운다(`261014_드론비행실행기_요청_VZ.md`). 여기는
 *
 *   - 스크립트가 묻는 값(이동 방향 · 먼저 갈 쪽 · 고도 · 이동거리 · 속도 · 왕복 횟수)과 고급 옵션,
 *   - 그 허용 범위와 기본값 — **스크립트 상수(`MIN_ALT` …)와 같은 수**,
 *   - 예상 시간(`estimate_s` 를 그대로 옮김),
 *   - 규약의 숫자 파라미터(`map<string,double>`)와, 실행기가 만들 명령줄의 미리보기
 *
 * 만 가진다. 범위 검사의 최종 판단은 스크립트의 `ap.error` 다 — 화면은 먼저 걸러 버튼을 닫을 뿐이다.
 *
 * 스크립트 쪽 상수가 바뀌면 여기도 고친다. `verify:flight-run` 이 예상 시간 공식을 파이썬 원문과 같은 수로 대조한다.
 */

export type Pattern = 'fb' | 'lr' | 'rotate';
export type Side = 'forward' | 'back' | 'right' | 'left';
export type AbortHow = 'rtl' | 'hold' | 'land';
export type EmergencyMode = 'land' | 'rtl' | 'hold';

export type FlightPlan = {
  pattern: Pattern;
  side: Side;
  altitudeM: number;
  lengthM: number;
  speedMps: number;
  passes: number;
  // ── 고급 (스크립트 기본값 그대로 두면 된다) ──
  gapS: number;
  /** `null` 이면 이륙 직전 기수 방향(스크립트 기본). */
  headingDeg: number | null;
  acceptRadiusM: number;
  alignHoldS: number;
  settleS: number;
  abort: AbortHow;
  rtkMinS: number;
  rtkTimeoutS: number;
};

export const PATTERNS: readonly Pattern[] = ['fb', 'lr', 'rotate'];
/** 이동 방향마다 고를 수 있는 먼저 갈 쪽 — 스크립트의 `SIDES`. 첫 것이 기본이다. */
export const SIDES_OF: Readonly<Record<Exclude<Pattern, 'rotate'>, readonly Side[]>> = {
  fb: ['forward', 'back'],
  lr: ['right', 'left'],
};
/** 기수 기준 이동선 방향(도) — 스크립트의 `SIDE_DEG`. */
export const SIDE_DEG: Readonly<Record<Side, number>> = { forward: 0, back: 180, right: 90, left: 270 };
export const ABORTS: readonly AbortHow[] = ['rtl', 'hold', 'land'];
export const EMERGENCY_MODES: readonly EmergencyMode[] = ['land', 'rtl', 'hold'];

/** 스크립트 `argparse` 기본값과 같다. */
export const FLIGHT_DEFAULTS: Readonly<FlightPlan> = {
  pattern: 'fb', side: 'forward', altitudeM: 5, lengthM: 5, speedMps: 1, passes: 2,
  gapS: 10, headingDeg: null, acceptRadiusM: 0.5, alignHoldS: 3, settleS: 2, abort: 'rtl', rtkMinS: 30, rtkTimeoutS: 120,
};

type Range = { min: number; max: number };
/**
 * 허용 범위. 앞의 넷은 스크립트 상수(`MIN_ALT, MAX_ALT` …)와 같다. `gapS` 의 하한 10 도 스크립트 검사다.
 * 상한이 스크립트에 없는 칸(간격 · 대기 · RTK 시간)은 화면이 손으로 넣다 0 을 하나 더 치는 실수만 막는다.
 */
export const FLIGHT_LIMITS: Readonly<Record<'altitudeM' | 'lengthM' | 'speedMps' | 'passes' | 'gapS' | 'headingDeg'
  | 'acceptRadiusM' | 'alignHoldS' | 'settleS' | 'rtkMinS' | 'rtkTimeoutS', Range>> = {
  altitudeM: { min: 2, max: 30 },
  lengthM: { min: 2, max: 150 },
  speedMps: { min: 0.5, max: 5 },
  passes: { min: 1, max: 10 },
  gapS: { min: 10, max: 600 },
  headingDeg: { min: 0, max: 360 },
  acceptRadiusM: { min: 0.1, max: 2 },
  alignHoldS: { min: 0, max: 60 },
  settleS: { min: 0, max: 60 },
  rtkMinS: { min: 0, max: 600 },
  rtkTimeoutS: { min: 1, max: 1800 },
};

/** 이동 방향을 바꾸면 먼저 갈 쪽을 그 방향의 것으로 맞춘다 — 스크립트가 `--side` 를 고르는 규칙과 같다. */
export function withPattern(plan: FlightPlan, pattern: Pattern): FlightPlan {
  if (pattern === 'rotate') return { ...plan, pattern };
  const sides = SIDES_OF[pattern];
  return { ...plan, pattern, side: sides.includes(plan.side) ? plan.side : sides[0] };
}

export type PlanProblem =
  | { field: keyof typeof FLIGHT_LIMITS; kind: 'range'; min: number; max: number }
  | { field: 'passes'; kind: 'integer' }
  | { field: 'side'; kind: 'side' }
  | { field: 'acceptRadiusM'; kind: 'radius' };

/** 스크립트 `main()` 의 검사들을 같은 순서로. 빈 배열이면 보낼 수 있다. */
export function planProblems(plan: FlightPlan): PlanProblem[] {
  const problems: PlanProblem[] = [];
  const check = (field: keyof typeof FLIGHT_LIMITS, value: number) => {
    const range = FLIGHT_LIMITS[field];
    if (!(Number.isFinite(value) && value >= range.min && value <= range.max)) problems.push({ field, kind: 'range', ...range });
  };
  const moving = plan.pattern !== 'rotate';
  if (plan.pattern !== 'rotate' && !SIDES_OF[plan.pattern].includes(plan.side)) problems.push({ field: 'side', kind: 'side' });
  check('altitudeM', plan.altitudeM);
  if (moving) {
    check('lengthM', plan.lengthM);
    check('speedMps', plan.speedMps);
  }
  check('passes', plan.passes);
  if (!Number.isInteger(plan.passes)) problems.push({ field: 'passes', kind: 'integer' });
  check('gapS', plan.gapS);
  if (plan.headingDeg !== null) check('headingDeg', plan.headingDeg);
  check('acceptRadiusM', plan.acceptRadiusM);
  // 회전이면 이동거리를 안 넘기므로 스크립트 기본(5 m)과 비교된다.
  const length = moving ? plan.lengthM : FLIGHT_DEFAULTS.lengthM;
  if (plan.acceptRadiusM >= length) problems.push({ field: 'acceptRadiusM', kind: 'radius' });
  check('alignHoldS', plan.alignHoldS);
  check('settleS', plan.settleS);
  check('rtkMinS', plan.rtkMinS);
  check('rtkTimeoutS', plan.rtkTimeoutS);
  return problems;
}

/** 미션 예상 시간(초) — 스크립트 `estimate_s` 를 한 줄씩 옮겼다. 시간 초과 판정은 이 값 × 2 + 60 초다. */
export function estimateSec(plan: FlightPlan): number {
  const length = plan.pattern === 'rotate' ? FLIGHT_DEFAULTS.lengthM : plan.lengthM;
  const speed = plan.pattern === 'rotate' ? FLIGHT_DEFAULTS.speedMps : plan.speedMps;
  const t = plan.altitudeM / 1.0 + 6 + plan.alignHoldS + plan.settleS + plan.altitudeM / 0.7 + 10;
  const rest = Math.max(plan.settleS, plan.gapS);
  const per = plan.pattern === 'rotate'
    ? 360.0 / 30.0 + rest
    : 2 * (length / speed + 4) + plan.settleS + rest;
  return t + per * plan.passes;
}

/** 스크립트가 쓰는 시간 초과 판정(초). 화면이 「이 시간을 넘으면 스크립트가 abort 한다」를 적는 데 쓴다. */
export function timeoutSec(plan: FlightPlan): number {
  return estimateSec(plan) * 2 + 60;
}

// ── 규약 — 숫자 파라미터 (요청 문서 §2-1) ────────────────────────────────

export const PATTERN_CODE: Readonly<Record<Pattern, number>> = { fb: 0, lr: 1, rotate: 2 };
export const SIDE_CODE: Readonly<Record<Side, number>> = { forward: 0, back: 1, right: 2, left: 3 };
export const ABORT_CODE: Readonly<Record<AbortHow, number>> = { rtl: 0, hold: 1, land: 2 };
export const EMERGENCY_CODE: Readonly<Record<EmergencyMode, number>> = { land: 0, rtl: 1, hold: 2 };

/**
 * 비행 설정 → 파라미터. **실행 여부(`dry_run` · `confirmed`)는 넣지 않는다** — 같은 설정의 dry-run 과 비행을
 * 이 값으로 짝짓는다(`planSignature`).
 *
 * 회전이면 먼저 갈 쪽 · 이동거리 · 속도를 싣지 않는다 — 스크립트도 회전에서는 묻지 않는다.
 * 고급 칸은 기본값이어도 싣는다 — 화면에 보인 값과 실행된 값이 같다는 것을 명령 기록만 보고 알 수 있게.
 */
export function planParams(plan: FlightPlan): Record<string, number> {
  const params: Record<string, number> = {
    pattern: PATTERN_CODE[plan.pattern],
    altitude_m: plan.altitudeM,
    passes: plan.passes,
    gap_s: plan.gapS,
    accept_radius_m: plan.acceptRadiusM,
    align_hold_s: plan.alignHoldS,
    settle_s: plan.settleS,
    abort: ABORT_CODE[plan.abort],
    rtk_min_s: plan.rtkMinS,
    rtk_timeout_s: plan.rtkTimeoutS,
  };
  if (plan.pattern !== 'rotate') {
    params.side = SIDE_CODE[plan.side];
    params.length_m = plan.lengthM;
    params.speed_mps = plan.speedMps;
  }
  if (plan.headingDeg !== null) params.heading_deg = plan.headingDeg;
  return params;
}

/** `rtk_test_start` 에 실을 전부. 실제 비행이면 `confirmed` 가 있어야 실행기가 받는다. */
export function startParams(plan: FlightPlan, run: { dryRun: boolean; confirmed: boolean }): Record<string, number> {
  const params = { ...planParams(plan), dry_run: run.dryRun ? 1 : 0 };
  return run.dryRun ? params : { ...params, confirmed: run.confirmed ? 1 : 0 };
}

/** 같은 설정인가 — dry-run 통과를 비행 버튼에 이어 줄 때 쓴다. 키 순서와 무관하게 같은 글자가 나온다. */
export function planSignature(plan: FlightPlan): string {
  const params = planParams(plan);
  return Object.keys(params).sort().map((key) => `${key}=${params[key]}`).join('&');
}

/**
 * pi3 실행기가 만들 명령줄(옵션 부분) — **화면에 보여 주는 용도**다. 실제로 띄우는 것은 실행기이고,
 * 실행기가 낸 `argv` 가 상태 토픽으로 돌아오면 화면은 그것을 따로 보여 준다.
 */
/**
 * 실행기가 고르는 두 스크립트 (261022 — `SAR_FLIGHT_SCRIPTS.md` §3-3). 그때 RTK 보정이 FC 로 들어오고 있으면
 * `test_sar_rtk.py`, 아니면 RTK 확인만 뺀 `test_sar.py` 다. **고르는 것은 실행기**이고 화면은 미리 짐작만 한다.
 */
export const SCRIPT_RTK = 'test_sar_rtk.py';
export const SCRIPT_PLAIN = 'test_sar.py';

/** 보정이 들어오나 → 실행기가 띄울 스크립트. 모르면 `null`. */
export function scriptFor(corrections: boolean | null): string | null {
  if (corrections === null) return null;
  return corrections ? SCRIPT_RTK : SCRIPT_PLAIN;
}

/** `test_sar.py` 에는 `--rtk-min` · `--rtk-timeout` 이 없다. */
export function argvPreview(plan: FlightPlan, dryRun: boolean, script: string = SCRIPT_RTK): string[] {
  const argv = ['--yes', '--pattern', plan.pattern];
  if (plan.pattern !== 'rotate') argv.push('--side', plan.side);
  argv.push('--altitude', fmt(plan.altitudeM));
  if (plan.pattern !== 'rotate') argv.push('--length', fmt(plan.lengthM), '--speed', fmt(plan.speedMps));
  argv.push('--passes', String(plan.passes), '--gap', fmt(plan.gapS));
  if (plan.headingDeg !== null) argv.push('--heading', fmt(plan.headingDeg));
  argv.push('--accept-radius', fmt(plan.acceptRadiusM), '--align-hold', fmt(plan.alignHoldS), '--settle', fmt(plan.settleS),
    '--abort', plan.abort);
  if (script !== SCRIPT_PLAIN) argv.push('--rtk-min', fmt(plan.rtkMinS), '--rtk-timeout', fmt(plan.rtkTimeoutS));
  if (dryRun) argv.push('--dry-run');
  return argv;
}

function fmt(value: number): string {
  return String(Number(value.toFixed(3)));
}

/** 기수 기준 이동선 방향(도, 0 = 기수 앞, 시계방향). 회전이면 `null`. */
export function relativeBearing(plan: FlightPlan): number | null {
  return plan.pattern === 'rotate' ? null : SIDE_DEG[plan.side];
}
