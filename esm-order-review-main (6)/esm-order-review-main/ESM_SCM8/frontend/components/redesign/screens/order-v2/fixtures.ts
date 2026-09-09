import type {
  NewOrderLogicDataset,
  NewOrderLogicPolicySettings,
  NewOrderSimulationResult
} from "./types";

export const sampleNewOrderLogicSettings: NewOrderLogicPolicySettings = {
  policyMode: "SHORTAGE",
  demandWeeks: 13,
  gradeCutoffPct: 80,
  minWeeksWithSales: 7,
  bulkSalesMultiple: 3,
  coverWeeks: 4,
  reviewBufferDays: 28,
  safetyStockFloorWeeks: 2,
  safetyStockCapWeeks: 13,
  zMatrix: {
    shortageMajor: 1.68,
    shortageMinor: 1.28,
    cashMajor: 1.28,
    cashMinor: 1.08
  },
  policyTransports: {
    CASH: "RAIL",
    SHORTAGE: "SEA"
  },
  leadTimes: [
    {
      code: "AIR",
      label: "항공",
      meanDays: 16.4,
      sigmaWeeks: 0.68
    },
    {
      code: "RAIL",
      label: "철송",
      meanDays: 36.6,
      sigmaWeeks: 1.15
    },
    {
      code: "SEA",
      label: "해운",
      meanDays: 72.9,
      sigmaWeeks: 2.18
    }
  ]
};

export const sampleNewOrderLogicData: NewOrderLogicDataset = {
  meta: {
    jobId: "new-order-20260727-102430-a81c",
    logicVersion: "v2.0.0-beta.2",
    currencyCode: "EUR",
    appliedMode: "SHORTAGE",
    sourceAsOf: "2026-07-27T09:00:00+09:00",
    calculatedAt: "2026-07-27T10:24:30+09:00",
    demandPeriod: {
      from: "2026-04-27",
      to: "2026-07-26",
      completedWeeks: 13
    },
    periodUnit: "week",
    entityCode: "PL",
    sourceSnapshotId: "cms-pl-20260727-0900"
  },
  rows: [
    {
      id: "ANU-SUN-050",
      productCode: "ANU-SUN-050",
      productName: "아누아 어성초 톤업 선크림 SPF50+",
      brand: "아누아",
      dataStatus: "정상",
      grade: "주력",
      isCalculable: true,
      weeklyMean: 2450,
      cv: 0.42,
      inboundQty: 16800,
      euAvailableQty: 12400,
      inTransitQty: 5200,
      localAvailableQty: 900,
      inventoryPosition: 35300,
      inventoryPositionWithoutIncoming: 18500,
      nextEta: "2026-08-08",
      nextEtaStatus: "원천 ETA",
      stockoutWeeks: 14.4,
      confirmedQty: 17600,
      memo: "현지 프로모션 물량 100개 추가",
      unitPriceEur: 31.5,
      modes: {
        SHORTAGE: {
          zApplied: 1.68,
          leadTimeDays: 72.9,
          leadTimeSigmaWeeks: 2.18,
          safetyStock: 14950,
          reorderPoint: 42900,
          targetStock: 47800,
          suggestedQty: 17500,
          upperSuggestedQty: 34300,
          signal: "발주",
          referenceAmountEur: 551250
        },
        CASH: {
          zApplied: 1.28,
          leadTimeDays: 36.6,
          leadTimeSigmaWeeks: 1.15,
          safetyStock: 9800,
          reorderPoint: 25050,
          targetStock: 29950,
          suggestedQty: 0,
          upperSuggestedQty: 11450,
          signal: "충분",
          referenceAmountEur: 0
        }
      },
      comparisonReasonsByMode: { CASH: ["해운 보호기간 적용", "주력 Z 1.68 적용"], SHORTAGE: ["해운 보호기간 적용", "주력 Z 1.68 적용"] }
    },
    {
      id: "TOR-DIV-030",
      productCode: "TOR-DIV-030",
      productName: "토리든 다이브인 저분자 히알루론산 세럼",
      brand: "토리든",
      dataStatus: "대량포함",
      grade: "주력",
      isCalculable: true,
      weeklyMean: 1980,
      cv: 1.18,
      inboundQty: 4100,
      euAvailableQty: 3200,
      inTransitQty: 1800,
      localAvailableQty: 450,
      inventoryPosition: 9550,
      inventoryPositionWithoutIncoming: 5450,
      nextEta: "2026-08-19",
      nextEtaStatus: "출고일 추정 ETA",
      stockoutWeeks: 4.8,
      confirmedQty: 26160,
      memo: "대량판매 주차 확인 필요",
      unitPriceEur: 9.8,
      modes: {
        SHORTAGE: {
          zApplied: 1.68,
          leadTimeDays: 72.9,
          leadTimeSigmaWeeks: 2.18,
          safetyStock: 12140,
          reorderPoint: 34730,
          targetStock: 38690,
          suggestedQty: 26160,
          upperSuggestedQty: 30260,
          signal: "확인후발주",
          referenceAmountEur: 256368
        },
        CASH: {
          zApplied: 1.28,
          leadTimeDays: 36.6,
          leadTimeSigmaWeeks: 1.15,
          safetyStock: 7220,
          reorderPoint: 19550,
          targetStock: 23510,
          suggestedQty: 13980,
          upperSuggestedQty: 18080,
          signal: "확인후발주",
          referenceAmountEur: 137004
        }
      },
      comparisonReasonsByMode: { CASH: ["수요 CV 1.18", "대량포함 확인 필요"], SHORTAGE: ["수요 CV 1.18", "대량포함 확인 필요"] }
    },
    {
      id: "JSB-RIC-100",
      productCode: "JSB-RIC-100",
      productName: "조선미녀 맑은쌀 선크림",
      brand: "조선미녀",
      dataStatus: "정상",
      grade: "주력",
      isCalculable: true,
      weeklyMean: 1420,
      cv: 0.36,
      inboundQty: 11200,
      euAvailableQty: 8600,
      inTransitQty: 2600,
      localAvailableQty: 380,
      inventoryPosition: 22780,
      inventoryPositionWithoutIncoming: 11580,
      nextEta: "2026-08-03",
      nextEtaStatus: "원천 ETA",
      stockoutWeeks: 16,
      confirmedQty: 3600,
      memo: "신규 입점 초도 물량 300개 추가",
      unitPriceEur: 17.9,
      modes: {
        SHORTAGE: {
          zApplied: 1.68,
          leadTimeDays: 72.9,
          leadTimeSigmaWeeks: 2.18,
          safetyStock: 6940,
          reorderPoint: 23160,
          targetStock: 26000,
          suggestedQty: 3300,
          upperSuggestedQty: 14500,
          signal: "발주",
          referenceAmountEur: 59070
        },
        CASH: {
          zApplied: 1.28,
          leadTimeDays: 36.6,
          leadTimeSigmaWeeks: 1.15,
          safetyStock: 4210,
          reorderPoint: 13050,
          targetStock: 15890,
          suggestedQty: 0,
          upperSuggestedQty: 4310,
          signal: "충분",
          referenceAmountEur: 0
        }
      },
      comparisonReasonsByMode: { CASH: ["쇼티지 방어 시나리오에서만 발주점 미달"], SHORTAGE: ["쇼티지 방어 시나리오에서만 발주점 미달"] }
    },
    {
      id: "MDH-COL-021",
      productCode: "MDH-COL-021",
      productName: "메디힐 콜라겐 흔적 앰플 마스크",
      brand: "메디힐",
      dataStatus: "확인(간헐)",
      grade: "일반",
      isCalculable: true,
      weeklyMean: 640,
      cv: 1.44,
      inboundQty: 2400,
      euAvailableQty: 2100,
      inTransitQty: 0,
      localAvailableQty: 180,
      inventoryPosition: 4680,
      inventoryPositionWithoutIncoming: 2280,
      nextEta: null,
      nextEtaStatus: "입고 예정 없음",
      stockoutWeeks: 7.3,
      confirmedQty: 6540,
      memo: "담당자 검토 후 보수적으로 조정",
      unitPriceEur: 5.3,
      modes: {
        SHORTAGE: {
          zApplied: 1.28,
          leadTimeDays: 72.9,
          leadTimeSigmaWeeks: 2.18,
          safetyStock: 4160,
          reorderPoint: 11470,
          targetStock: 12750,
          suggestedQty: 8080,
          upperSuggestedQty: 10480,
          signal: "확인후발주",
          referenceAmountEur: 42824
        },
        CASH: {
          zApplied: 1.08,
          leadTimeDays: 36.6,
          leadTimeSigmaWeeks: 1.15,
          safetyStock: 2490,
          reorderPoint: 6480,
          targetStock: 7760,
          suggestedQty: 3080,
          upperSuggestedQty: 5480,
          signal: "확인후발주",
          referenceAmountEur: 16324
        }
      },
      comparisonReasonsByMode: { CASH: ["13주 중 판매 주차 7주 미만", "고갈주수 참고값 확인"], SHORTAGE: ["13주 중 판매 주차 7주 미만", "고갈주수 참고값 확인"] }
    },
    {
      id: "CRX-SNL-096",
      productCode: "CRX-SNL-096",
      productName: "코스알엑스 스네일 96 뮤신 에센스",
      brand: "코스알엑스",
      dataStatus: "판매없음",
      grade: "일반",
      isCalculable: true,
      weeklyMean: 0,
      cv: null,
      inboundQty: 12900,
      euAvailableQty: 9800,
      inTransitQty: 0,
      localAvailableQty: 0,
      inventoryPosition: 22700,
      inventoryPositionWithoutIncoming: 9800,
      nextEta: "2026-08-01",
      nextEtaStatus: "원천 ETA",
      stockoutWeeks: null,
      confirmedQty: 0,
      memo: "",
      unitPriceEur: 9.2,
      modes: {
        SHORTAGE: {
          zApplied: 1.28,
          leadTimeDays: 72.9,
          leadTimeSigmaWeeks: 2.18,
          safetyStock: 0,
          reorderPoint: 0,
          targetStock: 0,
          suggestedQty: 0,
          upperSuggestedQty: 0,
          signal: "-",
          referenceAmountEur: 0
        },
        CASH: {
          zApplied: 1.08,
          leadTimeDays: 36.6,
          leadTimeSigmaWeeks: 1.15,
          safetyStock: 0,
          reorderPoint: 0,
          targetStock: 0,
          suggestedQty: 0,
          upperSuggestedQty: 0,
          signal: "-",
          referenceAmountEur: 0
        }
      },
      comparisonReasonsByMode: { CASH: ["최근 13주 판매없음"], SHORTAGE: ["최근 13주 판매없음"] }
    },
    {
      id: "ANU-NIA-030",
      productCode: "ANU-NIA-030",
      productName: "아누아 나이아신아마이드 세럼",
      brand: "아누아",
      dataStatus: "이력부족",
      grade: null,
      isCalculable: false,
      decisionLockReason: "최근 13개 완료 주 판매이력이 부족합니다.",
      weeklyMean: null,
      cv: null,
      inboundQty: 1350,
      euAvailableQty: 1200,
      inTransitQty: 0,
      localAvailableQty: 120,
      inventoryPosition: 2670,
      inventoryPositionWithoutIncoming: 1320,
      nextEta: null,
      nextEtaStatus: "입고 예정 없음",
      stockoutWeeks: null,
      confirmedQty: null,
      memo: "신규 SKU 별도 검토",
      unitPriceEur: 5.1,
      modes: {
        SHORTAGE: {
          zApplied: null,
          leadTimeDays: null,
          leadTimeSigmaWeeks: null,
          safetyStock: null,
          reorderPoint: null,
          targetStock: null,
          suggestedQty: null,
          upperSuggestedQty: null,
          signal: "-",
          referenceAmountEur: null
        },
        CASH: {
          zApplied: null,
          leadTimeDays: null,
          leadTimeSigmaWeeks: null,
          safetyStock: null,
          reorderPoint: null,
          targetStock: null,
          suggestedQty: null,
          upperSuggestedQty: null,
          signal: "-",
          referenceAmountEur: null
        }
      },
      comparisonReasonsByMode: { CASH: ["13주 이력 미충족", "신규 SKU 프로세스 필요"], SHORTAGE: ["13주 이력 미충족", "신규 SKU 프로세스 필요"] }
    }
  ]
};

export const sampleNewOrderSimulation: NewOrderSimulationResult = {
  jobId: sampleNewOrderLogicData.meta.jobId,
  simulatedAt: "2026-07-27T10:31:00+09:00",
  baseline: {
    mode: "SHORTAGE",
    orderSkuCount: 2,
    confirmSkuCount: 2,
    totalSuggestedQty: 55040,
    totalReferenceAmountEur: 909512
  },
  candidate: {
    mode: "CASH",
    orderSkuCount: 0,
    confirmSkuCount: 2,
    totalSuggestedQty: 17060,
    totalReferenceAmountEur: 153328
  },
  changedSkuCount: 4
};
