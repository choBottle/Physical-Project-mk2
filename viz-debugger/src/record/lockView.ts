/**
 * src/record/lockView.ts (261022 신설 — 녹화 중 화면 고정)
 *
 * **녹화하는 동안 그 칸이 움직이거나 커지고 작아지지 않게 막는다.** 녹화는 탭 화면에서 칸만 잘라 찍으므로
 * (`screenRecord.ts`) 칸이 스크롤로 화면 끝에 걸리거나 끌려 가거나 확대되면 찍히는 크기가 바뀌고, 인코더가 새 크기로
 * 다시 선다. 크롬 mp4 는 그 순간부터 영상이 깨지므로(`screenRecord.ts` 의 pickFormat) 여기서 막는다.
 *
 *   스크롤    칸을 품은 스크롤 상자(캔버스 · 창 · 페이지)의 휠 · 스크롤 키를 막고, 스크롤바를 끌어도 제자리로 돌린다.
 *             칸과 상관없는 상자(옆의 로그 목록 등)는 그대로 스크롤된다.
 *   끌기      칸을 품은 캔버스 카드(`.view-node`)의 끌기 · 크기 조절 · 더블클릭 확대를 막는다. 카드의 버튼은 눌린다.
 *   확대      Chrome 확대(Ctrl + 휠 · Ctrl + +/-/0)를 막는다.
 *
 * 창 크기 조절 · 개발자 도구처럼 웹 페이지가 막을 수 없는 것은 남는다. 막은 동작이 있으면 `subscribeBlocked` 로 알린다.
 */

type Saved = { element: Element; top: number; left: number };
type Lock = { host: Element; scrollers: Saved[]; card: Element | null };

const locks = new Map<string, Lock>();
const blockedListeners = new Set<() => void>();
let lastBlockedMs = 0;

function isScroller(element: Element): boolean {
  if (element === document.scrollingElement) return true;
  const style = getComputedStyle(element);
  return /(auto|scroll|overlay)/.test(`${style.overflowX} ${style.overflowY}`);
}

function scrollersOf(element: Element): Saved[] {
  const found: Saved[] = [];
  for (let node = element.parentElement; node !== null; node = node.parentElement) {
    if (isScroller(node)) found.push({ element: node, top: node.scrollTop, left: node.scrollLeft });
  }
  const page = document.scrollingElement;
  if (page !== null && !found.some((item) => item.element === page)) found.push({ element: page, top: page.scrollTop, left: page.scrollLeft });
  return found;
}

function lockedScroller(element: Element): Saved | undefined {
  for (const lock of locks.values()) {
    const hit = lock.scrollers.find((item) => item.element === element);
    if (hit !== undefined) return hit;
  }
  return undefined;
}

function insideHost(target: EventTarget | null): boolean {
  if (!(target instanceof Node)) return false;
  for (const lock of locks.values()) if (lock.host.contains(target)) return true;
  return false;
}

function blocked(): void {
  const now = Date.now();
  if (now - lastBlockedMs < 300) return;
  lastBlockedMs = now;
  for (const listener of blockedListeners) listener();
}

/** 이 휠이 스크롤할 첫 상자를 찾는다 — 그 방향으로 더 갈 수 있는 가장 가까운 스크롤 상자. */
function wheelScroller(target: EventTarget | null, dx: number, dy: number): Element | null {
  let node: Element | null = target instanceof Element ? target : target instanceof Node ? target.parentElement : null;
  for (; node !== null; node = node.parentElement) {
    if (!isScroller(node)) continue;
    const canY = dy !== 0 && (dy > 0 ? node.scrollTop + node.clientHeight < node.scrollHeight - 1 : node.scrollTop > 0);
    const canX = dx !== 0 && (dx > 0 ? node.scrollLeft + node.clientWidth < node.scrollWidth - 1 : node.scrollLeft > 0);
    if (canY || canX) return node;
  }
  return document.scrollingElement;
}

function onWheel(event: WheelEvent): void {
  if (event.ctrlKey || event.metaKey) {
    event.preventDefault();
    blocked();
    return;
  }
  const scroller = wheelScroller(event.target, event.deltaX, event.deltaY);
  if (scroller !== null && lockedScroller(scroller) !== undefined) {
    event.preventDefault();
    // 칸 위의 휠은 칸 자신이 쓴다(상공 카메라 확대 등) — 알림은 띄우지 않는다.
    if (!insideHost(event.target)) blocked();
  }
}

const SCROLL_KEYS = new Set(['PageUp', 'PageDown', 'Home', 'End', ' ', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']);

function editable(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
}

function onKeyDown(event: KeyboardEvent): void {
  if ((event.ctrlKey || event.metaKey) && ['+', '-', '=', '0'].includes(event.key)) {
    event.preventDefault();
    blocked();
    return;
  }
  if (!SCROLL_KEYS.has(event.key) || editable(event.target) || event.target instanceof HTMLButtonElement) return;
  const start = event.target instanceof Element ? event.target : document.body;
  for (let node: Element | null = start; node !== null; node = node.parentElement) {
    if (lockedScroller(node) !== undefined || node === document.body) {
      event.preventDefault();
      blocked();
      return;
    }
    if (isScroller(node)) return;
  }
}

/** 스크롤바를 끌거나 화면이 스스로 스크롤했다 — 잠근 상자면 제자리로 돌린다. */
function onScroll(event: Event): void {
  const target = event.target === document ? document.scrollingElement : event.target;
  if (!(target instanceof Element)) return;
  const saved = lockedScroller(target);
  if (saved === undefined || (target.scrollTop === saved.top && target.scrollLeft === saved.left)) return;
  target.scrollTop = saved.top;
  target.scrollLeft = saved.left;
  blocked();
}

const PRESSABLE = 'button, a, input, select, textarea, summary, label, [role="button"]';

function inLockedCard(target: EventTarget | null): boolean {
  if (!(target instanceof Element) || target.closest(PRESSABLE) !== null) return false;
  for (const lock of locks.values()) if (lock.card !== null && lock.card.contains(target)) return true;
  return false;
}

/** 카드 끌기 · 크기 조절 · 확대는 React 가 받기 전에(창 단계 캡처) 멈춘다. 칸 위를 눌러도 카드가 끌리므로 칸도 막는다. */
function onPointerDown(event: Event): void {
  if (!inLockedCard(event.target)) return;
  event.stopPropagation();
  event.preventDefault();
  blocked();
}

function onDoubleClick(event: Event): void {
  if (!inLockedCard(event.target)) return;
  event.stopPropagation();
  event.preventDefault();
  blocked();
}

const listenerOptions = { capture: true, passive: false } as const;

function install(): void {
  window.addEventListener('wheel', onWheel, listenerOptions);
  window.addEventListener('keydown', onKeyDown, listenerOptions);
  window.addEventListener('pointerdown', onPointerDown, listenerOptions);
  window.addEventListener('dblclick', onDoubleClick, listenerOptions);
  document.addEventListener('scroll', onScroll, { capture: true });
}

function uninstall(): void {
  window.removeEventListener('wheel', onWheel, listenerOptions);
  window.removeEventListener('keydown', onKeyDown, listenerOptions);
  window.removeEventListener('pointerdown', onPointerDown, listenerOptions);
  window.removeEventListener('dblclick', onDoubleClick, listenerOptions);
  document.removeEventListener('scroll', onScroll, { capture: true });
}

/** 그 녹화(`id`)의 칸(`host`)을 고정한다. 돌려주는 함수로 푼다. 녹화가 여럿이면 다 풀릴 때 감시를 걷는다. */
export function lockView(id: string, host: Element): () => void {
  if (locks.size === 0) install();
  locks.set(id, { host, scrollers: scrollersOf(host), card: host.closest('.view-node') });
  return () => {
    if (!locks.delete(id)) return;
    if (locks.size === 0) uninstall();
  };
}

/** 막은 동작이 있을 때 불린다(0.3초에 한 번까지). */
export function subscribeBlocked(listener: () => void): () => void {
  blockedListeners.add(listener);
  return () => { blockedListeners.delete(listener); };
}
