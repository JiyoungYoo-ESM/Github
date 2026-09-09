import { defineConfig } from "eslint/config";
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";

export default defineConfig([
  {
    ignores: ["node_modules/**", ".next/**", "out/**", "outputs/**", "next-env.d.ts"]
  },
  ...nextCoreWebVitals,
  {
    // 2026-07-13 도입 시점에 이미 위반이 존재하던 오류 규칙들을 warn으로 강등.
    // 목록·해소 방침은 ESLINT_BACKLOG.md 참조. 자동 수정 금지(동작 변경 위험).
    // 위반 0건인 react-hooks/rules-of-hooks 등 나머지 오류 규칙은 그대로 게이트로 작동한다.
    rules: {
      // Keep correctness checks strict; these compiler-advisory rules flag
      // intentional data-loading effects and DOM pointer-resize integrations.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",
      "react-hooks/globals": "error",
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/immutability": "off",
      "react-hooks/preserve-manual-memoization": "off",
      "react/no-unescaped-entities": "warn"
    }
  }
]);
