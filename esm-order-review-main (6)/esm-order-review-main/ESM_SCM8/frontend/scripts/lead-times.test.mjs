import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  buildLeadTimeOverrides,
  chooseTransportForAvailableDays,
  effectiveLeadTimeMethods,
  leadTimeStorageKey,
  leadTimeValuesFromMethods,
  parseLeadTimeReference,
  resolveLeadTime
} from "../lib/lead-times.ts";

const expectedByEntity = {
  HQ: [],
  PL: [
    ["OCEAN", "해운", 70],
    ["TRUCKING", "트럭킹", 30],
    ["RAIL", "철송", 30],
    ["AIR", "항공", 15]
  ],
  UK: [
    ["OCEAN", "해운", 75],
    ["AIR_DIR", "항공(DIR·직항)", 5],
    ["AIR_TS", "항공(T/S·환적)", 12]
  ],
  USA: [
    ["OCEAN", "해운", 30],
    ["AIR", "항공", 5]
  ],
  ME: [
    ["OCEAN", "해운", 50],
    ["AIR", "항공", 6]
  ],
  MX: [
    ["OCEAN", "해운", 40],
    ["AIR", "항공", 16]
  ],
  MY: [
    ["OCEAN", "해운", 21],
    ["AIR", "항공", 6]
  ],
  VN: [
    ["OCEAN", "해운", 20],
    ["AIR", "항공", 6]
  ]
};

const references = Object.fromEntries(
  Object.entries(expectedByEntity).map(([entityCode, methods]) => [
    entityCode,
    parseLeadTimeReference({
      entity_code: entityCode,
      effective_date: "2026-07-23",
      source: "해외법인 리드타임 260723ver.xlsx",
      methods: methods.map(([code, label, leadTimeDays]) => ({
        code,
        label,
        lead_time_days: leadTimeDays
      }))
    })
  ])
);

for (const [entityCode, expectedMethods] of Object.entries(expectedByEntity)) {
  const reference = references[entityCode];
  const values = leadTimeValuesFromMethods(reference.methods);
  assert.deepEqual(
    reference.methods.map((method) => [method.code, method.label, method.lead_time_days]),
    expectedMethods,
    `${entityCode} 운송수단과 기본 일수를 API 응답 그대로 보존해야 합니다.`
  );
  for (const [code, , expectedDays] of expectedMethods) {
    assert.equal(resolveLeadTime(reference.methods, values, code), expectedDays);
  }
  assert.deepEqual(
    buildLeadTimeOverrides(reference.methods, values),
    {},
    `${entityCode} 기본값은 사용자 override로 전송하면 안 됩니다.`
  );
}

const unsupportedCases = [
  ["HQ", "OCEAN"],
  ["USA", "RAIL"],
  ["VN", "TRUCKING"],
  ["MX", "AIR_DIR"],
  ["UK", "AIR"],
  ["UK", "TRUCKING"],
  ["UK", "RAIL"]
];
for (const [entityCode, transportCode] of unsupportedCases) {
  const reference = references[entityCode];
  assert.equal(
    resolveLeadTime(reference.methods, leadTimeValuesFromMethods(reference.methods), transportCode),
    null,
    `${entityCode}/${transportCode}는 다른 운송수단 값으로 대체하면 안 됩니다.`
  );
}

const ukReference = references.UK;
const ukValues = leadTimeValuesFromMethods(ukReference.methods);
const changedUkValues = { ...ukValues, AIR_DIR: "7" };
assert.deepEqual(
  buildLeadTimeOverrides(ukReference.methods, changedUkValues),
  { AIR_DIR: 7 },
  "변경된 운송수단만 override로 전송해야 합니다."
);
assert.throws(
  () => buildLeadTimeOverrides(ukReference.methods, { ...ukValues, AIR_TS: "" }),
  /항공\(T\/S·환적\).*0보다 큰 정수/
);

const ukEffectiveMethods = effectiveLeadTimeMethods(ukReference.methods, ukValues);
assert.equal(chooseTransportForAvailableDays(ukEffectiveMethods, 12)?.label, "항공(T/S·환적)");
assert.equal(chooseTransportForAvailableDays(ukEffectiveMethods, 5)?.label, "항공(DIR·직항)");
assert.equal(chooseTransportForAvailableDays([], 100), null, "지원 운송수단이 없으면 fallback을 만들면 안 됩니다.");
const plReference = references.PL;
const plEffectiveMethods = effectiveLeadTimeMethods(
  plReference.methods,
  leadTimeValuesFromMethods(plReference.methods)
);
assert.equal(
  chooseTransportForAvailableDays(plEffectiveMethods, 30)?.code,
  "RAIL",
  "동일 30일 후보에서는 기존 계산 순서대로 철송을 트럭킹보다 먼저 선택해야 합니다."
);

assert.notEqual(
  leadTimeStorageKey("operator", "PL"),
  leadTimeStorageKey("operator", "USA"),
  "법인별 사용자 입력 저장소는 분리되어야 합니다."
);
assert.notEqual(
  leadTimeStorageKey("operator-a", "PL"),
  leadTimeStorageKey("operator-b", "PL"),
  "계정별 사용자 입력 저장소는 분리되어야 합니다."
);

assert.throws(() => parseLeadTimeReference({
  entity_code: "USA",
  effective_date: "2026-07-23",
  source: "test",
  methods: [{ code: "AIR", label: "항공", lead_time_days: 0 }]
}), /양의 정수/);

const analysisSource = readFileSync(new URL("../lib/api/analysis.ts", import.meta.url), "utf8");
assert.match(analysisSource, /formData\.append\("lead_time_overrides", JSON\.stringify/);
assert.match(analysisSource, /lead_time_overrides:\s*options\.leadTimeOverrides/);
assert.doesNotMatch(analysisSource, /formData\.append\("lead_time_(?:air|sea|rail|truck)"/);

const integratedTableSource = readFileSync(
  new URL("../app/integrated-order-review/IntegratedOrderTable.tsx", import.meta.url),
  "utf8"
);
assert.doesNotMatch(integratedTableSource, /air\s*\|\|\s*7/);
assert.match(integratedTableSource, /key=\{selectedEntity\}/, "법인 변경 시 통합 발주 상태를 remount해야 합니다.");

const seasonApiSource = readFileSync(new URL("../lib/api/season.ts", import.meta.url), "utf8");
assert.match(seasonApiSource, /const requestEntityCode = getActiveEntityCode\(\)/);
assert.match(seasonApiSource, /getActiveEntityCode\(\) !== requestEntityCode/);
assert.doesNotMatch(seasonApiSource, /lead_time_(?:overrides|air|sea|rail|truck)/);

const authSource = readFileSync(new URL("../lib/auth.ts", import.meta.url), "utf8");
assert.match(
  authSource,
  /removeItemsWithPrefix\("local",\s*`\$\{LEAD_TIME_STORAGE_PREFIX\}:`\)/,
  "로그아웃·계정 전환 시 저장된 법인별 사용자 리드타임을 정리해야 합니다."
);

console.log("lead-times frontend tests passed");
