export type RegionGroup =
  | "북유럽"
  | "서유럽"
  | "남유럽"
  | "중동유럽"
  | "동아시아"
  | "동남아시아"
  | "남아시아"
  | "중앙아시아"
  | "중동"
  | "북미"
  | "중미·카리브"
  | "남미"
  | "북아프리카"
  | "서아프리카"
  | "동아프리카"
  | "중앙아프리카"
  | "남아프리카"
  | "오세아니아"
  | "기타";
export type RegionStatus = "confirmed" | "needs_review";
export type RegionFilter = "전체" | RegionGroup;

export type CountryRegionInfo = {
  region: RegionGroup;
  status: RegionStatus;
  note?: string;
};

export type RegionVisualMeta = {
  label: RegionGroup;
  lat: number;
  lng: number;
  color: string;
};

export const REGION_FILTERS: RegionFilter[] = [
  "전체",
  "북유럽",
  "서유럽",
  "남유럽",
  "중동유럽",
  "동아시아",
  "동남아시아",
  "남아시아",
  "중앙아시아",
  "중동",
  "북미",
  "중미·카리브",
  "남미",
  "북아프리카",
  "서아프리카",
  "동아프리카",
  "중앙아프리카",
  "남아프리카",
  "오세아니아",
  "기타"
];

export const REGION_VISUAL_META: RegionVisualMeta[] = [
  { label: "북유럽", lat: 59, lng: 15, color: "#38BDF8" },
  { label: "서유럽", lat: 49, lng: 6, color: "#2563EB" },
  { label: "남유럽", lat: 41, lng: 13, color: "#7C3AED" },
  { label: "중동유럽", lat: 50, lng: 23, color: "#E6002D" },
  { label: "동아시아", lat: 35, lng: 116, color: "#F97316" },
  { label: "동남아시아", lat: 9, lng: 105, color: "#F59E0B" },
  { label: "남아시아", lat: 22, lng: 78, color: "#84CC16" },
  { label: "중앙아시아", lat: 45, lng: 67, color: "#22C55E" },
  { label: "중동", lat: 28, lng: 45, color: "#14B8A6" },
  { label: "북미", lat: 43, lng: -100, color: "#0EA5E9" },
  { label: "중미·카리브", lat: 18, lng: -77, color: "#06B6D4" },
  { label: "남미", lat: -15, lng: -60, color: "#10B981" },
  { label: "북아프리카", lat: 27, lng: 12, color: "#D97706" },
  { label: "서아프리카", lat: 10, lng: -2, color: "#CA8A04" },
  { label: "동아프리카", lat: -3, lng: 38, color: "#A16207" },
  { label: "중앙아프리카", lat: 0, lng: 20, color: "#92400E" },
  { label: "남아프리카", lat: -25, lng: 25, color: "#78350F" },
  { label: "오세아니아", lat: -25, lng: 135, color: "#8B5CF6" },
  { label: "기타", lat: 0, lng: 0, color: "#64748B" }
];

const REGION_COUNTRIES: Record<Exclude<RegionGroup, "기타">, string[]> = {
  북유럽: [
    "denmark",
    "estonia",
    "finland",
    "greenland",
    "iceland",
    "ireland",
    "latvia",
    "lithuania",
    "norway",
    "sweden",
    "united kingdom",
    "uk",
    "england",
    "scotland",
    "wales"
  ],
  서유럽: [
    "austria",
    "belgium",
    "france",
    "germany",
    "liechtenstein",
    "luxembourg",
    "monaco",
    "netherlands",
    "switzerland"
  ],
  남유럽: [
    "andorra",
    "cyprus",
    "gibraltar",
    "greece",
    "italy",
    "malta",
    "portugal",
    "san marino",
    "spain",
    "holy see",
    "vatican city"
  ],
  중동유럽: [
    "albania",
    "armenia",
    "azerbaijan",
    "belarus",
    "bosnia and herzegovina",
    "bulgaria",
    "croatia",
    "czech republic",
    "czechia",
    "georgia",
    "hungary",
    "kosovo",
    "moldova",
    "moldova republic of",
    "montenegro",
    "macedonia former yugoslav republic of",
    "north macedonia",
    "poland",
    "romania",
    "russia",
    "russian federation",
    "serbia",
    "slovakia",
    "slovenia",
    "ukraine"
  ],
  동아시아: [
    "china",
    "hong kong",
    "japan",
    "korea",
    "korea republic of",
    "south korea",
    "macau",
    "macao",
    "mongolia",
    "taiwan",
    "taiwan province of china"
  ],
  동남아시아: [
    "brunei",
    "cambodia",
    "indonesia",
    "laos",
    "malaysia",
    "myanmar",
    "philippines",
    "singapore",
    "thailand",
    "timor leste",
    "vietnam",
    "viet nam"
  ],
  남아시아: [
    "afghanistan",
    "bangladesh",
    "bhutan",
    "india",
    "maldives",
    "nepal",
    "pakistan",
    "sri lanka"
  ],
  중앙아시아: [
    "kazakhstan",
    "kyrgyzstan",
    "tajikistan",
    "turkmenistan",
    "uzbekistan"
  ],
  중동: [
    "bahrain",
    "iran",
    "iran islamic republic of",
    "iraq",
    "israel",
    "jordan",
    "kuwait",
    "lebanon",
    "oman",
    "palestine",
    "qatar",
    "saudi arabia",
    "syrian arab republic",
    "syria",
    "turkey",
    "turkiye",
    "united arab emirates",
    "uae",
    "yemen"
  ],
  북미: [
    "bermuda",
    "canada",
    "saint pierre and miquelon",
    "united states",
    "united states of america",
    "usa"
  ],
  "중미·카리브": [
    "anguilla",
    "antigua and barbuda",
    "aruba",
    "bahamas",
    "barbados",
    "belize",
    "bonaire",
    "british virgin islands",
    "cayman islands",
    "costa rica",
    "curacao",
    "cuba",
    "dominica",
    "dominican republic",
    "el salvador",
    "grenada",
    "guatemala",
    "haiti",
    "honduras",
    "jamaica",
    "martinique",
    "mexico",
    "nicaragua",
    "panama",
    "puerto rico",
    "saint kitts and nevis",
    "saint lucia",
    "saint martin",
    "saint vincent and the grenadines",
    "sint maarten",
    "trinidad and tobago",
    "turks and caicos islands",
    "virgin islands"
  ],
  남미: [
    "argentina",
    "bolivia",
    "bolivia plurinational state of",
    "brazil",
    "chile",
    "colombia",
    "ecuador",
    "falkland islands",
    "french guiana",
    "guyana",
    "paraguay",
    "peru",
    "suriname",
    "uruguay",
    "venezuela",
    "venezuela bolivarian republic of"
  ],
  북아프리카: [
    "algeria",
    "egypt",
    "libya",
    "morocco",
    "sudan",
    "tunisia",
    "western sahara"
  ],
  서아프리카: [
    "benin",
    "burkina faso",
    "cape verde",
    "cote d ivoire",
    "ivory coast",
    "gambia",
    "ghana",
    "guinea",
    "guinea bissau",
    "liberia",
    "mali",
    "mauritania",
    "niger",
    "nigeria",
    "senegal",
    "sierra leone",
    "togo"
  ],
  동아프리카: [
    "burundi",
    "comoros",
    "djibouti",
    "eritrea",
    "ethiopia",
    "kenya",
    "madagascar",
    "malawi",
    "mauritius",
    "mayotte",
    "mozambique",
    "reunion",
    "rwanda",
    "seychelles",
    "somalia",
    "south sudan",
    "tanzania",
    "tanzania united republic of",
    "uganda",
    "zambia",
    "zimbabwe"
  ],
  중앙아프리카: [
    "angola",
    "cameroon",
    "central african republic",
    "chad",
    "congo",
    "congo democratic republic of the",
    "democratic republic of the congo",
    "equatorial guinea",
    "gabon",
    "sao tome and principe"
  ],
  남아프리카: [
    "botswana",
    "eswatini",
    "lesotho",
    "namibia",
    "south africa",
    "swaziland"
  ],
  오세아니아: [
    "american samoa",
    "australia",
    "cook islands",
    "fiji",
    "french polynesia",
    "guam",
    "kiribati",
    "marshall islands",
    "micronesia",
    "nauru",
    "new caledonia",
    "new zealand",
    "niue",
    "northern mariana islands",
    "palau",
    "papua new guinea",
    "samoa",
    "solomon islands",
    "tonga",
    "tuvalu",
    "vanuatu"
  ]
};

const NEEDS_REVIEW = [
  "european union",
  "eu",
  "union",
  "union europeenne",
  "european community"
];

const KOREAN_ALIAS: Record<string, string> = {
  독일: "germany",
  프랑스: "france",
  이탈리아: "italy",
  스페인: "spain",
  포르투갈: "portugal",
  네덜란드: "netherlands",
  벨기에: "belgium",
  룩셈부르크: "luxembourg",
  오스트리아: "austria",
  스위스: "switzerland",
  아일랜드: "ireland",
  영국: "united kingdom",
  덴마크: "denmark",
  스웨덴: "sweden",
  노르웨이: "norway",
  핀란드: "finland",
  아이슬란드: "iceland",
  그리스: "greece",
  몰타: "malta",
  키프로스: "cyprus",
  폴란드: "poland",
  체코: "czechia",
  슬로바키아: "slovakia",
  헝가리: "hungary",
  슬로베니아: "slovenia",
  크로아티아: "croatia",
  루마니아: "romania",
  불가리아: "bulgaria",
  세르비아: "serbia",
  우크라이나: "ukraine",
  러시아: "russia",
  리투아니아: "lithuania",
  라트비아: "latvia",
  에스토니아: "estonia",
  미국: "united states",
  캐나다: "canada",
  멕시코: "mexico",
  브라질: "brazil",
  아르헨티나: "argentina",
  칠레: "chile",
  콜롬비아: "colombia",
  페루: "peru",
  인도네시아: "indonesia",
  캄보디아: "cambodia",
  한국: "korea republic of",
  대한민국: "korea republic of",
  일본: "japan",
  중국: "china",
  태국: "thailand",
  베트남: "vietnam",
  대만: "taiwan",
  홍콩: "hong kong",
  싱가포르: "singapore",
  말레이시아: "malaysia",
  필리핀: "philippines",
  인도: "india",
  파키스탄: "pakistan",
  호주: "australia",
  뉴질랜드: "new zealand",
  이스라엘: "israel",
  팔레스타인: "palestine",
  유니온: "union",
  유럽연합: "european union",
  터키: "turkey",
  아랍에미리트: "united arab emirates",
  사우디아라비아: "saudi arabia",
  이집트: "egypt",
  모로코: "morocco",
  남아프리카공화국: "south africa"
};

const regionRules = new Map<string, CountryRegionInfo>();

Object.entries(REGION_COUNTRIES).forEach(([region, countries]) => {
  countries.forEach((country) => {
    regionRules.set(country, { region: region as RegionGroup, status: "confirmed" });
  });
});

NEEDS_REVIEW.forEach((country) => {
  regionRules.set(country, { region: "기타", status: "needs_review", note: "유니온 계열은 내부 권역 기준 확인이 필요합니다." });
});

export function normalizeCountryName(country: string) {
  return country
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\([^)]*\)/g, " ")
    .replace(/[._,/\\'’‘-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function resolveAlias(normalized: string) {
  const koreanAliasKey = Object.keys(KOREAN_ALIAS).find((key) => normalized.includes(key));
  return KOREAN_ALIAS[normalized] ?? (koreanAliasKey ? KOREAN_ALIAS[koreanAliasKey] : normalized);
}

export function getCountryRegion(country: string): CountryRegionInfo {
  const normalized = normalizeCountryName(country);
  const alias = resolveAlias(normalized);

  if (!alias || alias === "미상" || alias === "unknown" || alias === "n/a") {
    return { region: "기타", status: "needs_review", note: "국가명이 비어 있거나 확인할 수 없습니다." };
  }

  if (regionRules.has(alias)) {
    return regionRules.get(alias)!;
  }

  const fuzzyKey = Array.from(regionRules.keys()).find((key) => alias ? alias.includes(key) || key.includes(alias) : false);
  if (fuzzyKey) {
    return regionRules.get(fuzzyKey)!;
  }

  return { region: "기타", status: "confirmed", note: "기준표에 없는 국가/지역입니다. 필요하면 세부 권역 기준표에 추가할 수 있습니다." };
}

export function needsRegionReview(info: CountryRegionInfo) {
  return info.status === "needs_review";
}
