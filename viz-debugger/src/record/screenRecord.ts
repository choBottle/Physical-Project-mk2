/**
 * src/record/screenRecord.ts (261007 신설 — 실시간 화면 녹화)
 *
 * **지금 눈으로 보고 있는 영상 칸을 그대로 녹화한다.** 목적은 「실시간으로 본 것을 나중에 다시 확인」이다(261007 지시).
 *
 * ## 왜 영상 요소를 바로 녹화하지 않나
 *
 * 카메라 · 추론 · Unity 상공 카메라는 다른 주소의 MJPEG 를 `<img>` 로 띄운다. 그런 그림을 캔버스에 옮기면 브라우저가
 * 그 캔버스의 녹화를 막는다(다른 출처). 3D 가상환경은 틀(iframe)이라 아예 꺼낼 수 없다. 그래서 **탭 화면을 찍고**
 * (`getDisplayMedia` · 이 탭) 그중 영상 칸만 남긴다 — 눈에 보이는 픽셀 그대로이고, 영상을 한 번 더 받지 않으므로 원본
 * 장비와 망에는 부담이 없다.
 *
 *   남기는 법   `restrictTo`(요소 캡처) 가 있으면 그것 — 그 요소만 찍혀 위에 얹힌 녹화 버튼 · 알림이 안 찍힌다.
 *               없으면 `cropTo`(영역 캡처) — 그 칸의 네모만큼 자른다. 위에 얹힌 것도 같이 찍힌다.
 *   확인 창     Chrome 이 「이 탭 공유」를 묻는다. 웹 페이지가 끌 수 없다 — 그대로 띄운다(261007 결정).
 *               공유는 녹화마다 따로 받고 멈추면 놓는다 — 한 벌을 복제해 나누면 Chrome 이 잘라내기를 거절한다
 *               (261022 수정). 그래서 동시에 여럿을 녹화하면 확인도 녹화마다 뜬다.
 *   저장        1초 조각을 개발 서버 창구로 보내 저장소 루트 `video/` 에 이어 쓴다(`scripts/video-records.mjs`).
 *   닫으면      녹화 버튼이 내려가면(창을 닫음) 그 녹화를 멈추고 저장한다(261007 결정). Chrome 의 「공유 중지」를
 *               누르면 그 녹화가 멈추고 저장된다.
 *
 * Chrome 전용이다(사용자 환경 · 261007). 요소 캡처 · 영역 캡처가 둘 다 없는 브라우저면 버튼이 사유를 적는다.
 */

import { useSyncExternalStore } from 'react';
import { t } from '../i18n/dict.ts';

const SAVE_URL = '/video-records';
const SLICE_MS = 1000;
const BITS_PER_SECOND = 4_000_000;
/** 끝난 녹화를 알림에 남겨 두는 시간 — 저장된 경로를 읽을 틈. 실패는 사람이 닫을 때까지 둔다. */
const SAVED_SHOWN_MS = 8000;

export type RecordingPhase = 'starting' | 'recording' | 'saving' | 'saved' | 'failed';

export type Recording = {
  id: string;
  label: string;
  phase: RecordingPhase;
  startedAtMs: number;
  bytes: number;
  /** 저장소 루트 기준 경로(`video/…`). 저장이 끝나야 생긴다. */
  path: string | null;
  error: string | null;
};

type Live = {
  recorder: MediaRecorder | null;
  track: MediaStreamTrack | null;
  saveId: string | null;
  chain: Promise<void>;
};

let recordings: readonly Recording[] = [];
const live = new Map<string, Live>();
const listeners = new Set<() => void>();
let serial = 0;

function emit(): void {
  for (const listener of listeners) listener();
}

function patch(id: string, change: Partial<Recording>): void {
  recordings = recordings.map((item) => (item.id === id ? { ...item, ...change } : item));
  emit();
}

function drop(id: string): void {
  recordings = recordings.filter((item) => item.id !== id);
  emit();
}

export function subscribeRecordings(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

const snapshot = () => recordings;

export function useRecordings(): readonly Recording[] {
  return useSyncExternalStore(subscribeRecordings, snapshot, snapshot);
}

/** 지금 도는(멈추는 중 포함) 녹화인가. */
export function isActive(item: Recording): boolean {
  return item.phase === 'starting' || item.phase === 'recording' || item.phase === 'saving';
}

export function dismissRecording(id: string): void {
  if (!live.has(id)) drop(id);
}

// ── 브라우저가 해 주는 것 ──────────────────────────────────────────────

type ElementTarget = { fromElement(element: Element): Promise<unknown> };
type TrackWith = MediaStreamTrack & { restrictTo?(target: unknown): Promise<void>; cropTo?(target: unknown): Promise<void> };

function targetApi(): { kind: 'restrict' | 'crop'; api: ElementTarget } | null {
  const scope = globalThis as unknown as { RestrictionTarget?: ElementTarget; CropTarget?: ElementTarget };
  if (scope.RestrictionTarget !== undefined) return { kind: 'restrict', api: scope.RestrictionTarget };
  if (scope.CropTarget !== undefined) return { kind: 'crop', api: scope.CropTarget };
  return null;
}

/** 이 브라우저에서 녹화가 안 되면 그 사유(사전 키), 되면 null. */
export function unsupportedReason(): string | null {
  if (typeof navigator === 'undefined' || navigator.mediaDevices?.getDisplayMedia === undefined) return 'rec.noCapture';
  if (typeof MediaRecorder === 'undefined') return 'rec.noRecorder';
  if (targetApi() === null) return 'rec.noElementCapture';
  return null;
}

/**
 * 크롬이 되는 것부터 고른다. **mp4(H.264) 가 먼저다** (261022 사용자 결정 — 저장 형식은 mp4).
 *
 * 주의: 칸을 잘라 찍으면 칸 크기가 바뀔 때 인코더가 새 크기로 다시 서는데, 크롬의 mp4 는 그때 나온 새 설정
 * (SPS · PPS)을 버리고 첫 설정만 파일 머리에 남겨 그 뒤 영상이 깨진다. 그래서 녹화 중에는 칸이 움직이지 않게
 * 막는다(`lockView.ts`). 창 크기 조절처럼 못 막는 변화가 생기면 그 뒤가 깨질 수 있다 — webm(VP9) 은 견딘다.
 */
function pickFormat(): { mimeType: string; ext: 'mp4' | 'webm' } {
  const candidates: Array<[string, 'mp4' | 'webm']> = [
    ['video/mp4;codecs=avc1.42E01F', 'mp4'],
    ['video/mp4;codecs=avc1', 'mp4'],
    ['video/mp4', 'mp4'],
    ['video/webm;codecs=vp9', 'webm'],
    ['video/webm;codecs=vp8', 'webm'],
    ['video/webm', 'webm'],
  ];
  for (const [mimeType, ext] of candidates) if (MediaRecorder.isTypeSupported(mimeType)) return { mimeType, ext };
  return { mimeType: '', ext: 'webm' };
}

/**
 * **녹화마다 탭 공유를 따로 받는다.** 한 벌을 받아 `clone()` 해 나눠 쓰면 Chrome 이 복제본이 딸린 트랙의
 * `restrictTo` · `cropTo` 를 거절한다(잘라내기는 트랙이 아니라 공유 원본에 걸리기 때문). 그래서 녹화는 제 공유의
 * 원본 트랙을 그대로 잘라 쓰고, 멈추면 그 공유를 놓는다. 대신 동시에 여럿을 녹화하면 확인 창도 녹화마다 뜬다.
 */
function shareTab(): Promise<MediaStream> {
  const options = {
    video: { frameRate: 30, displaySurface: 'browser' },
    audio: false,
    // 이 탭을 먼저 내민다 — 다른 탭 · 창을 고르면 칸을 잘라낼 수 없다.
    preferCurrentTab: true,
    selfBrowserSurface: 'include',
    surfaceSwitching: 'exclude',
    monitorTypeSurfaces: 'exclude',
  } as unknown as DisplayMediaStreamOptions;
  return navigator.mediaDevices.getDisplayMedia(options);
}

/** 그 칸만 남긴다. 요소 캡처가 거절되면 영역 캡처로 한 번 더 해 본다. 둘 다 안 되면 브라우저가 준 사유를 붙여 알린다. */
async function narrowTo(track: TrackWith, element: Element): Promise<void> {
  const scope = globalThis as unknown as { RestrictionTarget?: ElementTarget; CropTarget?: ElementTarget };
  let lastError: unknown = null;
  if (scope.RestrictionTarget !== undefined && track.restrictTo !== undefined) {
    try { await track.restrictTo(await scope.RestrictionTarget.fromElement(element)); return; } catch (error) { lastError = error; }
  }
  if (scope.CropTarget !== undefined && track.cropTo !== undefined) {
    try { await track.cropTo(await scope.CropTarget.fromElement(element)); return; } catch (error) { lastError = error; }
  }
  const detail = lastError instanceof Error ? `${lastError.name}: ${lastError.message}` : String(lastError);
  throw new Error(t('rec.narrowFailed', { detail }));
}

async function post(path: string, body?: BodyInit, json = false): Promise<Record<string, unknown>> {
  const response = await fetch(`${SAVE_URL}/${path}`, {
    method: 'POST',
    body,
    headers: json ? { 'Content-Type': 'application/json' } : { 'Content-Type': 'application/octet-stream' },
  });
  const data = await response.json().catch(() => ({})) as Record<string, unknown>;
  if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : `HTTP ${response.status}`);
  return data;
}

/** 저장 창구가 있는가 — 단독 빌드 · 정적 서버에는 없다. 한 번만 묻는다. */
let saverCheck: Promise<boolean> | null = null;
export function saverAvailable(): Promise<boolean> {
  saverCheck ??= fetch(`${SAVE_URL}/ping`, { cache: 'no-store' })
    .then(async (response) => response.ok && (await response.json().catch(() => null))?.ok === true)
    .catch(() => false);
  return saverCheck;
}

function errorText(error: unknown): string {
  if (error instanceof DOMException && error.name === 'NotAllowedError') return t('rec.denied');
  return error instanceof Error ? error.message : String(error);
}

/**
 * 그 요소를 녹화하기 시작한다. **버튼 누름 안에서 곧바로 불러야 한다** — 확인 창은 사람이 누른 직후에만 뜬다.
 * 돌려주는 id 로 멈춘다.
 */
export function startRecording(element: Element, label: string): string {
  serial += 1;
  const id = `rec-${Date.now().toString(36)}-${serial}`;
  recordings = [...recordings, { id, label, phase: 'starting', startedAtMs: Date.now(), bytes: 0, path: null, error: null }];
  const state: Live = { recorder: null, track: null, saveId: null, chain: Promise.resolve() };
  live.set(id, state);
  emit();

  const fail = (error: unknown) => {
    state.track?.stop();
    live.delete(id);
    patch(id, { phase: 'failed', error: errorText(error) });
  };

  if (targetApi() === null) { fail(new Error(t('rec.noElementCapture'))); return id; }
  // 확인 창을 먼저 띄운다 — 누름 직후여야 뜬다. 저장 창구 확인 · 칸 잘라내기는 그 뒤에 한다.
  const sharing = shareTab();
  void (async () => {
    try {
      const stream = await sharing;
      const track = stream.getVideoTracks()[0] as TrackWith | undefined;
      state.track = track ?? null;
      if (track === undefined) { for (const other of stream.getTracks()) other.stop(); throw new Error(t('rec.noTrack')); }
      // 확인 창을 기다리는 사이에 창을 닫았다 — 방금 받은 공유를 놓는다(공유 중 표시줄이 남지 않게).
      if (!live.has(id)) { track.stop(); return; }
      const surface = (track.getSettings() as { displaySurface?: string }).displaySurface;
      if (surface !== undefined && surface !== 'browser') throw new Error(t('rec.notThisTab'));
      await narrowTo(track, element);
      const opened = await post('open', JSON.stringify({ label, ext: pickFormat().ext }), true);
      state.saveId = String(opened.id);
      if (!live.has(id)) { track.stop(); await post(`close?id=${encodeURIComponent(state.saveId)}`); drop(id); return; }
      const format = pickFormat();
      const recorder = new MediaRecorder(new MediaStream([track]), {
        ...(format.mimeType === '' ? {} : { mimeType: format.mimeType }),
        videoBitsPerSecond: BITS_PER_SECOND,
      });
      state.recorder = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size === 0 || state.saveId === null) return;
        const saveId = state.saveId;
        // 조각은 **차례대로** 붙여야 한다 — 앞 조각이 끝난 뒤에 다음을 보낸다.
        state.chain = state.chain.then(async () => {
          const result = await post(`append?id=${encodeURIComponent(saveId)}`, event.data);
          patch(id, { bytes: Number(result.bytes) || 0 });
        }).catch((error) => { patch(id, { error: errorText(error) }); });
      };
      // Chrome 의 「공유 중지」를 누르거나 칸이 사라져 트랙이 끝나면 저장으로 넘어간다.
      track.addEventListener('ended', () => { void stopRecording(id); });
      recorder.start(SLICE_MS);
      patch(id, { phase: 'recording', startedAtMs: Date.now(), path: String(opened.path ?? '') || null });
    } catch (error) {
      fail(error);
    }
  })();
  return id;
}

/** 멈추고 저장한다. 이미 멈췄거나 없는 녹화면 아무것도 안 한다. */
export async function stopRecording(id: string): Promise<void> {
  const state = live.get(id);
  if (state === undefined) return;
  live.delete(id);
  const recorder = state.recorder;
  if (recorder === null) {
    // 아직 확인 창 · 준비 중이었다 — 찍은 것이 없다.
    state.track?.stop();
    drop(id);
    return;
  }
  patch(id, { phase: 'saving' });
  if (recorder.state !== 'inactive') {
    await new Promise<void>((resolve) => {
      recorder.addEventListener('stop', () => resolve(), { once: true });
      recorder.stop();
    });
  }
  state.track?.stop();
  try {
    await state.chain;
    const closed = await post(`close?id=${encodeURIComponent(state.saveId ?? '')}`);
    if (closed.path === null) throw new Error(t('rec.empty'));
    patch(id, { phase: 'saved', path: String(closed.path), bytes: Number(closed.bytes) || 0 });
    setTimeout(() => drop(id), SAVED_SHOWN_MS);
  } catch (error) {
    patch(id, { phase: 'failed', error: errorText(error) });
  }
}
