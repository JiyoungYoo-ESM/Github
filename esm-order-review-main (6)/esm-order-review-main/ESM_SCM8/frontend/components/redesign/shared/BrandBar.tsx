"use client";

export function SkuNameWithCode({ name, sku }: { name: string; sku: string }) {
  return (
    <div className="flex min-w-0 w-full items-center gap-2">
      <p className="min-w-0 truncate text-[13px] font-black text-ink" title={name}>{name}</p>
      <span
        className="max-w-[120px] shrink-0 truncate rounded-[5px] bg-row px-1.5 py-0.5 text-[10.5px] font-black text-muted2"
        title={`상품코드 ${sku}`}
      >
        {sku}
      </span>
    </div>
  );
}



export function BrandBar({ name, value, width, detail, code }: { name: string; value: string; width: string; detail?: string; code?: string }) {
  return (
    <div className="min-w-0 w-full">
      <div className="mb-[6px] flex min-w-0 w-full items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {code ? <SkuNameWithCode name={name} sku={code} /> : <span className="block truncate text-[13px] font-black text-ink" title={name}>{name}</span>}
        </div>
        <span className="max-w-[58%] shrink-0 whitespace-normal break-keep text-right text-[12px] font-black leading-[1.35] text-ink" title={value}>{value}</span>
      </div>
      {detail ? <p className="mb-[6px] text-[11px] font-semibold leading-[1.45] text-muted2">{detail}</p> : null}
      <div className="h-[5px] overflow-hidden rounded-full bg-row">
        <div className="h-full rounded-full bg-brand" style={{ width }} />
      </div>
    </div>
  );
}


