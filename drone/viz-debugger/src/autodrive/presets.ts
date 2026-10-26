/**
 * src/autodrive/presets.ts (260929 신설 — 장애물 탐지 영상 주소 고르기)
 *
 * **연결 관리의 「장애물 탐지 영상」 줄마다 고르는 칸.** 로봇 브로커(`physical/presets.ts`)와 같은 모양이다 —
 * 두 대상의 줄이 같은 꼴이어야 한 판에서 읽힌다(260929 지시 「로봇 쪽이랑 UI 구성을 맞추자」).
 *
 * 주소는 이 폴더 밖에 적지 않는다(`verify:autodrive-ai` — AI 서버 주소는 경계 안).
 *
 * ## 주소는 환경변수에서 온다 (공개 저장소 정리)
 *
 * 팀이 쓰는 실제 서버 주소는 소스에 적지 않는다 — `.env.local`(커밋 안 됨)에 둔다. 값이 없으면
 * 그 줄은 목록에 안 생긴다(빈 프리셋을 만들지 않는 `physical/presets.ts` 와 같은 규칙). 변수는 `.env.example`.
 *
 * 환경변수는 `(import.meta …).env?.VITE_…` 를 **그 자리에서** 읽는다 — Vite 빌드는 이 꼴만 값으로 바꾼다
 * (`const meta = import.meta` 처럼 중간 변수를 두면 빌드 결과에서 늘 비어 있다).
 */

export type AiPreset = {
  id: string;
  labelKey: string;
  /** 빈 문자열이면 아직 값이 없다 — 화면이 고를 수 없게 막는다. `manual` 만 예외다. */
  url: string;
  whyKey: string;
};

/** Go1 앞 카메라 AI 서버 (260915 사용자가 준 주소 — `VITE_AUTODRIVE_AI_GO1`). 없으면 빈 문자열. */
export const AI_GO1_BASE: string = (import.meta as unknown as { env?: Record<string, string | undefined> }).env?.VITE_AUTODRIVE_AI_GO1 ?? '';
/** 드론 카메라 AI 서버 (260929 사용자가 준 주소 — `VITE_AUTODRIVE_AI_DRONE`). 없으면 빈 문자열. */
export const AI_DRONE_BASE: string = (import.meta as unknown as { env?: Record<string, string | undefined> }).env?.VITE_AUTODRIVE_AI_DRONE ?? '';

export const AI_PRESETS: readonly AiPreset[] = [
  { id: 'go1', labelKey: 'preset.ai.go1', url: AI_GO1_BASE, whyKey: 'preset.ai.go1.why' },
  { id: 'drone', labelKey: 'preset.ai.drone', url: AI_DRONE_BASE, whyKey: 'preset.ai.drone.why' },
  { id: 'manual', labelKey: 'preset.manual', url: '', whyKey: 'preset.manual.why' },
  // 주소가 안 정해진 줄은 목록에 두지 않는다 — 직접 입력으로 넣는다.
].filter((preset) => preset.id === 'manual' || preset.url.trim() !== '');

export function aiPresetReady(preset: AiPreset): boolean {
  return preset.id === 'manual' || preset.url.trim() !== '';
}
