/**
 * src/transport/envelope.ts (261014 신설 — 통합 데이터 규약 v2 VZ-01)
 *
 * **봉투의 공통 머리를 읽는 곳은 여기 하나다.** 새 이름(v2)을 먼저 읽고, 없으면 옛 이름.
 *
 * 화면은 두 송신기를 동시에 상대한다 — 실제 서버(BE-08 뒤 새 이름)와 목 게이트웨이(규약 단계 5까지
 * 옛 이름, V6). 그래서 이 함수들은 **단계 5에서 목 게이트웨이까지 바꾼 뒤에** 정리한다. 그 전에 지우면
 * 목 게이트웨이로 돌리는 시연이 깨진다.
 */

import type { Envelope } from './types.ts';

/** 장비(또는 프로그램) id — `source_id` · 옛 `entity`. */
export const envSource = (e: Pick<Envelope, 'source_id' | 'entity'>): string => e.source_id ?? e.entity ?? '';

/** 데이터 시각(ISO) — `timestamp` · 옛 `ts`. 없으면 빈 글자(`Date.parse` 가 NaN 을 낸다). */
export const envTime = (e: Pick<Envelope, 'timestamp' | 'ts'>): string => e.timestamp ?? e.ts ?? '';

/** 순번 — `sequence_id` · 옛 `seq`. */
export const envSeq = (e: Pick<Envelope, 'sequence_id' | 'seq'>): number => e.sequence_id ?? e.seq ?? 0;
