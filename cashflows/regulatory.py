"""Deterministic LCR/NCR report generated from canonical source positions."""
from decimal import Decimal
from .models import RegulatorySourcePosition

D=Decimal

LINE_SPEC=[
    ('hqla','level1_coins','Coins and banknotes','normal'),
    ('hqla','level1_reserves','Central Bank reserves drawable in stress','normal'),
    ('hqla','level1_sovereign','Securities issued or guaranteed by sovereigns, central banks and PSEs (0% RWA)','normal'),
    ('hqla','total_level1','Total Level 1 Assets','subtotal'),
    ('hqla','level2a_securities','Securities issued or guaranteed by sovereigns, central banks and PSEs (20% RWA)','normal'),
    ('hqla','total_level2a','Total Level 2A Assets','subtotal'),
    ('hqla','level2b_equities','Equities qualified as Level 2B','normal'),
    ('hqla','total_level2b','Total Level 2B Assets','subtotal'),
    ('hqla','level2b_cap','The 15% Cap on Level 2B Assets','adjustment'),
    ('hqla','level2_cap','The 40% Cap on Level 2 Assets','adjustment'),
    ('hqla','total_hqla','Total Stock of HQLA','subtotal'),
    ('outflows','section_retail','a) Retail Deposits','section'),
    ('outflows','retail_stable','Stable Deposits – Retail','normal'),
    ('outflows','retail_less_stable','Less Stable Deposits – Retail','normal'),
    ('outflows','total_retail','Total retail outflows','subtotal'),
    ('outflows','section_wholesale','b) Wholesale Deposits','section'),
    ('outflows','wholesale_operational','Operational deposits','normal'),
    ('outflows','wholesale_non_operational','Non-operational deposits','normal'),
    ('outflows','secured_funding','Secured funding and repo transactions','normal'),
    ('outflows','other_outflows','Other contractual and contingent outflows','normal'),
    ('outflows','total_outflows','Total cash outflows','subtotal'),
    ('inflows','inflow_financial','Inflows from financial institutions','normal'),
    ('inflows','inflow_customer','Inflows from customers and other counterparties','normal'),
    ('inflows','total_inflows','Total cash inflows before cap','subtotal'),
    ('inflows','inflow_cap','75% inflow cap','adjustment'),
    ('inflows','eligible_inflows','Eligible cash inflows','subtotal'),
    ('result','net_cash_outflows','Total net cash outflows','subtotal'),
    ('result','lcr','Liquidity Coverage Ratio','ratio'),
]

def ncr_report(entity):
    positions=RegulatorySourcePosition.objects.filter(entity=entity,active=True)
    values={key:{'exposure':D(0),'weighted':D(0),'factor':None} for _section,key,_label,_kind in LINE_SPEC}
    for p in positions:
        row=values.get(p.lcr_category)
        if row is None: continue
        row['exposure'] += p.balance
        row['weighted'] += p.balance*p.lcr_factor
        row['factor']=p.lcr_factor
    def weighted(*keys): return sum((values[key]['weighted'] for key in keys),D(0))
    def exposure(*keys): return sum((values[key]['exposure'] for key in keys),D(0))
    values['total_level1'].update(exposure=exposure('level1_coins','level1_reserves','level1_sovereign'),weighted=weighted('level1_coins','level1_reserves','level1_sovereign'))
    values['total_level2a'].update(exposure=values['level2a_securities']['exposure'],weighted=values['level2a_securities']['weighted'])
    values['total_level2b'].update(exposure=values['level2b_equities']['exposure'],weighted=values['level2b_equities']['weighted'])
    l1=values['total_level1']['weighted'];l2a=values['total_level2a']['weighted'];l2b=values['total_level2b']['weighted']
    cap2b=max(l2b-D('15')/D('85')*(l1+l2a),l2b-D('15')/D('60')*l1,D(0))
    cap2=max((l2a+l2b-cap2b)-D(2)/D(3)*l1,D(0))
    values['level2b_cap']['weighted']=cap2b; values['level2_cap']['weighted']=cap2
    values['total_hqla']['weighted']=l1+l2a+l2b-cap2b-cap2; values['total_hqla']['exposure']=values['total_hqla']['weighted']
    values['total_retail'].update(exposure=exposure('retail_stable','retail_less_stable'),weighted=weighted('retail_stable','retail_less_stable'))
    values['total_outflows'].update(exposure=exposure('retail_stable','retail_less_stable','wholesale_operational','wholesale_non_operational','secured_funding','other_outflows'),weighted=weighted('retail_stable','retail_less_stable','wholesale_operational','wholesale_non_operational','secured_funding','other_outflows'))
    values['total_inflows'].update(exposure=exposure('inflow_financial','inflow_customer'),weighted=weighted('inflow_financial','inflow_customer'))
    values['inflow_cap']['weighted']=values['total_outflows']['weighted']*D('.75')
    values['eligible_inflows']['weighted']=min(values['total_inflows']['weighted'],values['inflow_cap']['weighted']);values['eligible_inflows']['exposure']=values['eligible_inflows']['weighted']
    values['net_cash_outflows']['weighted']=values['total_outflows']['weighted']-values['eligible_inflows']['weighted'];values['net_cash_outflows']['exposure']=values['net_cash_outflows']['weighted']
    nco=values['net_cash_outflows']['weighted'];values['lcr']['weighted']=values['total_hqla']['weighted']/nco if nco else D(0)
    rows=[]
    for section,key,label,kind in LINE_SPEC:
        value=values[key]
        rows.append({'section':section,'key':key,'label':label,'kind':kind,'factor':None if value['factor'] is None else str(value['factor']),'exposure':str(value['exposure']),'weighted':str(value['weighted'])})
    return {'entity':entity.slug,'entity_name':entity.name,'currency':entity.base_currency,'source_position_count':positions.count(),'rows':rows,'lcr':str(values['lcr']['weighted']),'hqla':str(values['total_hqla']['weighted']),'net_cash_outflows':str(nco),'basis':'Deterministic LCR/NCR calculation from mapped source positions; original currency; mock source data until bank integration.'}
