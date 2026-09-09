import { apiFetch, ApiRequestError, FASTAPI_BASE_URL, parseApiError } from "./client";

export type CorporateInventoryWarehouse = {
  warehouse_code: string;
  warehouse_name: string;
  ending_inventory_krw: string;
  ending_inventory_current_krw: string;
  ending_inventory_local: string | null;
  exchange_rate_krw: string | null;
  exchange_rate_date: string | null;
};

export type CorporateInventoryCompany = {
  company_code: string;
  company_name: string;
  country_name: string;
  base_currency: string;
  warehouse_count: number;
  ending_inventory_krw: string;
  ending_inventory_current_krw: string;
  ending_inventory_local: string | null;
  inventory_status: "available" | "no_inventory";
  valuation_basis: "cms_eqty_cost" | "current_exchange_rate" | "no_inventory";
  exchange_rate_unit: string | null;
  exchange_rate_krw: string | null;
  exchange_rate_date: string | null;
  warehouses: CorporateInventoryWarehouse[];
};

export type CorporateInventoryHoldings =
  | {
      status: "ready";
      as_of: string;
      total_krw: string;
      total_current_krw: string;
      difference_krw: string;
      active_company_count: number;
      companies_with_inventory_count: number;
      companies: CorporateInventoryCompany[];
    }
  | {
      status: "failed";
      as_of: string;
      message: string;
    };

export type CorporateInventoryTransitCurrency = {
  currency_code: string;
  original_amount: string;
  quantity: string;
  converted_krw: string;
  exchange_rate_basis: "invoice_contract" | "krw";
  exchange_rates: Array<{
    rate: string;
    rate_date: string;
  }>;
};

export type CorporateInventoryTransitMode = {
  transport_mode_code: string;
  transport_mode_name: string;
  transport_mode_sources: string[];
  quantity: string;
  total_krw: string;
  currencies: CorporateInventoryTransitCurrency[];
};

export type CorporateInventoryTransitDestination = {
  destination_code: string;
  destination_name: string;
  quantity: string;
  total_krw: string;
  currencies: CorporateInventoryTransitCurrency[];
  transport_modes: CorporateInventoryTransitMode[];
};

export type CorporateInventoryInTransit =
  | {
      status: "ready";
      as_of: string;
      total_krw: string;
      destinations: CorporateInventoryTransitDestination[];
    }
  | {
      status: "failed";
      as_of: string;
      message: string;
    };

export type CorporateInventoryTotal =
  | {
      status: "ready";
      total_krw: string;
    }
  | {
      status: "unavailable";
      message: string;
    };

export type CorporateInventoryResponse = {
  as_of: string;
  generated_at: string;
  holdings: CorporateInventoryHoldings;
  in_transit: CorporateInventoryInTransit;
  total_inventory: CorporateInventoryTotal;
};

export async function getCorporateInventory(): Promise<CorporateInventoryResponse> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/corporate-inventory`);
  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }
  return response.json() as Promise<CorporateInventoryResponse>;
}
