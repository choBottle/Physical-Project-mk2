/**
 * src/media/parse.ts (260921 신설 — `/media` 수신 경로)
 *
 * **방식 B 프레임 한 건을 뜯는다.** 순수 함수만 있다 — 검사가 그대로 부른다.
 *
 * ```
 * [4바이트 big-endian: 헤더 길이][JSON 헤더(UTF-8)][페이로드 바이트]
 * ```
 *
 * ## 던지지 않는다
 *
 * 형식이 틀린 것은 **결과**이지 예외가 아니다. 던지면 부르는 쪽이 `try` 로 감싸고, 그러면
 * 지금 전송 계층이 그러듯 **조용히 버리는** 자리가 또 생긴다. 사유를 값으로 돌려준다.
 *
 * ## 헤더를 다시 판정하지 않는다
 *
 * `encoding` 값 어휘를 여기서 거르지 않는다 — 서버도 안 본다(값을 검증하지 않고 페이로드를
 * 열지도 않는다). 모르는 값은 그대로 들고 가고, **디코드하지 않고 상태로 표시**하는 것은
 * 화면의 몫이다. 여기서 화이트리스트로 막으면 상대가 코덱을 하나 늘릴 때마다 조용히 빈다.
 *
 * ## 헤더는 두 모양이다 (통합 데이터 규약 v2 — VZ-02 · 묶음 A)
 *
 * - **v1** — `frame_ref{source_id, capture_timestamp, sequence_id}` 객체 + `keyframe` 필수.
 * - **v2** — 평평한 프레임 헤더(규약 §3-5). 맨 위 `camera_id` · `sequence_id` · `timestamp` ·
 *   `session_id`. JPEG 는 늘 키프레임이라 `keyframe` 을 싣지 않는다.
 *
 * 가르는 기준은 서버(BE-07)와 같다 — **`frame_ref` 가 있으면 v1.** 엣지(EDGEHW-01)가 언제 바뀌어도
 * 되게 둘 다 받는다. 버퍼 키는 `(camera_id, sequence_id)` 쌍이다. 재접속하면 `sequence_id` 가 다시
 * 시작한다 — v1 은 그 리셋을 순번 역전으로만 알고, v2 는 `session_id` 가 바뀐 것으로도 안다.
 */

/** 이 프레임을 가리키는 세 칸(규약 §3-3 `frame_ref`) + 세션. 처음 손에 넣은 기기가 붙이고 서버는 그대로 전파한다. */
export type MediaFrameRef = {
  /** 카메라 — v2 `camera_id`, v1 `frame_ref.source_id`. */
  cameraId: string;
  /**
   * 프레임 시각 — v2 `timestamp`(그림을 손에 넣은 순간), v1 `frame_ref.capture_timestamp`
   * (엣지가 프레임 경계를 확정한 시각). 보정되지 않았다.
   */
  timestamp: string;
  sequenceId: number;
  /** v2 `session_id` — 순번이 다시 시작되는 경계. v1 헤더에는 없어 null. */
  sessionId: string | null;
};

export type MediaHeader = {
  frameRef: MediaFrameRef;
  /** 페이로드 코덱 **선언**. 값 어휘를 우리가 거르지 않는다. */
  encoding: string;
  /** 이 프레임만으로 디코드를 시작할 수 있는가(IDR). JPEG 는 항상 true. */
  keyframe: boolean;
  /** v1 헤더(`frame_ref` 객체)로 왔는가. 과도기 표시용 — 엣지가 다 바뀌면 지운다. */
  legacy: boolean;
  width: number;
  height: number;
  /** RFC 6381 — WebCodecs `VideoDecoderConfig.codec`. **상수로 박지 않는다**(실물이 정한다). */
  codec: string | null;
  correlationId: string | null;
};

export type MediaFrame = { header: MediaHeader; payload: Uint8Array };

/** 왜 못 뜯었는가. 화면이 세고 표시한다 — 조용히 버리는 자리를 만들지 않는다. */
export type MediaParseError =
  | 'too_short'
  | 'bad_header_length'
  | 'header_not_json'
  | 'header_shape';

export type MediaParseResult =
  | { ok: true; frame: MediaFrame }
  | { ok: false; reason: MediaParseError };

const num = (value: unknown): number | null =>
  (typeof value === 'number' && Number.isFinite(value) ? value : null);
const str = (value: unknown): string | null =>
  (typeof value === 'string' && value !== '' ? value : null);

/** v1 — `frame_ref` 객체. */
function frameRefV1(value: unknown): MediaFrameRef | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null;
  const raw = value as Record<string, unknown>;
  const cameraId = str(raw.source_id);
  const timestamp = str(raw.capture_timestamp);
  const sequenceId = num(raw.sequence_id);
  if (cameraId === null || timestamp === null || sequenceId === null) return null;
  return { cameraId, timestamp, sequenceId, sessionId: null };
}

/** v2 — 평평한 헤더의 맨 위 칸. */
function frameRefV2(raw: Record<string, unknown>): MediaFrameRef | null {
  const cameraId = str(raw.camera_id);
  const timestamp = str(raw.timestamp);
  const sequenceId = num(raw.sequence_id);
  if (cameraId === null || timestamp === null || sequenceId === null) return null;
  return { cameraId, timestamp, sequenceId, sessionId: str(raw.session_id) };
}

/**
 * 바이너리 메시지 한 건 → 헤더와 페이로드.
 *
 * 길이 칸이 **남은 바이트보다 크면** 거기서 멈춘다. 안 막으면 `subarray` 가 조용히 짧은
 * 배열을 돌려주고, 디코더가 「깨진 프레임」으로 실패해 원인이 두 단계 뒤에서 나타난다.
 */
export function parseMediaFrame(buffer: ArrayBuffer): MediaParseResult {
  if (buffer.byteLength < 4) return { ok: false, reason: 'too_short' };

  const view = new DataView(buffer);
  const headerLength = view.getUint32(0, false); // big-endian
  if (headerLength === 0 || 4 + headerLength > buffer.byteLength) {
    return { ok: false, reason: 'bad_header_length' };
  }

  const bytes = new Uint8Array(buffer);
  let parsed: unknown;
  try {
    parsed = JSON.parse(new TextDecoder().decode(bytes.subarray(4, 4 + headerLength)));
  } catch {
    return { ok: false, reason: 'header_not_json' };
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return { ok: false, reason: 'header_shape' };
  }

  const raw = parsed as Record<string, unknown>;
  const legacy = raw.frame_ref !== undefined;
  const ref = legacy ? frameRefV1(raw.frame_ref) : frameRefV2(raw);
  const encoding = str(raw.encoding);
  const width = num(raw.width);
  const height = num(raw.height);
  // `keyframe` 은 불리언이다. 없는 것을 false 로 읽으면 첫 프레임을 디코더에 안 넣고 영영 기다리게
  // 된다 — 그 화면은 「연결됨인데 영상 없음」과 구분이 안 된다. 그래서 없으면 **JPEG(v2)만** 키프레임으로
  // 보고, 그 밖(v1 전부 · v2 H.264)은 모양이 틀린 것으로 돌려준다.
  const keyframe = typeof raw.keyframe === 'boolean' ? raw.keyframe
    : (!legacy && encoding === 'jpeg' ? true : null);
  if (ref === null || encoding === null || keyframe === null
    || width === null || height === null) {
    return { ok: false, reason: 'header_shape' };
  }

  return {
    ok: true,
    frame: {
      header: {
        frameRef: ref,
        encoding,
        keyframe,
        legacy,
        width,
        height,
        codec: str(raw.codec),
        correlationId: str(raw.correlation_id),
      },
      // **복사하지 않는다.** 프레임은 30fps 로 오고 한 건이 수 KB~수백 KB 다.
      payload: bytes.subarray(4 + headerLength),
    },
  };
}

/**
 * **새 세션인가.** 보내는 쪽이 다시 뜨면 `sequence_id` 가 처음부터 시작한다. 그때 버퍼를 비우지
 * 않으면 지연 계산이 음수·거대값이 된다. v2 는 `session_id` 가 바뀐 것으로 바로 안다 — 재기동이
 * 빨라 순번이 이전보다 커진 채 다시 시작해도 놓치지 않는다. v1(세션 없음)은 **순번이 줄어든 것**으로만 안다.
 *
 * 카메라가 바뀐 것도 새 세션으로 본다 — 다른 카메라의 순번과 견줄 이유가 없다.
 */
export function isNewSession(prev: MediaFrameRef | null, next: MediaFrameRef): boolean {
  if (prev === null) return true;
  if (prev.cameraId !== next.cameraId) return true;
  if (prev.sessionId !== null && next.sessionId !== null && prev.sessionId !== next.sessionId) return true;
  return next.sequenceId < prev.sequenceId;
}
