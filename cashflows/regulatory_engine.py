from __future__ import annotations
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

REGULATORY_ENGINE_VERSION = '0.1.0'
D0 = Decimal('0')
D1 = Decimal('1')


def dec(value: Any, default: str = '0') -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def residual_days(terms: dict, as_of: date) -> int | None:
    raw = terms.get('maturity')
    if not raw:
        return None
    try:
        d = date.fromisoformat(str(raw))
    except ValueError:
        return None
    return max((d - as_of).days, 0)


def maturity_band(days: int | None) -> str:
    if days is None:
        return 'open'
    if days < 180:
        return '<6m'
    if days < 365:
        return '6-12m'
    return '>=1y'


def _factor_for_nsfr(treatment: dict, days: int | None) -> Decimal:
    factors = treatment.get('factors') or {}
    band = maturity_band(days)
    if band in factors:
        return dec(factors[band])
    return dec(treatment.get('factor', '0'))


def calculate_regulatory(entity, contracts, mappings, config, as_of: date):
    """Deterministic first-stage LCR/NSFR engine.

    Source contracts are the authority. Regulatory mappings supply only the
    classifications/factors that are not present on the source records. Every
    contribution is returned for persistence and drill-down.
    """
    active_mappings = [m for m in mappings if m.active]
    def find_mapping(terms, product):
        group = str(terms.get('liquidity_group') or '')
        lp = str(terms.get('liquidity_product') or '')
        candidates = [m for m in active_mappings if m.source_product == product]
        for m in candidates:
            if m.liquidity_group == group and m.liquidity_product == lp and (group or lp): return m
        for m in candidates:
            if m.liquidity_group == group and not m.liquidity_product and group: return m
        for m in candidates:
            if not m.liquidity_group and not m.liquidity_product: return m
        return None
    reporting_currency = config.reporting_currency or entity.base_currency
    fx = {k.upper(): dec(v) for k, v in (config.fx_to_reporting or {}).items()}
    fx.setdefault(reporting_currency, D1)

    lcr_lines: dict[str, dict] = {}
    nsfr_lines: dict[str, dict] = {}
    contributions = []
    warnings: list[dict] = []
    source_total = D0
    converted_total = D0
    mapped_total = D0

    def line_add(store, code, label, amount, raw_amount, factor, section):
        row = store.setdefault(code, {'code': code, 'label': label, 'section': section,
                                      'source_balance': D0, 'weighted_amount': D0})
        row['source_balance'] += raw_amount
        row['weighted_amount'] += amount

    for contract in contracts:
        terms = contract.terms or {}
        cid = terms.get('contract_id') or contract.external_id
        product = str(terms.get('product') or '')
        ccy = str(terms.get('currency') or reporting_currency).upper()
        balance = abs(dec(terms.get('principal')))
        source_total += balance
        rate = fx.get(ccy)
        if rate is None:
            warnings.append({'contract_id': cid, 'type': 'missing_fx', 'message': f'No {ccy}->{reporting_currency} FX rate configured.'})
            continue
        base = balance * rate
        converted_total += base
        mapping = find_mapping(terms, product)
        if mapping is None:
            warnings.append({'contract_id': cid, 'type': 'unmapped_product', 'message': f'No regulatory mapping for source product {product or "(blank)"}.'})
            continue
        mapped_total += base
        days = residual_days(terms, as_of)
        band = maturity_band(days)

        # LCR
        lcr = mapping.lcr_treatment or {}
        kind = lcr.get('kind', 'excluded')
        applies = True
        if lcr.get('within_days') is not None:
            applies = days is not None and days <= int(lcr['within_days'])
        if kind != 'excluded' and applies:
            factor = dec(lcr.get('factor', '0'))
            code = lcr.get('line_code') or 'LCR_UNCLASSIFIED'
            label = lcr.get('line_label') or mapping.title
            weighted = base * factor
            section = {'hqla':'HQLA', 'outflow':'Outflows', 'inflow':'Inflows'}.get(kind, 'Other')
            line_add(lcr_lines, code, label, weighted, base, factor, section)
            contributions.append({
                'metric': 'LCR', 'contract_id': cid, 'product': product, 'currency': ccy,
                'source_balance': base, 'category_code': code, 'category_label': label,
                'factor': factor, 'weighted_amount': weighted, 'maturity_band': band,
                'treatment': {'kind': kind, 'days_to_maturity': days, 'fx_rate': str(rate), 'source_balance_original': str(balance)},
            })

        # NSFR
        nsfr = mapping.nsfr_treatment or {}
        side = nsfr.get('side', 'excluded')
        if side in ('ASF', 'RSF'):
            factor = _factor_for_nsfr(nsfr, days)
            code = nsfr.get('line_code') or f'NSFR_{side}_UNCLASSIFIED'
            label = nsfr.get('line_label') or mapping.title
            weighted = base * factor
            line_add(nsfr_lines, code, label, weighted, base, factor, side)
            contributions.append({
                'metric': 'NSFR', 'contract_id': cid, 'product': product, 'currency': ccy,
                'source_balance': base, 'category_code': code, 'category_label': label,
                'factor': factor, 'weighted_amount': weighted, 'maturity_band': band,
                'treatment': {'side': side, 'days_to_maturity': days, 'fx_rate': str(rate), 'source_balance_original': str(balance)},
            })

    hqla = sum((r['weighted_amount'] for r in lcr_lines.values() if r['section'] == 'HQLA'), D0)
    outflows = sum((r['weighted_amount'] for r in lcr_lines.values() if r['section'] == 'Outflows'), D0)
    inflows = sum((r['weighted_amount'] for r in lcr_lines.values() if r['section'] == 'Inflows'), D0)
    inflow_cap = outflows * dec(config.lcr_inflow_cap or '0.75')
    eligible_inflows = min(inflows, inflow_cap)
    net_outflows = max(outflows - eligible_inflows, D0)
    lcr_ratio = (hqla / net_outflows * Decimal('100')) if net_outflows else None

    asf = sum((r['weighted_amount'] for r in nsfr_lines.values() if r['section'] == 'ASF'), D0)
    rsf = sum((r['weighted_amount'] for r in nsfr_lines.values() if r['section'] == 'RSF'), D0)
    nsfr_ratio = (asf / rsf * Decimal('100')) if rsf else None

    def clean_lines(store):
        order = {'HQLA':0, 'Outflows':1, 'Inflows':2, 'ASF':0, 'RSF':1, 'Other':9}
        rows = sorted(store.values(), key=lambda r: (order.get(r['section'], 9), r['code']))
        return [{**r, 'source_balance': str(r['source_balance'].quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)),
                    'weighted_amount': str(r['weighted_amount'].quantize(Decimal('0.001'), rounding=ROUND_HALF_UP))} for r in rows]

    controls = {
        'source_contract_count': len(contracts),
        'mapped_contract_count': len({c['contract_id'] for c in contributions}),
        'warning_count': len(warnings),
        'reporting_currency': reporting_currency,
        'source_balance_nominal': str(source_total),
        'source_balance_converted': str(converted_total.quantize(Decimal('0.001'))),
        'mapped_balance_converted': str(mapped_total.quantize(Decimal('0.001'))),
        'complete_mapping': not any(w['type'] in ('missing_fx','unmapped_product') for w in warnings),
    }
    lcr_result = {
        'hqla': str(hqla.quantize(Decimal('0.001'))), 'gross_outflows': str(outflows.quantize(Decimal('0.001'))),
        'gross_inflows': str(inflows.quantize(Decimal('0.001'))), 'inflow_cap': str(inflow_cap.quantize(Decimal('0.001'))),
        'eligible_inflows': str(eligible_inflows.quantize(Decimal('0.001'))), 'net_cash_outflows': str(net_outflows.quantize(Decimal('0.001'))),
        'ratio': None if lcr_ratio is None else str(lcr_ratio.quantize(Decimal('0.01'))), 'lines': clean_lines(lcr_lines),
    }
    nsfr_result = {
        'asf': str(asf.quantize(Decimal('0.001'))), 'rsf': str(rsf.quantize(Decimal('0.001'))),
        'ratio': None if nsfr_ratio is None else str(nsfr_ratio.quantize(Decimal('0.01'))), 'lines': clean_lines(nsfr_lines),
    }
    return {'lcr': lcr_result, 'nsfr': nsfr_result, 'controls': controls, 'warnings': warnings, 'contributions': contributions}
