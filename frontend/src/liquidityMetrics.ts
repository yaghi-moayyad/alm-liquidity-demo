import type {BankLadder, LadderRow, Result} from './types';

export type CashFlowBasis = 'contractual' | 'behavioral';
export type CashFlowMode = 'principal' | 'total';

export type LiquidityBucket = {
  code: string;
  label: string;
  index: number;
  inflows: number;
  outflows: number;
  offBalance: number;
  capacity: number;
  gapBefore: number;
  gapAfter: number;
  cumulativeBefore: number;
  cumulativeAfter: number;
  cushionPercent: number | null;
};

export type LiquidityProfile = {
  ladder: BankLadder;
  buckets: LiquidityBucket[];
  reconciled: boolean;
  capacityBalance: number;
};

const required = [
  'total_inflows', 'total_outflows', 'total_off_balance_sheet',
  'total_counterbalancing_capacity', 'contractual_gap',
  'contractual_gap_including_capacity', 'cumulative_contractual_gap',
  'cumulative_gap_including_capacity',
];

export const amount = (value: string | number | null | undefined): number => Number(value || 0);

export function ladderFor(result: Result, currency: string, basis: CashFlowBasis): BankLadder | undefined {
  return basis === 'behavioral' ? result.behavioral_bank_ladder?.[currency] : result.bank_ladder?.[currency];
}

export function buildLiquidityProfile(ladder: BankLadder | undefined, mode: CashFlowMode): LiquidityProfile | null {
  if (!ladder?.buckets.length) return null;
  const byKey = new Map(ladder.rows.map(row => [row.key, row]));
  if (required.some(key => !byKey.get(key)?.[mode] || byKey.get(key)![mode].length !== ladder.buckets.length)) return null;
  const cell = (key: string, index: number) => amount(byKey.get(key)![mode][index]);
  let cumulativeBefore = 0, cumulativeAfter = 0, reconciled = true;
  // The balance-based gap ratio is deliberately principal-only. It compares
  // each maturity-bucket gap with the current stock of outflow obligations;
  // off-balance-sheet is kept signed as supplied in the ladder.
  const balanceDenominator = amount(byKey.get('total_outflows')?.balance) + amount(byKey.get('total_off_balance_sheet')?.balance);
  const buckets = ladder.buckets.map((bucket, index) => {
    const inflows = cell('total_inflows', index);
    const outflows = cell('total_outflows', index);
    const offBalance = cell('total_off_balance_sheet', index);
    const capacity = cell('total_counterbalancing_capacity', index);
    const gapBefore = inflows - outflows - offBalance;
    const gapAfter = gapBefore + capacity;
    cumulativeBefore += gapBefore;
    cumulativeAfter += gapAfter;
    if (Math.abs(cell('contractual_gap', index) - gapBefore) > 0.05 ||
        Math.abs(cell('contractual_gap_including_capacity', index) - gapAfter) > 0.05 ||
        Math.abs(cell('cumulative_contractual_gap', index) - cumulativeBefore) > 0.05 * (index + 1) ||
        Math.abs(cell('cumulative_gap_including_capacity', index) - cumulativeAfter) > 0.05 * (index + 1)) reconciled = false;
    return {
      code: bucket.code, label: bucket.label, index,
      inflows, outflows, offBalance, capacity, gapBefore, gapAfter,
      cumulativeBefore, cumulativeAfter,
      // Principal contractual gap including capacity / principal as-of obligations.
      // This is a management metric for one bucket, not regulatory LCR.
      cushionPercent: balanceDenominator > 0 ? 100 * cell('contractual_gap_including_capacity', index) / balanceDenominator : null,
    };
  });
  return {ladder, buckets, reconciled, capacityBalance: amount(byKey.get('total_counterbalancing_capacity')?.balance)};
}

export function lineContributors(ladder: BankLadder, bucketIndex: number, mode: CashFlowMode) {
  return ladder.rows.filter(row => row.kind === 'normal' &&
    ['inflows', 'outflows', 'off_balance_sheet', 'counterbalancing_capacity'].includes(row.section))
    .map(row => ({
      ...row,
      amount: amount(row[mode][bucketIndex]),
      childrenInBucket: (row.children || []).map(child => ({...child, amount: amount(child[mode][bucketIndex])}))
        .filter(child => Math.abs(child.amount) > 0.005).sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount)),
    })).filter(row => Math.abs(row.amount) > 0.005)
    .sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount));
}

export function comparableBucket(current: LiquidityProfile, previous: LiquidityProfile | null, code: string): LiquidityBucket | null {
  if (!previous || current.buckets.length !== previous.buckets.length ||
      !current.buckets.every((bucket, index) => bucket.code === previous.buckets[index].code)) return null;
  return previous.buckets.find(bucket => bucket.code === code) || null;
}

export function bucketMovement(current: LiquidityBucket, previous: LiquidityBucket) {
  return [
    {label: 'Inflows', movement: current.inflows - previous.inflows},
    {label: 'Outflows', movement: previous.outflows - current.outflows},
    {label: 'Off-balance-sheet', movement: previous.offBalance - current.offBalance},
    {label: 'Counterbalancing capacity', movement: current.capacity - previous.capacity},
  ];
}

export function lineMovement(current: BankLadder, previous: BankLadder, index: number, mode: CashFlowMode) {
  const earlier = new Map(previous.rows.map(row => [row.key, row]));
  return current.rows.filter(row => row.kind === 'normal' &&
    ['inflows', 'outflows', 'off_balance_sheet', 'counterbalancing_capacity'].includes(row.section))
    .map(row => {
      const old = earlier.get(row.key);
      const delta = amount(row[mode][index]) - amount(old?.[mode][index]);
      const contribution = row.section === 'outflows' || row.section === 'off_balance_sheet' ? -delta : delta;
      return {key: row.key, label: row.label, section: row.section, delta, contribution};
    }).filter(row => Math.abs(row.contribution) > 0.005)
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));
}

export function liquidityCsv(profile: LiquidityProfile, currency: string, basis: CashFlowBasis, mode: CashFlowMode, asOfDate: string) {
  const quote = (cell: string | number | null) => `"${String(cell ?? '').replaceAll('"', '""')}"`;
  const lines = [
    ['Reporting date', asOfDate], ['Currency', currency], ['Basis', basis], ['Cash flow', mode],
    [],
    ['Bucket', 'Inflows', 'Outflows', 'Off-balance-sheet obligations', 'Counterbalancing capacity',
      'Gap before capacity', 'Gap after capacity', 'Cumulative before capacity', 'Cumulative after capacity', 'Principal gap ratio / signed as-of outflow balance % (not LCR)'],
    ...profile.buckets.map(bucket => [bucket.label, bucket.inflows, bucket.outflows, bucket.offBalance, bucket.capacity,
      bucket.gapBefore, bucket.gapAfter, bucket.cumulativeBefore, bucket.cumulativeAfter, bucket.cushionPercent]),
  ];
  return '\uFEFF' + lines.map(line => line.map(quote).join(',')).join('\r\n');
}

export type LineContributor = ReturnType<typeof lineContributors>[number];
export type LadderSection = LadderRow['section'];
