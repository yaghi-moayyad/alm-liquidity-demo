import type {
  Entity,
  Portfolio,
  Input,
  Run,
  Flow,
  BehavioralFlow,
  Validation,
  Session,
  EntitySettings,
  RunContract,
  LiquidityAssumptionSet,
  LiquidityAssumption,
  ProductCatalogueChoice,
  NcrReport,
  NsfrReport,
  RegulatoryPoint,
  RegulatoryDrivers,
  RegulatoryMovement,
  RegulatoryDriverDetail,
  RegulatoryCalculation,
  RegulatoryContribution,
  RegulatoryMapping,
  StressConfig,
  LcrStressResults,
  StressRun,
} from "./types";
export function csrf() {
  return decodeURIComponent(
    document.cookie
      .split("; ")
      .find((x) => x.startsWith("csrftoken="))
      ?.split("=")[1] || "",
  );
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.method && options.method !== "GET") {
    headers.set("Content-Type", "application/json");
    headers.set("X-CSRFToken", csrf());
  }
  const response = await fetch("/api/v1" + path, {
    credentials: "same-origin",
    ...options,
    headers,
  });
  const contentType = response.headers.get("content-type") || "";
  const body = await response.text();
  const raw: unknown =
    body && contentType.includes("application/json") ? JSON.parse(body) : {};
  const data = raw as T;
  if (!response.ok) {
    const errorPayload =
      raw && typeof raw === "object"
        ? (raw as { error?: string; details?: Record<string, unknown> })
        : {};
    if (response.status === 401 || response.status === 403) {
      if (String(errorPayload.error).includes("credentials"))
        window.location.href = "/accounts/login/?next=/";
    }
    throw new Error(
      errorPayload.details
        ? Object.entries(errorPayload.details)
            .map(
              ([k, v]) =>
                `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`,
            )
            .join(" · ")
        : errorPayload.error || `Request failed (${response.status})`,
    );
  }
  return data;
}
export const api = {
  session: () => request<Session>("/session"),
  entities: () => request<Entity[]>("/entities"),
  createEntity: (
    data: Pick<
      Entity,
      "name" | "slug" | "country" | "base_currency" | "is_mock"
    >,
  ) =>
    request<Entity>("/entities", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  portfolio: (entity: string) =>
    request<Portfolio>(`/entities/${entity}/portfolio`),
  settings: (entity: string) =>
    request<EntitySettings>(`/entities/${entity}/settings`),
  saveSettings: (
    entity: string,
    data: Pick<EntitySettings, "interest_projection" | "forward_curve">,
  ) =>
    request<EntitySettings>(`/entities/${entity}/settings`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  bucketProfile: (entity: string) =>
    request<{ bucket_days: number[] }>(`/entities/${entity}/bucket-profile`),
  saveBucketProfile: (entity: string, bucketDays: number[]) =>
    request<{ bucket_days: number[] }>(`/entities/${entity}/bucket-profile`, {
      method: "PUT",
      body: JSON.stringify({ bucket_days: bucketDays }),
    }),
  assumptions: (entity: string) =>
    request<LiquidityAssumptionSet>(`/entities/${entity}/assumptions`),
  productCatalogue: (entity: string) =>
    request<ProductCatalogueChoice[]>(`/entities/${entity}/product-catalogue`),
  saveProductTreatment: (
    entity: string,
    id: number,
    cashflowTreatment: ProductCatalogueChoice["cashflow_treatment"],
  ) =>
    request<ProductCatalogueChoice>(
      `/entities/${entity}/product-catalogue/${id}`,
      { method: "PATCH", body: JSON.stringify({ cashflow_treatment: cashflowTreatment }) },
    ),
  regulatoryCalculations: (entity: string) =>
    request<RegulatoryCalculation[]>(`/entities/${entity}/regulatory/calculations`),
  regulatoryMappings: (entity: string) =>
    request<RegulatoryMapping[]>(`/entities/${entity}/regulatory/mappings`),
  regulatoryConfig: (entity: string) =>
    request<Record<string, unknown>>(`/entities/${entity}/regulatory/config`),
  calculateRegulatory: (entity: string) =>
    request<RegulatoryCalculation>(`/entities/${entity}/regulatory/calculations`, {
      method: "POST",
      body: "{}",
    }),
  regulatoryContributions: (
    entity: string,
    calculationId: number,
    metric: "LCR" | "NSFR",
    lineCode: string,
  ) =>
    request<RegulatoryContribution[]>(
      `/entities/${entity}/regulatory/calculations/${calculationId}/contributions?metric=${metric}&line=${encodeURIComponent(lineCode)}`,
    ),
  ncrReport: (entity: string) =>
    request<NcrReport>(`/entities/${entity}/ncr-report`),
  lcrReport: (entity: string, asOf?: string) =>
    request<NcrReport>(
      `/entities/${entity}/lcr-report${asOf ? `?as_of=${asOf}` : ""}`,
    ),
  nsfrReport: (entity: string, asOf?: string) =>
    request<NsfrReport>(
      `/entities/${entity}/nsfr-report${asOf ? `?as_of=${asOf}` : ""}`,
    ),
  regulatorySeries: (entity: string, reportType: "lcr" | "nsfr") =>
    request<{ report_type: string; points: RegulatoryPoint[] }>(
      `/entities/${entity}/regulatory-series?report_type=${reportType}`,
    ),
  regulatoryDrivers: (
    entity: string,
    reportType: "lcr" | "nsfr",
    asOf: string,
  ) =>
    request<RegulatoryDrivers>(
      `/entities/${entity}/regulatory-drivers?report_type=${reportType}&as_of=${asOf}`,
    ),
  regulatoryDriverDetail: (
    entity: string,
    reportType: "lcr" | "nsfr",
    asOf: string,
    detailKey: string,
  ) =>
    request<RegulatoryDriverDetail>(
      `/entities/${entity}/regulatory-driver-detail?report_type=${reportType}&as_of=${asOf}&detail_key=${detailKey}`,
    ),
  regulatoryMovementHistory: (entity: string, reportType: "lcr" | "nsfr") =>
    request<{ report_type: string; movements: RegulatoryMovement[] }>(
      `/entities/${entity}/regulatory-movement-history?report_type=${reportType}`,
    ),
  regulatoryExportUrl: (
    entity: string,
    reportType: "lcr" | "nsfr",
    asOf: string,
  ) =>
    `/api/v1/entities/${entity}/regulatory-export?report_type=${reportType}&as_of=${asOf}`,
  lcrStressConfig: (entity: string) =>
    request<{
      configuration: StressConfig;
      top_depositor_amounts: Record<string, number>;
      updated: string;
    }>(`/entities/${entity}/lcr-stress-config`),
  saveLcrStressConfig: (
    entity: string,
    data: {
      configuration: StressConfig;
      top_depositor_amounts: Record<string, number>;
    },
  ) =>
    request<{
      configuration: StressConfig;
      top_depositor_amounts: Record<string, number>;
      updated: string;
    }>(`/entities/${entity}/lcr-stress-config`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  restoreLcrStressDefault: (entity: string, scenarioId: string) =>
    request<{
      configuration: StressConfig;
      top_depositor_amounts: Record<string, number>;
      updated: string;
    }>(`/entities/${entity}/lcr-stress-config/restore-default`, {
      method: "POST",
      body: JSON.stringify({ scenario_id: scenarioId }),
    }),
  lcrStressPreview: (entity: string, asOf: string) =>
    request<{
      as_of_date: string;
      configuration: StressConfig;
      results: LcrStressResults;
    }>(`/entities/${entity}/lcr-stress-preview?as_of=${asOf}`),
  lcrStressRuns: (entity: string) =>
    request<{
      runs: {
        id: number;
        as_of_date: string;
        created: string;
        baseline_lcr: string;
        scenario_count: number;
      }[];
    }>(`/entities/${entity}/lcr-stress-runs`),
  lcrStressRun: (entity: string, id: number) =>
    request<StressRun>(`/entities/${entity}/lcr-stress-runs/${id}`),
  createLcrStressRun: (entity: string, asOf: string) =>
    request<StressRun>(`/entities/${entity}/lcr-stress-runs?as_of=${asOf}`, {
      method: "POST",
      body: "{}",
    }),
  lcrStressExportUrl: (entity: string, id: number) =>
    `/api/v1/entities/${entity}/lcr-stress-runs/${id}/export`,
  addAssumption: (
    entity: string,
    data: Omit<LiquidityAssumption, "id" | "updated">,
  ) =>
    request<LiquidityAssumptionSet>(`/entities/${entity}/assumptions`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  saveAssumption: (
    entity: string,
    id: number,
    data: Partial<LiquidityAssumption>,
  ) =>
    request<LiquidityAssumptionSet>(`/entities/${entity}/assumptions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteAssumption: (entity: string, id: number) =>
    request<LiquidityAssumptionSet>(`/entities/${entity}/assumptions/${id}`, {
      method: "DELETE",
    }),
  savePortfolio: (input: Input, revision: number) =>
    request<Portfolio>(`/entities/${input.entity}/portfolio`, {
      method: "PUT",
      body: JSON.stringify({ ...input, expected_revision: revision }),
    }),
  validate: (input: Input) =>
    request<Validation>("/validate", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  runs: (entity: string) => request<{ runs: Run[] }>(`/runs?entity=${entity}`),
  run: (id: string) => request<Run>(`/runs/${id}`),
  submit: (input: Input, key: string) =>
    request<{ id: string; status: string }>("/runs", {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify(input),
    }),
  flows: (id: string, contract: string, offset = 0) =>
    request<{ total: number; cashflows: Flow[] }>(
      `/runs/${id}/cashflows?contract_id=${encodeURIComponent(contract)}&limit=100&offset=${offset}`,
    ),
  behavioralFlows: (id: string, contract: string, offset = 0) =>
    request<{ total: number; cashflows: BehavioralFlow[] }>(
      `/runs/${id}/behavioral-cashflows?contract_id=${encodeURIComponent(contract)}&limit=100&offset=${offset}`,
    ),
  contracts: (id: string, q: string) =>
    request<{ query: string; contracts: RunContract[] }>(
      `/runs/${id}/contracts?q=${encodeURIComponent(q)}&limit=25`,
    ),
  input: (id: string) => request<Input>(`/runs/${id}/input`),
};
export const money = (value: string | number, currency = "JOD") =>
  Number(value).toLocaleString("en-US", {
    minimumFractionDigits: currency === "JOD" ? 3 : 2,
    maximumFractionDigits: currency === "JOD" ? 3 : 2,
  });
export const compact = (value: string | number) =>
  new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(Number(value));
export const dateLabel = (s: string) =>
  s
    ? new Date(s + "T00:00:00").toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : "—";
export const timeLabel = (s: string) =>
  new Date(s).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
export const productLabel = (s: string) =>
  ({
    loan: "Loan",
    term_deposit: "Term deposit",
    bond: "Bond",
    interbank_asset: "Interbank placement",
    cash_central_bank: "Cash & central bank",
    borrowing: "Borrowing",
    demand_deposit: "Demand deposit",
  })[s] || s;
export const toInput = (p: Portfolio): Input => ({
  entity: p.entity.slug,
  as_of_date: p.as_of_date,
  bucket_days: p.bucket_days,
  contracts: p.contracts,
});
