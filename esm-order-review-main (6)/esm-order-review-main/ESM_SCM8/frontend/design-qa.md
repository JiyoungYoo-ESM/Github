# Customer Support · Microsoft Forms Design QA

- Source visual truth: `C:\Users\USER\OneDrive - (주)실리콘투\바탕 화면\silicon2_customer_center_mockup.html`
- Implementation: `/support` (`components/redesign/screens/support/CustomerSupportScreen.tsx`)
- Implementation screenshot: `artifacts/support-forms-qa/implementation-support-forms.png`
- Viewport: Chrome desktop, browser default viewport
- Source dimensions/density: responsive HTML; a normalized source capture was blocked by the browser's local-file security policy
- State: 문의하기 tab with an authenticated, organization-only Microsoft Forms launch card

## Full-view comparison evidence

The implementation was rendered in Chrome. The original local HTML mockup could not be claimed for a same-input side-by-side comparison because browser control blocks `file://` pages. This prevents a formal visual-fidelity pass even though the implementation capture is available.

## Focused region comparison evidence

- Header tabs, FAQ list, Forms embed, and processing-status guidance were inspected in the browser.
- The launch card shows the company-account guidance, the Forms CTA, and a new-window fallback without leaving a broken iframe region.
- A focused side-by-side image could not be produced because the source local-file tab was blocked.

## Findings

- [P1] The live Forms embed is blocked in the deployment browser.
  - Location: 문의하기 tab.
  - Evidence: the iframe rendered as a large gray broken-document area.
  - Impact: users cannot reach the inquiry fields in the customer-center page.
  - Fix: use the stable external Forms launch card; the broken iframe has been removed.
- [P2] Formal source-vs-implementation visual comparison is blocked.
  - Location: full customer-center screen.
  - Evidence: implementation screenshot exists, but the supplied `file://` mockup cannot be opened by browser control.
  - Impact: exact spacing, typography, and crop parity cannot be certified.
  - Fix: provide/export the source mockup as a PNG, or serve the mockup from an approved HTTP preview URL.

## Required fidelity surfaces

- Fonts and typography: the existing app typography and weights are preserved; direct source comparison is blocked.
- Spacing and layout rhythm: the original support header/tabs remain, with a bordered Forms container aligned to the app content width.
- Colors and visual tokens: only existing app tokens are used for brand, surface, border, success, and text colors.
- Image quality and asset fidelity: no new raster assets are present; icons use the project's existing Lucide dependency.
- Copy and content: app-side copy consistently says Teams/email, but the remote Forms description currently mentions Slack.

## Primary interactions tested

- FAQ → 문의하기 tab switching
- Organization-only Microsoft Forms iframe loading
- Presence of all required questions and optional file upload
- 문의하기 → 처리현황 tab switching
- New-window fallback link target
- Processing-status guidance and new-inquiry action
- Console checked; the only application error came from the unrelated exchange-rate API while the backend was unavailable locally

## Comparison history

- Initial implementation: replaced PostgreSQL ticket submission/status calls with the Microsoft Forms embed and temporary Teams/email status guidance.
- Browser pass: embed and primary tab interactions worked. Live Forms copy mismatch was found.
- Source comparison: blocked by local-file browser security policy; no workaround attempted.

final result: blocked

# Analysis Period · CMS Date Picker Design QA

- Source visual truth: `C:\Users\USER\AppData\Local\Temp\codex-clipboard-8aaa3ac9-310a-49b0-82bb-25ec8501a421.png` (current analysis condition screen) and `C:\Users\USER\AppData\Local\Temp\codex-clipboard-3ee74ddd-382f-4010-838f-f83ced810202.png` (CMS date picker open state)
- Source pixels: 692 x 512 and 278 x 279; density normalization was not required.
- Implementation route: `http://127.0.0.1:3000/insight/input`
- Implementation screenshot: unavailable; the protected route redirected to `/login` in both the in-app browser and Chrome preview session.
- State: analysis input screen with a date picker opened from 분석 시작일 or 분석 종료일.

## Full-view comparison evidence

- Both supplied source images were opened and inspected at original resolution.
- The implementation route rendered the login screen because no authenticated preview session was available, so a same-viewport source-to-implementation comparison could not be captured.

## Focused region comparison evidence

- Source focus: yellow CMS-style date trigger, orange month header, weekday row, gray day cells, yellow selected day, and month navigation.
- Implementation focus: code uses the same interaction structure and visual tokens, but the rendered calendar state remains blocked pending authentication.

## Findings

- [P0] Authenticated implementation state unavailable for visual QA.
  - Location: `/insight/input`, `InputDateBoxV2`.
  - Evidence: browser navigation redirected to the login screen instead of the analysis condition card.
  - Impact: exact rendered spacing, clipping, and interaction state cannot be certified from a browser screenshot.
  - Fix: sign in to the local application, open `/insight/input`, capture the calendar-open state at the intended desktop and mobile viewports, and rerun this comparison.

## Required fidelity surfaces

- Fonts and typography: existing Pretendard app typography is preserved; rendered comparison is blocked.
- Spacing and layout rhythm: CMS-inspired 202 px calendar width, 30 px orange header, 25 px day cells, and overflow-visible analysis card are implemented; rendered comparison is blocked.
- Colors and visual tokens: CMS-like yellow input, orange header, gray cells, and yellow selected date are defined as app CSS tokens; rendered comparison is blocked.
- Image quality and asset fidelity: no raster assets are required; calendar and navigation icons use the existing Lucide dependency.
- Copy and content: existing Korean labels and date values are preserved; weekday/month labels follow the supplied CMS visual (`Su`–`Sa`, English month name).

## Primary interactions tested

- TypeScript typecheck, design-token audit, targeted ESLint, full frontend test suite, and production build passed.
- Source image inspection passed.
- Browser route navigation reached `/login`; calendar open/select/month navigation could not be exercised without authentication.
- Console/error verification for the authenticated screen is pending.

## Comparison history

- Pass 1: implemented a CMS-style custom date picker with month navigation, selected-day emphasis, min/max range enforcement, outside-click/Escape dismissal, and existing analysis-state callbacks.
- Pass 2: lint and token audit fixes replaced raw picker colors with global design tokens; production build and tests passed.
- Post-fix visual evidence: blocked by authentication redirect.

final result: blocked

# Order Formula Drawer Design QA

## Comparison Target

- Source visual truth: `C:\Users\USER\.codex\generated_images\019fb052-3d01-7fd0-ac44-a3fc9819a1d0\call_HhfrxRMoCLZXeScpAl6OtRon.png`
- Content source of truth: `C:\Users\USER\OneDrive - (주)실리콘투\바탕 화면\EU_발주템플릿_발주담당자교과서_v2_최종검증판.docx` (pages 4, 13, 17, and 26)
- Source pixels: 1488 x 1058
- Intended CSS viewport: 1440 x 1024 at device scale factor 1
- Implementation route: `http://127.0.0.1:3000/order-analysis/new-order-logic`
- Implementation screenshot: unavailable
- State: settings screen with `발주 산식 보기` drawer open

## Evidence

- The selected source visual was opened and inspected at original resolution.
- The implementation route was opened in Chrome at the intended viewport.
- The protected route redirected to `/login`, so the implemented drawer could not be opened or captured.
- No source-to-implementation composite comparison could be produced.
- Focused region comparison was not possible because the authenticated implementation state was unavailable.

## Findings

- [P0] Authenticated screen unavailable for visual verification
  - Location: `/order-analysis/new-order-logic`
  - Evidence: browser navigation reached the login screen instead of the V2 settings screen.
  - Impact: drawer proportions, typography, spacing, responsive behavior, focus handling, and interaction states cannot be verified from a rendered implementation.
  - Fix: sign in to the local application, reopen the V2 route, capture the drawer-open state at 1440 x 1024, and compare it with the selected source visual.

## Required Fidelity Surfaces

- Fonts and typography: blocked pending an authenticated browser render.
- Spacing and layout rhythm: blocked pending an authenticated browser render.
- Colors and visual tokens: source and code tokens reviewed, but rendered comparison is blocked.
- Image quality and asset fidelity: no raster assets are required; UI icons use the existing icon library.
- Copy and content: implementation copy follows the final-validation textbook, including the textbook's 30/50-day lead times, MOQ rounding, total holdings terminology, and conservative upper quantity; rendered wrapping is not yet verified.

## Comparison History

- Pass 1: blocked before visual comparison because the protected route redirected to login.
- Content revision: formula copy was aligned to the final-validation textbook rather than the current web calculation engine.
- Fixes made: content source and regression checks were updated; authentication is still required to collect implementation visual evidence.
- Post-fix evidence: pending.

## Verification Completed

- TypeScript typecheck: passed.
- Design token audit: passed.
- Targeted UI regression checks: passed.
- ESLint on modified components: passed.
- Full frontend test suite: passed.

final result: blocked
