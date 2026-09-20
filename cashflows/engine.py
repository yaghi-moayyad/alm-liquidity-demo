"""Contractual liquidity prototype. Framework-independent, decimal arithmetic."""
from datetime import date, timedelta
from calendar import monthrange
from decimal import Decimal, localcontext, ROUND_HALF_UP
import re

VERSION = '0.7.0'
MAX_CONTRACTS = 2000
MAX_PERIODS = 1200
D = Decimal
PRODUCTS = {'loan': 'inflow', 'bond': 'inflow', 'interbank_asset': 'inflow', 'cash_central_bank': 'inflow',
            'term_deposit': 'outflow', 'borrowing': 'outflow', 'demand_deposit': 'outflow'}
PRECISION = {'JOD': D('.001'), 'USD': D('.01'), 'EUR': D('.01'), 'GBP': D('.01')}
DEFAULT_BUCKETS = [1, 7, 14, 30, 60, 90, 180, 270, 365, 730, 1095, 1825]
REQUIRED = {'contract_id', 'product', 'currency', 'principal'}
OPTIONAL = {'annual_rate', 'rate_type', 'repayment', 'day_count', 'frequency_months',
            'accrual_start', 'next_payment', 'maturity', 'end_of_month', 'status',
            'interest_rate_index', 'client_rate_spread', 'rate_cap', 'rate_floor',
            'liquidity_product', 'liquidity_group', 'counterparty', 'counterparty_group',
            'funding_source', 'liquidity_buffer_class', 'encumbered', 'liquidity_haircut'}


def decimal(value, name):
    try:
        v = D(str(value))
    except Exception:
        raise ValueError(f'{name} must be a finite number')
    if not v.is_finite():
        raise ValueError(f'{name} must be a finite number')
    return v


def parse_date(value, name):
    try:
        return date.fromisoformat(value)
    except Exception:
        raise ValueError(f'{name} must be an ISO date (YYYY-MM-DD)')


def add_months(anchor, months, eom=False):
    m = anchor.year * 12 + anchor.month - 1 + months
    y, mo = divmod(m, 12)
    mo += 1
    last = monthrange(y, mo)[1]
    return date(y, mo, last if eom else min(anchor.day, last))


def year_fraction(start, end, convention):
    if convention == 'ACT/360':
        return D((end - start).days) / D(360)
    if convention == 'ACT/365F':
        return D((end - start).days) / D(365)
    if convention == '30E/360':
        return D(360 * (end.year - start.year) + 30 * (end.month - start.month)
                 + min(end.day, 30) - min(start.day, 30)) / D(360)
    raise ValueError('day_count must be ACT/360, ACT/365F or 30E/360')


def validate_config(payload):
    if not isinstance(payload, dict):
        raise ValueError('Request must be a JSON object')
    unknown = set(payload) - {'as_of_date', 'entity', 'bucket_days', 'contracts', 'interest_projection', 'forward_curve', 'calculation_basis', 'behavioral_assumption_set', 'product_treatments'}
    if unknown:
        raise ValueError('Unknown request fields: ' + ', '.join(sorted(unknown)))
    asof = parse_date(payload.get('as_of_date'), 'as_of_date')
    entity = payload.get('entity', 'Jordan')
    if not isinstance(entity, str) or not entity.strip() or len(entity) > 64:
        raise ValueError('entity must be a nonempty code of at most 64 characters')
    buckets = payload.get('bucket_days', DEFAULT_BUCKETS)
    if (not isinstance(buckets, list) or not 1 <= len(buckets) <= 30
            or any(type(x) is not int or not 1 <= x <= 36500 for x in buckets)
            or buckets != sorted(set(buckets))):
        raise ValueError('bucket_days must be 1–30 strictly increasing positive integer day boundaries (maximum 36500)')
    contracts = payload.get('contracts')
    if not isinstance(contracts, list) or not 1 <= len(contracts) <= MAX_CONTRACTS:
        raise ValueError(f'Provide between 1 and {MAX_CONTRACTS} contracts')
    return asof, entity, buckets, contracts


def projected_rate(contract, payment_date, asof, settings):
    """Return the contractual all-in annual rate for a payment period."""
    current = decimal(contract['annual_rate'], 'annual_rate')
    if contract.get('rate_type', 'fixed') == 'fixed' or settings.get('interest_projection', 'constant') == 'constant':
        return current
    index = contract.get('interest_rate_index')
    if not index:
        raise ValueError('Floating-rate contract needs interest_rate_index when using a forward curve')
    points = [p for p in settings.get('forward_curve', []) if isinstance(p, dict) and p.get('currency') == contract['currency'] and p.get('index') == index]
    if not points:
        raise ValueError(f'No forward-curve points for {contract["currency"]} {index}')
    try:
        points = sorted(points, key=lambda p: int(p['tenor_days']))
        point = next((p for p in points if int(p['tenor_days']) >= (payment_date-asof).days), points[-1])
        rate = decimal(point['rate'], 'forward_curve rate') + decimal(contract.get('client_rate_spread', 0), 'client_rate_spread')
    except (KeyError, TypeError, ValueError):
        raise ValueError('Forward-curve points need valid tenor_days and rate values')
    if 'rate_floor' in contract: rate=max(rate, decimal(contract['rate_floor'], 'rate_floor'))
    if 'rate_cap' in contract: rate=min(rate, decimal(contract['rate_cap'], 'rate_cap'))
    if not D(0) <= rate <= D(1): raise ValueError('Projected floating rate must be between 0 and 1')
    return rate


def schedule(contract, asof, settings=None):
    settings_provided = settings is not None
    settings = settings or {}
    if not isinstance(contract, dict):
        raise ValueError('Contract must be an object')
    missing = REQUIRED - set(contract)
    if missing:
        raise ValueError('Missing fields: ' + ', '.join(sorted(missing)))
    unknown = set(contract) - REQUIRED - OPTIONAL
    if unknown:
        raise ValueError('Unsupported fields (not silently applied): ' + ', '.join(sorted(unknown)))
    cid = contract['contract_id']
    if not isinstance(cid, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', cid):
        raise ValueError('contract_id must be 1–64 letters, numbers, underscores, dots or hyphens')
    product = contract['product']
    if not isinstance(product, str) or product not in PRODUCTS:
        raise ValueError('Unsupported product; see the supported product list')
    currency = contract['currency']
    if not isinstance(currency, str) or currency not in PRECISION:
        raise ValueError('Supported currencies: JOD, USD, EUR, GBP')
    quantum = PRECISION[currency]
    principal = decimal(contract['principal'], 'principal')
    if not D(0) < principal <= D('1000000000000'):
        raise ValueError('principal must be positive and no more than 1 trillion')
    if principal != principal.quantize(quantum):
        raise ValueError(f'principal must respect the {currency} currency precision {quantum}')
    if contract.get('status', 'performing') != 'performing':
        raise ValueError('Overdue/defaulted contracts require separate rules and are not supported yet')
    if contract.get('rate_type', 'fixed') not in ('fixed', 'floating'):
        raise ValueError('rate_type must be fixed or floating')
    if contract.get('rate_type', 'fixed') == 'floating' and (not settings_provided or 'interest_projection' not in settings):
        raise ValueError('Floating rates require an agreed projection convention')
    base = {'contract_id': cid, 'product': product, 'currency': currency,
            'direction': PRODUCTS[product], 'principal': str(principal.quantize(quantum))}
    if contract.get('liquidity_product'):
        base['liquidity_product'] = str(contract['liquidity_product'])
    if contract.get('liquidity_group'):
        base['liquidity_group'] = str(contract['liquidity_group'])
    for field in ('counterparty', 'counterparty_group', 'funding_source', 'liquidity_buffer_class'):
        if contract.get(field): base[field] = str(contract[field])
    if 'encumbered' in contract:
        if type(contract['encumbered']) is not bool: raise ValueError('encumbered must be true or false')
        base['encumbered'] = contract['encumbered']
    if 'liquidity_haircut' in contract:
        haircut = decimal(contract['liquidity_haircut'], 'liquidity_haircut')
        if not D(0) <= haircut <= D(1): raise ValueError('liquidity_haircut must be between 0 and 1')
        base['liquidity_haircut'] = str(haircut)
    if product in ('demand_deposit', 'cash_central_bank'):
        if set(contract) & {'annual_rate', 'repayment', 'day_count', 'frequency_months',
                            'accrual_start', 'next_payment', 'maturity', 'end_of_month'}:
            raise ValueError('Undated demand deposits accept balance fields only; dated terms need separate rules')
        if product == 'demand_deposit':
            return base, [], {'contract_id': cid, 'product': product, 'direction': base['direction'], 'currency': currency, 'balance': base['principal'], 'liquidity_product': base.get('liquidity_product', ''), 'liquidity_group': base.get('liquidity_group', ''),
                              'reason': 'Open maturity: separately disclosed; no invented withdrawal date or interest schedule'}
        return base, [], {'contract_id': cid, 'product': product, 'direction': base['direction'], 'currency': currency, 'balance': base['principal'], 'liquidity_product': base.get('liquidity_product', ''), 'liquidity_group': base.get('liquidity_group', ''),
                          'reason': 'Cash and central-bank position: separately disclosed as counterbalancing capacity'}
    needed = {'annual_rate', 'repayment', 'day_count', 'frequency_months', 'accrual_start', 'next_payment', 'maturity'}
    if needed - set(contract):
        raise ValueError('Missing schedule terms: ' + ', '.join(sorted(needed - set(contract))))
    rate = decimal(contract['annual_rate'], 'annual_rate')
    if not D(0) <= rate <= D(1):
        raise ValueError('annual_rate must be between 0 and 1 (0.06 = 6%)')
    method = contract['repayment']
    if method not in ('bullet', 'equal_principal', 'level_payment'):
        raise ValueError('repayment must be bullet, equal_principal or level_payment')
    if product in ('term_deposit', 'bond') and method != 'bullet':
        raise ValueError('This prototype supports bullet principal for term deposits and bonds')
    freq = contract['frequency_months']
    if type(freq) is not int or freq not in (1, 3, 6, 12):
        raise ValueError('frequency_months must be 1, 3, 6 or 12')
    eom = contract.get('end_of_month', False)
    if type(eom) is not bool:
        raise ValueError('end_of_month must be true or false')
    start = parse_date(contract['accrual_start'], 'accrual_start')
    nxt = parse_date(contract['next_payment'], 'next_payment')
    maturity = parse_date(contract['maturity'], 'maturity')
    if not start <= asof < nxt <= maturity:
        raise ValueError('Require accrual_start ≤ reporting date < next_payment ≤ maturity')
    if (nxt-start).days > 370:
        raise ValueError('First accrual period exceeds 370 days; review accrual_start')
    if (maturity-asof).days > 36525:
        raise ValueError('Maturity exceeds the prototype 100-year limit')
    if eom and nxt.day != monthrange(nxt.year, nxt.month)[1]:
        raise ValueError('next_payment must be month end when end_of_month=true')
    dates, i, current = [], 0, nxt
    while current < maturity:
        dates.append(current)
        i += 1
        if i >= MAX_PERIODS:
            raise ValueError('Schedule exceeds 1200 payments')
        current = add_months(nxt, i * freq, eom)
    dates.append(maturity)
    starts = [start] + dates[:-1]
    factors = [projected_rate(contract, end, asof, settings) * year_fraction(a, end, contract['day_count']) for a, end in zip(starts, dates)]
    # A constant payment that discounts each date using its contractual accrual factor.
    # A final adjustment absorbs currency rounding; initial first period can include accrued interest.
    payment = D(0)
    if method == 'level_payment':
        discount, annuity = D(1), D(0)
        for f in factors:
            discount /= D(1) + f
            annuity += discount
        payment = (principal / annuity).quantize(quantum, rounding=ROUND_HALF_UP)
    equal = (principal / D(len(dates))).quantize(quantum, rounding=ROUND_HALF_UP)
    balance, flows = principal, []
    for j, (end, begin, factor) in enumerate(zip(dates, starts, factors)):
        interest = (balance * factor).quantize(quantum, rounding=ROUND_HALF_UP)
        if j == len(dates) - 1:
            repay = balance
        elif method == 'bullet':
            repay = D(0)
        elif method == 'equal_principal':
            repay = min(balance, equal)
        else:
            repay = min(balance, payment - interest)
            if repay < 0:
                raise ValueError('Level payment causes negative amortization; unsupported')
        balance -= repay
        flows.append({'contract_id': cid, 'product': product, 'currency': currency,
                      'direction': base['direction'], 'payment_date': end.isoformat(),
                      'accrual_start': begin.isoformat(), 'accrual_end': end.isoformat(),
                      'days_from_asof': (end - asof).days,
                      'principal': str(repay.quantize(quantum)), 'interest': str(interest),
                      'total': str((repay + interest).quantize(quantum)),
                      'remaining_principal': str(balance.quantize(quantum)),
                      'liquidity_product': base.get('liquidity_product', ''),
                      'liquidity_group': base.get('liquidity_group', '')})
    base.update({'repayment': method, 'day_count': contract['day_count'], 'payments': len(flows),
                 'principal_check': sum(D(f['principal']) for f in flows) == principal,
                 'total_interest': str(sum((D(f['interest']) for f in flows), D(0)).quantize(quantum))})
    return base, flows, None


def calculate(payload, progress=None):
    asof, entity, buckets, contracts = validate_config(payload)
    with localcontext() as ctx:
        ctx.prec = 40
        accepted, flows, exceptions, undated = [], [], [], []
        ids = [c.get('contract_id') for c in contracts if isinstance(c, dict) and isinstance(c.get('contract_id'), str)]
        from collections import Counter
        duplicates = {k for k,v in Counter(ids).items() if v > 1}
        for index, contract in enumerate(contracts):
            try:
                cid = contract.get('contract_id') if isinstance(contract, dict) else None
                if isinstance(cid, str) and cid in duplicates:
                    raise ValueError('Duplicate contract_id; all occurrences excluded')
                base, generated, open_item = schedule(contract, asof, payload)
                accepted.append(base)
                flows.extend(generated)
                if open_item:
                    undated.append(open_item)
            except (ValueError, TypeError, OverflowError, ArithmeticError) as exc:
                exceptions.append({'row': index + 1, 'contract_id': str(contract.get('contract_id', '?')) if isinstance(contract,dict) else '?',
                                   'error': str(exc) or 'Invalid contract terms'})
            if progress and ((index+1) % 25 == 0 or index+1 == len(contracts)):
                progress(index+1, len(contracts))
        def build_summary(summary_flows):
            labels = []
            lower = 1
            for upper in buckets:
                labels.append(f'{upper} day' if lower == upper else f'{lower}–{upper} days')
                lower = upper + 1
            labels.append(f'>{buckets[-1]} days')
            result = {}
            summary_currencies = sorted({c['currency'] for c in accepted} | {f['currency'] for f in summary_flows})
            for cur in summary_currencies:
                result[cur] = [{'bucket': label, 'inflow_principal':D(0), 'inflow_interest':D(0),
                    'outflow_principal':D(0), 'outflow_interest':D(0)} for label in labels]
            for f in summary_flows:
                k = next((i for i, upper in enumerate(buckets) if f['days_from_asof'] <= upper), len(buckets))
                f['bucket'] = labels[k]
                row = result[f['currency']][k]
                row[f['direction']+'_principal'] += D(f['principal'])
                row[f['direction']+'_interest'] += D(f['interest'])
            for cur, rows in result.items():
                cumulative = D(0)
                for row in rows:
                    row['inflows'] = row['inflow_principal'] + row['inflow_interest']
                    row['outflows'] = row['outflow_principal'] + row['outflow_interest']
                    row['net_gap'] = row['inflows'] - row['outflows']
                    cumulative += row['net_gap']
                    row['cumulative_gap'] = cumulative
                    for key, val in list(row.items()):
                        if isinstance(val, D): row[key] = str(val.quantize(PRECISION[cur]))
            return result

        summaries = build_summary(flows)
        currencies = sorted({c['currency'] for c in accepted})
        controls = []
        for cur in currencies:
            scheduled = sum((D(c['principal']) for c in accepted if c['currency']==cur and c['product'] not in ('demand_deposit','cash_central_bank')),D(0))
            generated = sum((D(f['principal']) for f in flows if f['currency']==cur),D(0))
            open_total = sum((D(u['balance']) for u in undated if u['currency']==cur and u.get('product') == 'demand_deposit'),D(0))
            controls.append({'currency':cur,'scheduled_balance':str(scheduled.quantize(PRECISION[cur])),
                'generated_principal':str(generated.quantize(PRECISION[cur])),
                'difference':str((scheduled-generated).quantize(PRECISION[cur])),
                'undated_balance':str(open_total.quantize(PRECISION[cur])), 'passed':scheduled==generated})

        from .reporting import build_bank_ladder
        bank_ladder = {cur: build_bank_ladder(flows, undated, cur, PRECISION[cur], basis='contractual') for cur in currencies}
        behavioural = payload.get('behavioral_assumption_set')
        basis = payload.get('calculation_basis', 'contractual')
        behavioural_result = None
        behavioural_flows = []
        behavioural_ladder = {}
        behavioural_summary = {}
        if basis == 'behavioral' and behavioural:
            from .behavioral_engine import generate_behavioral_cashflows
            behavioural_result = generate_behavioral_cashflows(
                flows, undated, asof, behavioural, PRECISION,
                treatments=payload.get('product_treatments', []),
            )
            behavioural_reporting_flows = behavioural_result['flows']
            behavioural_flows = behavioural_result.get('audit_flows', behavioural_reporting_flows)
            behavioural_summary = build_summary(behavioural_reporting_flows)
            behavioural_ladder = {
                cur: build_bank_ladder(
                    behavioural_reporting_flows, behavioural_result['undated'], cur, PRECISION[cur],
                    capacity_events=behavioural_result['capacity_events'], basis='behavioral'
                ) for cur in currencies
            }

        projection = payload.get('interest_projection', 'constant')
        behavioural_name = behavioural.get('name', 'saved behavioural assumptions') if behavioural else None
        if basis == 'behavioral' and behavioural_name:
            basis_text = f'Behavioural engine using {behavioural_name}'
        elif basis == 'behavioral':
            basis_text = 'Behavioural basis requested but no active assumption set was available'
        else:
            basis_text = 'Contractual'
        return {'engine_version':VERSION, 'as_of_date':asof.isoformat(),'entity':entity,
                'bucket_days':buckets,'input_count':len(contracts),'accepted_count':len(accepted),
                'rejected_count':len(exceptions),'cashflow_count':len(flows),
                'behavioral_cashflow_count':len(behavioural_flows),
                'currencies':currencies,'contracts':accepted,'cashflows':flows,
                'behavioral_cashflows':behavioural_flows,
                'summary':summaries, 'behavioral_summary':behavioural_summary,
                'exceptions':exceptions,'undated':undated,'controls':controls,'bank_ladder':bank_ladder,
                'behavioral_bank_ladder':behavioural_ladder, 'calculation_basis':basis,
                'behavioral_engine': behavioural_result['stats'] if behavioural_result else None,
                'behavioral_adjustments': behavioural_result['adjustments'] if behavioural_result else [],
                'behavioral_assumption_set': ({k: behavioural[k] for k in ('id','name','version','effective_date','source') if k in behavioural} if behavioural else None),
                'interest_projection':projection,
                'basis':f'{basis_text}; {"market forward curve" if projection == "forward_curve" else "current rates held constant"} for floating-rate interest; original currency; saved input snapshot',
                'status':'failed_validation' if not accepted else ('completed_with_exceptions' if exceptions else 'completed')}
