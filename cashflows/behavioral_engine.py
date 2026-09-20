"""Assumption-driven behavioural cash-flow transformation engine.

The contractual engine remains the source of legal payment dates.  This module
creates a second, auditable behavioural view by applying approved rule snapshots
without reading the database.  That keeps completed runs reproducible and makes
future statistical/ML calibration a plug-in source of assumptions rather than a
replacement for the cash-flow engine.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

D = Decimal

CURVE_CATEGORIES = {
    'deposit_runoff',
    'loan_prepayment',
    'term_deposit_early_withdrawal',
}


def _decimal(value, default='0'):
    try:
        result = D(str(value if value is not None else default))
    except Exception:
        return D(default)
    return result if result.is_finite() else D(default)


def _scope(currency, base_currency):
    return 'LCY' if currency == base_currency else 'FCY'


def _match_rule(rules, category, group, product, currency, base_currency):
    """Return the most specific enabled rule for a product/currency.

    Exact product beats ALL and exact LCY/FCY beats ALL.  sort_order remains the
    stable tie-breaker because rule snapshots preserve it.
    """
    scope = _scope(currency, base_currency)
    matches = []
    for rule in rules:
        if not rule.get('enabled', True) or rule.get('category') != category:
            continue
        if rule.get('product_group', '') not in ('', 'ALL', group):
            continue
        if rule.get('product_type', '') not in ('', 'ALL', product):
            continue
        if rule.get('currency_scope', 'ALL') not in ('ALL', scope, currency):
            continue
        specificity = (
            1 if rule.get('product_group') == group else 0,
            1 if rule.get('product_type') == product else 0,
            1 if rule.get('currency_scope') in (scope, currency) else 0,
            -int(rule.get('sort_order', 0)),
        )
        matches.append((specificity, rule))
    return max(matches, key=lambda item: item[0])[1] if matches else None


def _treatment_for(treatments, group, product, fallback='hybrid'):
    for item in treatments or []:
        if item.get('product_group') == group and item.get('product_type') == product:
            return item.get('cashflow_treatment', fallback)
    return fallback


def _curve_increments(rule):
    prior = D(0)
    for point in sorted((rule or {}).get('value', {}).get('curve', []), key=lambda p: int(p.get('days', 0))):
        days = int(point.get('days', 0))
        cumulative = min(D(1), max(D(0), _decimal(point.get('cumulative'))))
        increase = max(D(0), cumulative - prior)
        prior = max(prior, cumulative)
        if days > 0 and increase > 0:
            yield days, increase, cumulative


def _event(template, asof, days, principal, quantum, source, rule=None, remaining=None):
    payment = asof + timedelta(days=days)
    amount = principal.quantize(quantum, rounding=ROUND_HALF_UP)
    result = {
        'contract_id': template['contract_id'],
        'product': template['product'],
        'currency': template['currency'],
        'direction': template['direction'],
        'payment_date': payment.isoformat(),
        'accrual_start': asof.isoformat(),
        'accrual_end': payment.isoformat(),
        'days_from_asof': days,
        'principal': str(amount),
        'interest': str(D(0).quantize(quantum)),
        'total': str(amount),
        'remaining_principal': str((remaining if remaining is not None else D(0)).quantize(quantum)),
        'liquidity_product': template.get('liquidity_product', ''),
        'liquidity_group': template.get('liquidity_group', ''),
        'behavioral_source': source,
        'behavioral_rule_id': (rule or {}).get('id'),
        'behavioral_rule_title': (rule or {}).get('title', ''),
    }
    return result



def _restate_remaining_principal(flows, quantum):
    """Recalculate behavioural outstanding principal after timing shifts."""
    ordered = sorted(flows, key=lambda f: (f['payment_date'], f.get('behavioral_source', 'contractual')))
    remaining = sum((_decimal(flow.get('principal')) for flow in ordered), D(0))
    for flow in ordered:
        remaining -= _decimal(flow.get('principal'))
        flow['remaining_principal'] = str(max(D(0), remaining).quantize(quantum, rounding=ROUND_HALF_UP))
    return ordered

def _shift_principal_earlier(contract_flows, asof, rule, quantum, source):
    """Shift principal from later contractual dates to behavioural dates.

    V1 intentionally leaves contractual interest unchanged.  The adjustment is
    therefore a principal-timing model, which is transparent and conservative
    for an MVP.  A later version can recalculate interest after prepayment.
    """
    if not contract_flows:
        return contract_flows, [], D(0)
    flows = deepcopy(contract_flows)
    opening = sum((_decimal(flow.get('principal')) for flow in flows), D(0))
    shifted_total = D(0)
    extras = []
    template = flows[0]

    for days, increase, _cumulative in _curve_increments(rule):
        target = (opening * increase).quantize(quantum, rounding=ROUND_HALF_UP)
        if target <= 0:
            continue
        event_date = asof + timedelta(days=days)
        candidates = [flow for flow in flows if date.fromisoformat(flow['payment_date']) > event_date and _decimal(flow.get('principal')) > 0]
        available = sum((_decimal(flow['principal']) for flow in candidates), D(0))
        amount = min(target, available)
        if amount <= 0:
            continue
        left = amount
        # Reduce the furthest contractual principal first: prepayment shortens
        # behavioural maturity while preserving nearer scheduled instalments.
        for flow in sorted(candidates, key=lambda f: f['payment_date'], reverse=True):
            current = _decimal(flow['principal'])
            reduction = min(current, left)
            new_principal = current - reduction
            flow['principal'] = str(new_principal.quantize(quantum))
            flow['total'] = str((new_principal + _decimal(flow.get('interest'))).quantize(quantum))
            left -= reduction
            if left <= 0:
                break
        shifted_total += amount
        extras.append(_event(template, asof, days, amount, quantum, source, rule))

    combined = [flow for flow in flows if _decimal(flow.get('principal')) > 0 or _decimal(flow.get('interest')) > 0] + extras
    combined = _restate_remaining_principal(combined, quantum)
    return combined, extras, shifted_total


def _apply_rollover(contract_flows, asof, rule, quantum):
    if not contract_flows or not rule:
        return contract_flows, [], D(0)
    rate = min(D(1), max(D(0), _decimal(rule.get('value', {}).get('rollover_rate'))))
    tenor_days = int(rule.get('value', {}).get('tenor_days') or 0)
    if rate <= 0 or tenor_days <= 0:
        return contract_flows, [], D(0)
    flows = deepcopy(contract_flows)
    principal_flows = [f for f in flows if _decimal(f.get('principal')) > 0]
    if not principal_flows:
        return flows, [], D(0)
    maturity_flow = max(principal_flows, key=lambda f: f['payment_date'])
    maturity_principal = _decimal(maturity_flow['principal'])
    rolled = (maturity_principal * rate).quantize(quantum, rounding=ROUND_HALF_UP)
    if rolled <= 0:
        return flows, [], D(0)
    maturity_flow['principal'] = str((maturity_principal - rolled).quantize(quantum))
    maturity_flow['total'] = str((_decimal(maturity_flow.get('interest')) + maturity_principal - rolled).quantize(quantum))
    maturity_date = date.fromisoformat(maturity_flow['payment_date'])
    new_date = maturity_date + timedelta(days=tenor_days)
    event = deepcopy(maturity_flow)
    event.update({
        'payment_date': new_date.isoformat(),
        'accrual_start': maturity_date.isoformat(),
        'accrual_end': new_date.isoformat(),
        'days_from_asof': (new_date - asof).days,
        'principal': str(rolled),
        'interest': str(D(0).quantize(quantum)),
        'total': str(rolled),
        'remaining_principal': str(D(0).quantize(quantum)),
        'behavioral_source': 'term_deposit_rollover',
        'behavioral_rule_id': rule.get('id'),
        'behavioral_rule_title': rule.get('title', ''),
    })
    flows.append(event)
    flows = _restate_remaining_principal(flows, quantum)
    event = next(flow for flow in flows if flow.get('behavioral_source') == 'term_deposit_rollover' and flow['payment_date'] == new_date.isoformat())
    return flows, [event], rolled


def generate_behavioral_cashflows(contractual_flows, undated, asof, assumption_set, precision, treatments=None):
    """Generate the behavioural cash-flow view and audit diagnostics.

    Parameters are plain Python objects so this function can be unit tested and
    called from workers without Django/database access.
    """
    if isinstance(asof, str):
        asof = date.fromisoformat(asof)
    rules = (assumption_set or {}).get('rules', [])
    base_currency = (assumption_set or {}).get('base_currency', 'JOD')
    adjustments = []
    capacity_events = []
    capacity_audit_flows = []
    behavioural_undated = []
    behavioural_flows = []

    by_contract = defaultdict(list)
    for flow in contractual_flows:
        by_contract[flow['contract_id']].append(deepcopy(flow))

    # Dated contractual products: apply hybrid timing adjustments by contract.
    for contract_id, contract_flows in by_contract.items():
        contract_flows.sort(key=lambda f: f['payment_date'])
        template = contract_flows[0]
        currency = template['currency']; quantum = precision[currency]
        group = template.get('liquidity_group', '')
        product = template.get('liquidity_product', '') or template.get('product', '')
        treatment = _treatment_for(treatments, group, product, 'hybrid')

        # Security liquidation is a behavioural capacity event, not a second
        # repayment.  When active, contractual security cash flows are omitted
        # from the behavioural ladder to avoid double counting.
        timing = _match_rule(rules, 'security_liquidation', group, product, currency, base_currency)
        if timing and treatment != 'contractual' and timing.get('value', {}).get('timing') != 'contractual':
            haircut = _match_rule(rules, 'security_haircut', group, product, currency, base_currency)
            timing_code = timing.get('value', {}).get('timing', '1d')
            days = {'1d': 1, '1w': 7, '1w2w': 14, '1m': 30, '1y': 365}.get(timing_code, 1)
            balance = sum((_decimal(f.get('principal')) for f in contract_flows), D(0))
            haircut_rate = min(D(1), max(D(0), _decimal((haircut or {}).get('value', {}).get('haircut'))))
            amount = (balance * (D(1) - haircut_rate)).quantize(quantum, rounding=ROUND_HALF_UP)
            capacity_events.append({
                'contract_id': contract_id, 'currency': currency, 'liquidity_product': product,
                'liquidity_group': group, 'days_from_asof': days, 'amount': str(amount),
                'balance': str(balance.quantize(quantum)), 'behavioral_source': 'security_liquidation',
                'behavioral_rule_id': timing.get('id'), 'behavioral_rule_title': timing.get('title', ''),
                'haircut': str(haircut_rate),
            })
            audit_event = _event(template, asof, days, amount, quantum, 'security_liquidation', timing)
            audit_event['behavioral_rule_title'] = f"{timing.get('title','Security liquidation')} · haircut {(haircut_rate * D(100)).quantize(D('0.01'))}%"
            capacity_audit_flows.append(audit_event)
            adjustments.append({'contract_id': contract_id, 'category': 'security_liquidation', 'amount': str(amount), 'currency': currency, 'rule': timing.get('title', '')})
            continue

        current = contract_flows
        if treatment != 'contractual' and template.get('product') == 'loan':
            rule = _match_rule(rules, 'loan_prepayment', group, product, currency, base_currency)
            if rule:
                current, _events, amount = _shift_principal_earlier(current, asof, rule, quantum, 'loan_prepayment')
                if amount:
                    adjustments.append({'contract_id': contract_id, 'category': 'loan_prepayment', 'amount': str(amount.quantize(quantum)), 'currency': currency, 'rule': rule.get('title', '')})

        if treatment != 'contractual' and template.get('product') == 'term_deposit':
            rule = _match_rule(rules, 'term_deposit_early_withdrawal', group, product, currency, base_currency)
            if rule:
                current, _events, amount = _shift_principal_earlier(current, asof, rule, quantum, 'term_deposit_early_withdrawal')
                if amount:
                    adjustments.append({'contract_id': contract_id, 'category': 'term_deposit_early_withdrawal', 'amount': str(amount.quantize(quantum)), 'currency': currency, 'rule': rule.get('title', '')})
            rollover = _match_rule(rules, 'term_deposit_rollover', group, product, currency, base_currency)
            if rollover:
                current, _events, amount = _apply_rollover(current, asof, rollover, quantum)
                if amount:
                    adjustments.append({'contract_id': contract_id, 'category': 'term_deposit_rollover', 'amount': str(amount.quantize(quantum)), 'currency': currency, 'rule': rollover.get('title', '')})

        behavioural_flows.extend(current)

    # Open-maturity products: deposit runoff creates actual behavioural events.
    for item in undated:
        currency = item['currency']; quantum = precision[currency]
        group = item.get('liquidity_group', '') or 'Retail Call'
        product = item.get('liquidity_product', '') or item.get('product', '')
        treatment = _treatment_for(treatments, group, product, 'behavioral' if item.get('product') == 'demand_deposit' else 'contractual')
        rule = _match_rule(rules, 'deposit_runoff', group, product, currency, base_currency) if treatment != 'contractual' and item.get('product') == 'demand_deposit' else None
        if not rule:
            behavioural_undated.append(deepcopy(item))
            continue
        balance = _decimal(item['balance']); remaining = balance; generated = D(0)
        template = {
            'contract_id': item['contract_id'], 'product': item['product'], 'currency': currency,
            'direction': item.get('direction', 'outflow'), 'liquidity_product': item.get('liquidity_product', ''),
            'liquidity_group': item.get('liquidity_group', ''),
        }
        for days, increase, _cumulative in _curve_increments(rule):
            amount = min(remaining, (balance * increase).quantize(quantum, rounding=ROUND_HALF_UP))
            if amount <= 0:
                continue
            remaining -= amount; generated += amount
            behavioural_flows.append(_event(template, asof, days, amount, quantum, 'deposit_runoff', rule, remaining))
        if remaining > 0:
            residual = deepcopy(item)
            residual['balance'] = str(remaining.quantize(quantum))
            residual['reason'] = 'Behavioural residual/core balance not assigned to a runoff date'
            residual['behavioral_residual'] = True
            residual['behavioral_rule_id'] = rule.get('id')
            residual['behavioral_rule_title'] = rule.get('title', '')
            behavioural_undated.append(residual)
        adjustments.append({'contract_id': item['contract_id'], 'category': 'deposit_runoff', 'amount': str(generated.quantize(quantum)), 'residual': str(remaining.quantize(quantum)), 'currency': currency, 'rule': rule.get('title', '')})

    behavioural_flows.sort(key=lambda f: (f['currency'], f['payment_date'], f['contract_id']))
    counts = defaultdict(int)
    for item in adjustments:
        counts[item['category']] += 1
    audit_flows = sorted(behavioural_flows + capacity_audit_flows, key=lambda f: (f['currency'], f['payment_date'], f['contract_id']))
    return {
        'flows': behavioural_flows,
        'audit_flows': audit_flows,
        'undated': behavioural_undated,
        'capacity_events': capacity_events,
        'adjustments': adjustments,
        'stats': {
            'cashflow_count': len(audit_flows),
            'reporting_cashflow_count': len(behavioural_flows),
            'capacity_event_count': len(capacity_audit_flows),
            'adjusted_contracts': len({a['contract_id'] for a in adjustments}),
            'adjustment_counts': dict(counts),
            'assumption_set': (assumption_set or {}).get('name'),
            'version': (assumption_set or {}).get('version'),
            'interest_treatment': 'Contractual interest retained; v1 behavioural adjustments change principal timing only.',
        },
    }
