"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatNumber } from "@/lib/utils";
import { isAmountField, sanitizeAmountData } from "@/lib/amount-permissions";
import { useUserPermissions } from "@/lib/use-user-permissions";

type SeasonTrendTableProps = {
  title: string;
  rows: Array<Record<string, unknown>>;
  columns?: string[];
  emptyText?: string;
};

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? formatNumber(value) : formatNumber(value, 1);
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  return String(value);
}

function displayColumn(column: string) {
  return column === "판매금액" ? "환산금액" : column;
}

export function SeasonTrendTable({
  title,
  rows,
  columns,
  emptyText = "표시할 데이터가 없습니다."
}: SeasonTrendTableProps) {
  const { canViewAmountData } = useUserPermissions();
  const visibleRows = canViewAmountData ? rows : sanitizeAmountData(rows);
  const visibleColumns = (columns ?? Object.keys(visibleRows[0] ?? {}).slice(0, 12))
    .filter((column) => canViewAmountData || !isAmountField(column));

  return (
    <Card className="border-slate-200">
      <CardHeader className="pb-3">
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-hidden rounded-lg border border-line">
          <div className="max-h-[520px] overflow-auto">
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-slate-50">
                <TableRow>
                  {visibleColumns.map((column) => (
                    <TableHead key={column}>{displayColumn(column)}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleRows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={Math.max(visibleColumns.length, 1)} className="py-10 text-center text-slate-500">
                      {emptyText}
                    </TableCell>
                  </TableRow>
                ) : (
                  visibleRows.map((row, index) => (
                    <TableRow key={index}>
                      {visibleColumns.map((column) => (
                        <TableCell key={column} className="max-w-[320px] truncate" title={displayValue(row[column])}>
                          {displayValue(row[column])}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
