// Monaco 에디터 본체를 public/monaco/vs 로 복사한다 (2026-10-12, 온프리미스/폐쇄망 대응).
// @monaco-editor/react 는 기본값으로 에디터 파일을 인터넷 CDN(cdn.jsdelivr.net)에서 받아온다.
// 내부망에서는 이 CDN 에 닿지 않아 코드 에디터 화면이 뜨지 않으므로, 설치된 monaco-editor 패키지의
// min/vs 를 정적 파일로 복사해 같은 서버(/monaco/vs)에서 제공한다. (lib/monacoLocal.ts 가 이 경로를 사용)
// 복사본은 재생성 가능한 산출물이라 git 에는 올리지 않는다(.gitignore: frontend/public/monaco/).
import { cpSync, existsSync, rmSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "node_modules", "monaco-editor", "min", "vs");
const dest = join(root, "public", "monaco", "vs");

if (!existsSync(join(src, "loader.js"))) {
  console.error(`[copy-monaco] 실패: ${src} 에 loader.js 가 없습니다. 'npm install' 로 monaco-editor 를 먼저 설치하세요.`);
  process.exit(1);
}

rmSync(join(root, "public", "monaco"), { recursive: true, force: true });
mkdirSync(dirname(dest), { recursive: true });
cpSync(src, dest, { recursive: true });

if (!existsSync(join(dest, "loader.js")) || !existsSync(join(dest, "editor", "editor.main.js"))) {
  console.error("[copy-monaco] 실패: 복사 후 필수 파일(loader.js, editor/editor.main.js)이 없습니다.");
  process.exit(1);
}
const version = JSON.parse(readFileSync(join(root, "node_modules", "monaco-editor", "package.json"), "utf8")).version;
console.log(`[copy-monaco] monaco-editor ${version} -> public/monaco/vs 복사 완료`);
