export type Entity = {
  id: string;
  slug: string;
  name: string;
  country: string;
  base_currency: string;
  is_mock: boolean;
  contract_count: number;
  as_of_date: string;
};
export type Contract = {
  contract_id: string;
  product: string;
  currency: string;
  principal: string;
  annual_rate?: string;
  repayment?: string;
  rate_type?: string;
  interest_rate_index?: string;
  client_rate_spread?: string;
  rate_cap?: string;
  rate_floor?: string;
  day_count?: string;
  frequency_months?: number;
  accrual_start?: string;
  next_payment?: string;
  maturity?: string;
  end_of_month?: boolean;
  status?: string;
  liquidity_product?: string;
  liquidity_group?: string;
};
export type Portfolio = {
  entity: Entity;
  as_of_date: string;
  bucket_days: number[];
  revision: number;
  contracts: Contract[];
};
export type Input = {
  entity: string;
  as_of_date: string;
  bucket_days: number[];
  contracts?: Contract[];
  use_saved_portfolio?: boolean;
  calculation_basis?: "contractual" | "behavioral";
  data_readiness_resolutions?: DataReadinessResolution[];
};
export type PortfolioSummary = {
  entity: Entity;
  as_of_date: string;
  bucket_days: number[];
  revision: number;
  contract_count: number;
  currencies: string[];
  products: string[];
  product_count: number;
  missing_maturity_count: number;
};
export type PortfolioContractPage = {
  total: number;
  offset: number;
  limit: number;
  contracts: Contract[];
};
export type Bucket = {
  bucket: string;
  inflow_principal: string;
  inflow_interest: string;
  outflow_principal: string;
  outflow_interest: string;
  inflows: string;
  outflows: string;
  net_gap: string;
  cumulative_gap: string;
};
export type Flow = {
  contract_id: string;
  product: string;
  currency: string;
  direction: string;
  payment_date: string;
  accrual_start: string;
  accrual_end: string;
  principal: string;
  interest: string;
  total: string;
  remaining_principal: string;
  bucket: string;
  maturity_source?: "bank" | "proxy" | "open";
};
export type RunContract = {
  contract_id: string;
  product: string;
  currency: string;
  direction: string;
};
export type Control = {
  currency: string;
  scheduled_balance: string;
  generated_principal: string;
  difference: string;
  undated_balance: string;
  passed: boolean;
};
export type Exception = { row: number; contract_id: string; error: string };
export type DataReadinessResolution = {
  group_key: string;
  action: "use_candidate_date" | "set_next_payment_date" | "derive_from_reporting_date" | "proxy_maturity" | "exclude";
  date?: string;
  candidate_field?: string;
};
export type DataReadinessGroup = {
  key: string;
  source_table: string;
  product: string;
  issue: string;
  issue_label: string;
  contract_count: number;
  balances: Record<string, string>;
  candidate_fields: string[];
  allowed_actions: DataReadinessResolution["action"][];
  examples: string[];
};
export type Validation = {
  accepted_count: number;
  rejected_count: number;
  cashflow_count: number;
  exceptions: Exception[];
  controls: Control[];
  undated: {
    contract_id: string;
    currency: string;
    balance: string;
    reason: string;
  }[];
  readiness_groups: DataReadinessGroup[];
};
export type LadderDetail = {
  key: string;
  label: string;
  balance: string;
  principal: string[];
  interest: string[];
  total: string[];
};
export type LadderRow = {
  section: string;
  key: string;
  label: string;
  kind: "normal" | "subtotal" | "gap" | "cumulative";
  balance: string;
  principal: string[];
  interest: string[];
  total: string[];
  children?: LadderDetail[];
};
export type BankLadder = {
  buckets: { code: string; label: string }[];
  rows: LadderRow[];
};
export type Result = Validation & {
  engine_version: string;
  as_of_date: string;
  entity: string;
  bucket_days: number[];
  input_count: number;
  currencies: string[];
  summary: Record<string, Bucket[]>;
  bank_ladder: Record<string, BankLadder>;
  behavioral_bank_ladder?: Record<string, BankLadder>;
  calculation_basis?: "contractual" | "behavioral";
  behavioral_assumption_set?: {
    id: number;
    name: string;
    version: number;
    effective_date: string;
    source: string;
  } | null;
  interest_projection: "constant" | "forward_curve";
  basis: string;
  status: string;
};
export type ForwardCurvePoint = {
  currency: string;
  index: string;
  tenor_days: number;
  rate: string;
};
export type EntitySettings = {
  as_of_date: string;
  interest_projection: "constant" | "forward_curve";
  forward_curve: ForwardCurvePoint[];
  proxy_maturity_enabled: boolean;
  proxy_maturity_date: string | null;
  proxy_maturity_scope: Record<string, unknown>;
  updated: string;
};
export type LiquidityAssumption = {
  id: number;
  category:
    | "deposit_runoff"
    | "term_deposit_early_withdrawal"
    | "loan_prepayment"
    | "facility_drawdown"
    | "rollover"
    | "security_liquidation"
    | "security_haircut";
  title: string;
  product_group: string;
  product_type: string;
  currency_scope: string;
  maturity_breakdown: string;
  value: {
    curve?: { days: number; label?: string; cumulative: string }[];
    curve_type?: string;
    timing?: string;
    haircut?: string;
    rollover_rate?: string;
    rollover_days?: number;
  };
  enabled: boolean;
  sort_order: number;
  updated: string;
};
export type LiquidityAssumptionSet = {
  id: number;
  name: string;
  version: number;
  effective_date: string;
  status: "active" | "draft" | "retired";
  source: string;
  is_system: boolean;
  updated: string;
  rules: LiquidityAssumption[];
};
export type ProductCatalogueChoice = {
  id: number;
  classification: string;
  product_group: string;
  product_type: string;
  cash_flow_treatment: "contractual" | "behavioral" | "hybrid" | "excluded";
  treatment_note: string;
};
export type NcrRow = {
  section: string;
  key: string;
  label: string;
  kind: "normal" | "subtotal" | "adjustment" | "section" | "ratio";
  factor: string | null;
  exposure: string;
  weighted: string;
};
export type NcrReport = {
  entity: string;
  entity_name: string;
  currency: string;
  as_of_date: string | null;
  source_position_count: number;
  rows: NcrRow[];
  lcr: string;
  hqla: string;
  net_cash_outflows: string;
  total_outflows: string;
  total_inflows?: string;
  eligible_inflows: string;
  basis: string;
};
export type NsfrRow = {
  section: "asf" | "rsf" | "result";
  code: string;
  label: string;
  jod: string[];
  usd: string[];
  other: string[];
  factors: string[];
  weighted: string;
  kind: "normal" | "subtotal" | "ratio";
};
export type NsfrReport = {
  entity: string;
  entity_name: string;
  currency: string;
  as_of_date: string | null;
  rows: NsfrRow[];
  asf: string;
  rsf: string;
  nsfr: string;
  basis: string;
};
export type RegulatoryPoint = {
  as_of_date: string;
  ratio: string;
  primary: string;
  secondary: string;
};
export type RegulatoryDrivers = {
  comparison_date: string | null;
  drivers: {
    label: string;
    amount: string;
    ratio_impact: string;
    detail_key: string;
    source_key?: string;
  }[];
  reconciled: boolean;
};
export type RegulatoryMovement = {
  as_of_date: string;
  comparison_date: string;
  ratio: string;
  delta_pp: string;
  primary_driver: RegulatoryDrivers["drivers"][number] | null;
  drivers: RegulatoryDrivers["drivers"];
  reconciled: boolean;
};
export type RegulatoryDriverDetail = {
  report_type: "lcr" | "nsfr";
  detail_key: string;
  label: string;
  as_of_date: string;
  comparison_date: string | null;
  driver_impact_pp: string;
  ratio_change_pp: string;
  currency: string;
  data_status: string;
  reconciled: boolean;
  items: {
    id: string;
    source_line_item: string;
    classification: string;
    code: string;
    prior_balance: string;
    current_balance: string;
    balance_change: string;
    factor: string | null;
    prior_contribution: string;
    current_contribution: string;
    contribution_change: string;
    metric_impact_pp: string;
    share_of_movement: string | null;
  }[];
};
export type StressRule = {
  name: string;
  target: string;
  operation: string;
  value_source?: string;
  values: Record<string, number>;
  element_ids?: string[];
};
export type StressScenario = {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  system_default: boolean;
  protected: boolean;
  levels: { id: string; label: string }[];
  rules: StressRule[];
};
export type StressConfig = {
  version: string;
  inflow_cap: number;
  lcr_limit: number;
  lcr_tolerance: number;
  scenarios: StressScenario[];
};
export type StressResultRow = {
  scenario_id: string;
  scenario: string;
  description: string;
  type: string;
  severity_id: string;
  severity: string;
  hqla: string;
  weighted_outflows: string;
  gross_weighted_inflows: string;
  inflow_cap: string;
  recognized_inflows: string;
  net_cash_outflow: string;
  lcr: string;
  movement: string;
  risk_status: string;
  lcr_report?: NcrReport;
};
export type LcrStressResults = {
  baseline: {
    hqla: string;
    weighted_outflows: string;
    gross_weighted_inflows: string;
    inflow_cap: string;
    recognized_inflows: string;
    net_cash_outflow: string;
    lcr: string;
    risk_status: string;
  };
  results: StressResultRow[];
  audit: Record<string, string>[];
  limit: string;
  tolerance: string;
  inflow_cap: string;
};
export type StressRun = {
  id: number;
  as_of_date: string;
  created: string;
  results: LcrStressResults;
  configuration?: {
    configuration: StressConfig;
    top_depositor_amounts: Record<string, number>;
  };
};
export type Run = {
  id: string;
  created: string;
  status: string;
  progress: number;
  error: string;
  as_of_date: string;
  entity: string;
  entity_name: string;
  is_mock: boolean;
  engine_version: string;
  result?: Result | null;
  input_hash?: string;
  started?: string;
  finished?: string;
};
export type Session = { username: string; is_staff: boolean };
