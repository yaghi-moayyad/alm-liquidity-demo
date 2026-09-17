"""Bank-format contractual liquidity ladder.

The stable codes here deliberately separate the calculation/reporting contract from
spreadsheet labels.  Bank source mappings can later target these codes directly.
"""
from decimal import Decimal

D = Decimal

BANK_BUCKETS = [
    ('open_maturity', 'Open maturity', None), ('overnight', 'Overnight', 1),
    ('1w', '1w', 7), ('2w', '2w', 14), ('3w', '3w', 21), ('1m', '1m', 30),
    ('2m', '2m', 60), ('3m', '3m', 90), ('4m', '4m', 120), ('5m', '5m', 150),
    ('6m', '6m', 180), ('9m', '9m', 270), ('1y', '1y', 365), ('2y', '2y', 730),
    ('3y', '3y', 1095), ('4y', '4y', 1460), ('5y', '5y', 1825), ('gt_5y', '>5y', 36500),
]

# Interim prototype mapping.  Raw bank datasets will replace this with explicit
# source/GL/product rules, including direction and counterbalancing designation.
PRODUCT_LINES = {
    ('inflow', 'loan'): 'retail_time_in',
    ('inflow', 'bond'): 'non_marketable_securities',
    ('inflow', 'interbank_asset'): 'other_bank_time_in',
    ('outflow', 'term_deposit'): 'retail_time_out',
    ('outflow', 'borrowing'): 'borrowed_funds',
    ('outflow', 'demand_deposit'): 'retail_call_out',
    ('inflow', 'cash_central_bank'): 'cash_central_bank',
}

ROW_SPEC = [
    ('inflows', 'non_marketable_securities', "Non-marketable Securities & CDs", 'normal'),
    ('inflows', 'retail_call_in', 'Retail Call', 'normal'), ('inflows', 'retail_time_in', 'Retail Time', 'normal'),
    ('inflows', 'intergroup_call_in', 'Intergroup Call', 'normal'), ('inflows', 'intergroup_time_in', 'Intergroup Time', 'normal'),
    ('inflows', 'other_bank_call_in', 'Other Bank Call', 'normal'), ('inflows', 'other_bank_time_in', 'Other Bank Time', 'normal'),
    ('inflows', 'corporate_call_in', 'Corporate Call', 'normal'), ('inflows', 'corporate_time_in', 'Corporate Time', 'normal'),
    ('inflows', 'other_loans', 'Other Loans', 'normal'), ('inflows', 'other_assets_illiquid', 'Other Assets (Illiquid)', 'normal'),
    ('inflows', 'total_inflows', 'Total inflows', 'subtotal'),
    ('outflows', 'repo', 'Repo', 'normal'), ('outflows', 'retail_call_out', 'Retail Call', 'normal'),
    ('outflows', 'retail_time_out', 'Retail Time', 'normal'), ('outflows', 'intergroup_call_out', 'Intergroup Call', 'normal'),
    ('outflows', 'intergroup_time_out', 'Intergroup Time', 'normal'), ('outflows', 'other_bank_call_out', 'Other Bank Call', 'normal'),
    ('outflows', 'other_bank_time_out', 'Other Bank Time', 'normal'), ('outflows', 'corporate_call_out', 'Corporate Call', 'normal'),
    ('outflows', 'corporate_time_out', 'Corporate Time', 'normal'), ('outflows', 'government', 'Government', 'normal'),
    ('outflows', 'borrowed_funds', 'Borrowed Funds', 'normal'), ('outflows', 'other_liabilities_illiquid', 'Other Liabilities (Illiquid)', 'normal'),
    ('outflows', 'total_outflows', 'Total outflows', 'subtotal'),
    ('off_balance_sheet', 'ir_derivatives', 'IR derivatives', 'normal'), ('off_balance_sheet', 'fx_derivatives', 'FX derivatives', 'normal'),
    ('off_balance_sheet', 'undrawn_commitment', 'Undrawn Commitment', 'normal'), ('off_balance_sheet', 'undrawn_uncommitted', 'Undrawn Uncommitted', 'normal'),
    ('off_balance_sheet', 'trade_finance', 'Trade Finance', 'normal'), ('off_balance_sheet', 'total_off_balance_sheet', 'Total off-balance-sheet', 'subtotal'),
    ('gap', 'contractual_gap', 'Contractual Gap', 'gap'), ('gap', 'cumulative_contractual_gap', 'Cumulative Contractual Gap', 'cumulative'),
    ('counterbalancing_capacity', 'cash_central_bank', 'Cash & central bank exposures', 'normal'),
    ('counterbalancing_capacity', 'marketable_securities', 'Marketable securities & CDs', 'normal'),
    ('counterbalancing_capacity', 'government_capacity', 'Government', 'normal'),
    ('counterbalancing_capacity', 'total_counterbalancing_capacity', 'Total counterbalancing capacity', 'subtotal'),
    ('gap', 'contractual_gap_including_capacity', 'Contractual Gap including Counterbalancing Capacity', 'gap'),
    ('gap', 'cumulative_gap_including_capacity', 'Cumulative Contractual Gap including Counterbalancing Capacity', 'cumulative'),
]

def bucket_code(days):
    for code, _label, upper in BANK_BUCKETS[1:]:
        if days <= upper:
            return code
    return 'gt_5y'

def _zeroes():
    return {
        'principal': [D(0)] * len(BANK_BUCKETS),
        'interest': [D(0)] * len(BANK_BUCKETS),
        # The position outstanding at the reporting date.  This deliberately
        # excludes interest, even when the ladder is displayed in total mode.
        'balance': D(0),
    }
def _add(left, right): return [a + b for a, b in zip(left, right)]
def _minus(left, right): return [a - b for a, b in zip(left, right)]

def build_bank_ladder(flows, undated, currency, precision, behavioral=None):
    """Return a horizontal ladder; optional rules create a behavioural view.

    The engine receives a rule snapshot, rather than reading the database, so a
    completed run remains reproducible after an analyst changes an assumption.
    """
    data = {key: _zeroes() for _section, key, _label, _kind in ROW_SPEC}
    details = {}
    bucket_index = {code: i for i, (code, _label, _upper) in enumerate(BANK_BUCKETS)}

    def add_detail(key, product, balance=D(0), principal=None, interest=None):
        product = product or 'Unclassified'
        item = details.setdefault((key, product), _zeroes())
        item['balance'] += balance
        if principal:
            for index, value in principal.items(): item['principal'][index] += value
        if interest:
            for index, value in interest.items(): item['interest'][index] += value

    rules = (behavioral or {}).get('rules', []) if behavioral else []
    treatments = (behavioral or {}).get('product_treatments', []) if behavioral else []
    def find_rule(category, group, product, scope='ALL'):
        for rule in rules:
            if not rule.get('enabled', True) or rule.get('category') != category: continue
            if rule.get('product_group') != group: continue
            if rule.get('product_type') not in ('', 'ALL', product): continue
            if rule.get('currency_scope', 'ALL') not in ('ALL', scope): continue
            return rule
        return None

    def treatment_for(group, product):
        for item in treatments:
            if item.get('product_group') == group and item.get('product_type') == product:
                return item.get('treatment', 'contractual')
        # Runs produced before the product-treatment catalogue was introduced
        # already carry behavioural rules. Keep those saved runs reproducible;
        # new runs always contain an explicit catalogue snapshot.
        return 'behavioral' if not treatments else 'contractual'

    base_currency = (behavioral or {}).get('base_currency', 'JOD')
    security_principal = {}
    for flow in flows:
        if flow['currency'] != currency: continue
        if behavioral and flow.get('liquidity_group') == 'Marketable Securities & CDs' and treatment_for(flow.get('liquidity_group'), flow.get('liquidity_product') or 'Tbond') in ('behavioral','hybrid'):
            security_principal[flow['contract_id']] = security_principal.get(flow['contract_id'], D(0)) + D(flow['principal'])
            continue
        key = PRODUCT_LINES.get((flow['direction'], flow['product']))
        if not key: continue
        index = bucket_index[bucket_code(flow['days_from_asof'])]
        data[key]['principal'][index] += D(flow['principal'])
        data[key]['interest'][index] += D(flow['interest'])
        data[key]['balance'] += D(flow['principal'])
        add_detail(key, flow.get('liquidity_product') or flow['product'], D(flow['principal']), {index:D(flow['principal'])}, {index:D(flow['interest'])})
    for item in undated:
        if item['currency'] != currency: continue
        key = PRODUCT_LINES.get((item.get('direction', 'outflow'), item.get('product', 'demand_deposit')))
        if behavioral and item.get('product') == 'demand_deposit':
            group = item.get('liquidity_group') or 'Retail Call'
            product = item.get('liquidity_product') or 'CurrentAccount'
            scope = 'LCY' if currency == base_currency else 'FCY'
            rule = find_rule('deposit_runoff', group, product, scope)
            if rule and key and treatment_for(group, product) in ('behavioral','hybrid'):
                balance = D(item['balance']); data[key]['balance'] += balance
                increments = {}; prior = D(0)
                for point in sorted(rule.get('value', {}).get('curve', []), key=lambda p: int(p.get('days', 0))):
                    current = D(str(point.get('cumulative', 0)))
                    increase = max(D(0), current - prior); prior = max(prior, current)
                    if increase:
                        index = bucket_index[bucket_code(int(point['days']))]
                        amount = balance * increase
                        data[key]['principal'][index] += amount
                        increments[index] = increments.get(index, D(0)) + amount
                add_detail(key, product, balance, increments)
                continue
        if key:
            data[key]['principal'][0] += D(item['balance'])
            data[key]['balance'] += D(item['balance'])
            add_detail(key, item.get('liquidity_product') or item.get('product'), D(item['balance']), {0:D(item['balance'])})

    # Marketable security liquidation is an additional behavioural capacity. It
    # uses principal only and applies the approved haircut before the selected
    # liquidation timing. Contractual coupons remain visible only in the
    # contractual view, avoiding an invented behavioural interest projection.
    if behavioral:
        by_contract = {f['contract_id']: f for f in flows if f['currency'] == currency}
        for contract_id, balance in security_principal.items():
            flow = by_contract[contract_id]; product = flow.get('liquidity_product') or 'Tbond'
            timing = find_rule('security_liquidation', 'Marketable Securities & CDs', product)
            haircut = find_rule('security_haircut', 'Marketable Securities & CDs', product)
            if not timing: continue
            code = timing.get('value', {}).get('timing', '1d')
            days = {'1d':1, '1w':7, '1w2w':14, '1m':30, '1y':365}.get(code, 1)
            amount = balance * (D(1) - D(str((haircut or {}).get('value', {}).get('haircut', 0))))
            index = bucket_index[bucket_code(days)]
            data['marketable_securities']['balance'] += balance
            data['marketable_securities']['principal'][index] += amount
            add_detail('marketable_securities', product, balance, {index:amount})

    def sum_rows(keys, field):
        return [sum((data[key][field][i] for key in keys), D(0)) for i in range(len(BANK_BUCKETS))]
    inflow_keys = [key for section,key,_label,kind in ROW_SPEC if section == 'inflows' and kind == 'normal']
    outflow_keys = [key for section,key,_label,kind in ROW_SPEC if section == 'outflows' and kind == 'normal']
    obs_keys = [key for section,key,_label,kind in ROW_SPEC if section == 'off_balance_sheet' and kind == 'normal']
    for field in ('principal', 'interest'):
        data['total_inflows'][field] = sum_rows(inflow_keys, field)
        data['total_outflows'][field] = sum_rows(outflow_keys, field)
        data['total_off_balance_sheet'][field] = sum_rows(obs_keys, field)
        data['total_counterbalancing_capacity'][field] = sum_rows(['cash_central_bank','marketable_securities','government_capacity'], field)
        data['contractual_gap'][field] = _minus(data['total_inflows'][field], _add(data['total_outflows'][field], data['total_off_balance_sheet'][field]))
        data['contractual_gap_including_capacity'][field] = _add(data['contractual_gap'][field], data['total_counterbalancing_capacity'][field])
        cumulative = D(0); included = D(0); cumulatives=[]; includeds=[]
        for gap, capacity_gap in zip(data['contractual_gap'][field], data['contractual_gap_including_capacity'][field]):
            cumulative += gap; included += capacity_gap; cumulatives.append(cumulative); includeds.append(included)
        data['cumulative_contractual_gap'][field] = cumulatives
        data['cumulative_gap_including_capacity'][field] = includeds

    def sum_balances(keys):
        return sum((data[key]['balance'] for key in keys), D(0))

    data['total_inflows']['balance'] = sum_balances(inflow_keys)
    data['total_outflows']['balance'] = sum_balances(outflow_keys)
    data['total_off_balance_sheet']['balance'] = sum_balances(obs_keys)
    data['total_counterbalancing_capacity']['balance'] = sum_balances(
        ['cash_central_bank', 'marketable_securities', 'government_capacity']
    )
    data['contractual_gap']['balance'] = (
        data['total_inflows']['balance'] - data['total_outflows']['balance']
        - data['total_off_balance_sheet']['balance']
    )
    data['contractual_gap_including_capacity']['balance'] = (
        data['contractual_gap']['balance'] + data['total_counterbalancing_capacity']['balance']
    )
    # The balance column is an as-of-date position, so a cumulative balance is
    # the cumulative contractual position across the report sections, not an
    # interest-bearing future value.
    data['cumulative_contractual_gap']['balance'] = data['contractual_gap']['balance']
    data['cumulative_gap_including_capacity']['balance'] = data['contractual_gap_including_capacity']['balance']

    rows=[]
    for section,key,label,kind in ROW_SPEC:
        principal=data[key]['principal']; interest=data[key]['interest']
        children=[]
        for (detail_key, product), item in sorted(details.items()):
            if detail_key != key: continue
            dp=item['principal']; di=item['interest']
            children.append({'key': f'{key}:{product}', 'label': product.replace('_', ' '),
                'balance':str(item['balance'].quantize(precision)),
                'principal':[str(v.quantize(precision)) for v in dp],
                'interest':[str(v.quantize(precision)) for v in di],
                'total':[str((p+i).quantize(precision)) for p,i in zip(dp,di)]})
        rows.append({'section':section,'key':key,'label':label,'kind':kind,
            'balance':str(data[key]['balance'].quantize(precision)),
            'principal':[str(v.quantize(precision)) for v in principal],
            'interest':[str(v.quantize(precision)) for v in interest],
            'total':[str((p+i).quantize(precision)) for p,i in zip(principal,interest)], 'children':children})
    return {'buckets':[{'code':code,'label':label} for code,label,_upper in BANK_BUCKETS], 'rows':rows}
