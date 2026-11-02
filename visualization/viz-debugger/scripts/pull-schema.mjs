// npm run schema:pull — 정본 .proto 에서 정적 모듈(protocol.js · protocol.d.ts)을 다시 뽑는다.
//
// **정본은 저장소 안의 `hardware/schema/physical_command.proto` 하나다.** 말단(로봇·드론
// 노드)이 그 파일로 만든 디스크립터(hardware/pi/common/physical_command_pb2.py)로 디코드하므로,
// 그 파일이 곧 와이어 규약이다. 가시화 쪽에는 사본을 두지 않는다 — 사본은 낡는다
// (실제로 `traceparent = 6` 이 빠진 사본이 남아 있었다).
//
// 예전에는 `origin/HW` 브랜치에서 `git show` 로 가져왔다. 모노레포가 된 뒤로는 같은
// 체크아웃 안의 파일을 그대로 읽는다 — 네트워크·브랜치 없이 늘 같은 결과가 나온다.
//
// 스키마를 고쳐야 하면 `hardware/schema/physical_command.proto` 를 고친다(필드 번호는 새로만
// 붙이고 재사용·재번호 금지). 그다음 이 스크립트를 돌리고 `verify:command-encode` 로 정본
// 바이트(fixtures/command-golden.json)와 같은지 확인한다. 저장소 루트의
// `scripts/check_contracts.py` 가 사본·생성물 어긋남을 CI 에서 잡는다.

import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const repoRoot = join(root, '..', '..');
const SOURCE = join(repoRoot, 'hardware', 'schema', 'physical_command.proto');

if (!existsSync(SOURCE)) {
  console.error(`❌ 정본이 없다: ${SOURCE}`);
  process.exit(1);
}

// .bin/*.cmd 대신 node 로 직접 부른다 — Windows 에서도 셸 없이 돈다.
const run = (name, args) => execFileSync(
  process.execPath,
  [join(root, 'node_modules', 'protobufjs-cli', 'bin', name), ...args],
  { cwd: root, stdio: 'inherit' },
);

console.log('· 정적 모듈을 다시 뽑는다 (pbjs) ← hardware/schema/physical_command.proto');
run('pbjs', ['-t', 'static-module', '-w', 'es6', '--es6', '-o', join(root, 'src', 'physical', 'protocol.js'), SOURCE]);
console.log('· 타입 선언도 다시 뽑는다 (pbts)');
run('pbts', ['-o', join(root, 'src', 'physical', 'protocol.d.ts'), join(root, 'src', 'physical', 'protocol.js')]);
console.log('✅ 끝 — 이제 `npm run verify:command-encode` 를 돌려라');
