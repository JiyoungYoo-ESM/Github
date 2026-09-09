# ESLint 백로그 (2026-07-13 도입 시점 기준선)

> ESLint(next/core-web-vitals) 도입 시점에 이미 존재하던 위반 81건의 기록. **자동 수정 금지** — 특히 exhaustive-deps와 set-state-in-effect는 기계적으로 고치면 useEffect 실행 시점이 바뀌어 동작이 변한다(IMPROVEMENT_PLAN.md 2번 항목).
> 도입 시점에 오류였던 규칙은 eslint.config.mjs에서 warn으로 강등해 CI 게이트를 통과시키되 이 문서로 관리한다. 위반 0건인 react-hooks/rules-of-hooks는 error를 유지한다.
> 해소 시점: IMPROVEMENT_PLAN 5번(워크스페이스 해체) 때 화면 단위로 검토하며 정리 권장.

## 2026-07-21 현황 갱신 (IMPROVEMENT_PLAN 9번: 경고/deprecated 제거)

- **해소됨(0건)**: `react/no-unescaped-entities`(10건 전부 `&quot;`/`&apos;`로 교체), `@next/next/no-img-element`(4건 전부 `next/image`로 교체). `npm run lint:ci`의 경고 예산을 14 → **0**으로 낮춰 회귀를 막는다.
- **여전히 off인 규칙 3종은 그대로 둔다** — `eslint.config.mjs`에서 일시적으로 `warn`으로 켜서 진단한 결과, 오늘 기준 **49건**(set-state-in-effect 45 + immutability 4, preserve-manual-memoization은 0으로 이미 해소)이 여전히 남아 있음을 확인했다. 이 문서 서두의 경고(기계적으로 고치면 동작이 바뀜)가 그대로 유효하므로, 화면 단위로 실제 useEffect 실행 시점을 검증하며 정리하는 별도 작업으로 남긴다(설정은 이번에 손대지 않음 — off 유지).
- `react-hooks/exhaustive-deps`/`globals`은 계속 `error`로 유지되고 있고 현재 위반 0건이라 게이트가 이미 작동 중이다.

## 규칙별 집계

| 건수 | 규칙 | 도입 시점 심각도 |
|---|---|---|
| 41 | react-hooks/set-state-in-effect | error → warn 강등 |
| 16 | react-hooks/exhaustive-deps | warn |
| 10 | react/no-unescaped-entities | error → warn 강등 |
| 5 | react-hooks/immutability | error → warn 강등 |
| 4 | @next/next/no-img-element | warn |
| 3 | react-hooks/preserve-manual-memoization | error → warn 강등 |
| 1 | react-hooks/incompatible-library | warn |
| 1 | react-hooks/globals | error → warn 강등 |

## 전체 목록

### app/about/AboutContent.tsx
- L219 [react/no-unescaped-entities] `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`.
- L219 [react/no-unescaped-entities] `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`.
- L291 [react/no-unescaped-entities] `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`.
- L291 [react/no-unescaped-entities] `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`.

### app/dashboard/DashboardClient.tsx
- L180 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders

### app/esm/page.tsx
- L110 [react/no-unescaped-entities] `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`.
- L113 [react/no-unescaped-entities] `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`.
- L122 [react/no-unescaped-entities] `'` can be escaped with `&apos;`, `&lsquo;`, `&#39;`, `&rsquo;`.
- L122 [react/no-unescaped-entities] `'` can be escaped with `&apos;`, `&lsquo;`, `&#39;`, `&rsquo;`.

### app/login/page.tsx
- L76 [@next/next/no-img-element] Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom 
- L92 [@next/next/no-img-element] Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom 

### app/order-review/OrderReviewClient.tsx
- L34 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders

### components/auth/AuthGuard.tsx
- L31 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders

### components/landing/LandingFooter.tsx
- L16 [@next/next/no-img-element] Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom 

### components/landing/LandingNav.tsx
- L17 [@next/next/no-img-element] Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom 

### components/layout/AppRouteLoader.tsx
- L95 [react-hooks/exhaustive-deps] React Hook useEffect has a missing dependency: 'showLoader'. Either include it or remove the dependency array.

### components/layout/GlobalSkuSearch.tsx
- L37 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders

### components/order-analysis/OrderAnalysisClient.tsx
- L53 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders

### components/order-review/OrderReviewTable.tsx
- L417 [react-hooks/incompatible-library] Compilation Skipped: Use of incompatible library

### components/order-review/SkuStockGapDrawer.tsx
- L81 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders

### components/redesign/SiliconAnalyticsWorkspace.tsx
- L293 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L1444 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L2530 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L2568 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L2633 [react-hooks/immutability] Error: This value cannot be modified
- L2634 [react-hooks/immutability] Error: This value cannot be modified
- L2653 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L2658 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L3118 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L3176 [react-hooks/immutability] Error: This value cannot be modified
- L3177 [react-hooks/immutability] Error: This value cannot be modified
- L3196 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L3201 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L3209 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L4403 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L4789 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L5057 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L5144 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L5767 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L5901 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L5913 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L5935 [react-hooks/preserve-manual-memoization] Compilation Skipped: Existing memoization could not be preserved
- L5984 [react-hooks/exhaustive-deps] The 'selectedBrandMetrics' array makes the dependencies of useCallback Hook (at line 6082) change on every render. To fi
- L6565 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L7399 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L7428 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L7450 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L7461 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L8025 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L8339 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L8343 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L8512 [react-hooks/preserve-manual-memoization] Compilation Skipped: Existing memoization could not be preserved
- L8722 [react-hooks/preserve-manual-memoization] Compilation Skipped: Existing memoization could not be preserved
- L8746 [react/no-unescaped-entities] `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`.
- L8746 [react/no-unescaped-entities] `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`.
- L9214 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L9266 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L9420 [react-hooks/exhaustive-deps] The 'reportBasisRows' array makes the dependencies of useCallback Hook (at line 9506) change on every render. To fix thi
- L9446 [react-hooks/exhaustive-deps] The 'metricRows' array makes the dependencies of useCallback Hook (at line 9506) change on every render. To fix this, wr
- L9463 [react-hooks/exhaustive-deps] The 'summaryRows' array makes the dependencies of useCallback Hook (at line 9506) change on every render. To fix this, w
- L10194 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders

### components/season-trend/CountryInsightMap.tsx
- L503 [react-hooks/exhaustive-deps] React Hook useMemo has a missing dependency: 'mappedCountryIds.length'. Either include it or remove the dependency array
- L506 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders

### components/season-trend/GlobalDemandTab.tsx
- L1705 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L1745 [react-hooks/exhaustive-deps] React Hook useMemo has a missing dependency: 'isCountryInScope'. Either include it or remove the dependency array.
- L1770 [react-hooks/exhaustive-deps] React Hook useMemo has a missing dependency: 'isCountryInScope'. Either include it or remove the dependency array.
- L1780 [react-hooks/exhaustive-deps] React Hook useMemo has a missing dependency: 'isCountryInScope'. Either include it or remove the dependency array.
- L1832 [react-hooks/exhaustive-deps] React Hook useMemo has a missing dependency: 'isCountryInScope'. Either include it or remove the dependency array.
- L1842 [react-hooks/exhaustive-deps] React Hook useMemo has a missing dependency: 'isCountryInScope'. Either include it or remove the dependency array.
- L1920 [react-hooks/exhaustive-deps] React Hook useMemo has a missing dependency: 'isCountryInScope'. Either include it or remove the dependency array.
- L1940 [react-hooks/exhaustive-deps] React Hook useMemo has a missing dependency: 'isCountryInScope'. Either include it or remove the dependency array.
- L1986 [react-hooks/exhaustive-deps] React Hook useMemo has a missing dependency: 'isCountryInScope'. Either include it or remove the dependency array.
- L2028 [react-hooks/exhaustive-deps] React Hook useMemo has a missing dependency: 'isCountryInScope'. Either include it or remove the dependency array.

### components/season-trend/SeasonTrendUploadPanel.tsx
- L122 [react-hooks/globals] Error: Cannot reassign variables declared outside of the component/hook

### components/sku-concentration/SkuConcentrationClient.tsx
- L181 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L216 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders

### components/stock-gap/StockGapClient.tsx
- L198 [react-hooks/immutability] Error: Cannot reassign variable after render completes
- L417 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders
- L465 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders

### components/upload/ExchangeRateField.tsx
- L38 [react-hooks/set-state-in-effect] Error: Calling setState synchronously within an effect can trigger cascading renders

### components/upload/useUploadWorkflow.ts
- L272 [react-hooks/exhaustive-deps] React Hook useEffect has a missing dependency: 'handleQuickFilesChange'. Either include it or remove the dependency arra
