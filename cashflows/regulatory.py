"""Deterministic regulatory liquidity calculations from mapped source snapshots."""
from decimal import Decimal
from .models import RegulatorySourcePosition, RegulatorySnapshot

D = Decimal
LCR_LINE_SPEC = [
    ('hqla','level1_coins','Coins and banknotes','normal'),('hqla','level1_reserves','Central Bank reserves drawable in stress','normal'),('hqla','level1_sovereign','Securities issued or guaranteed by sovereigns, central banks and PSEs (0% RWA)','normal'),('hqla','total_level1','Total Level 1 Assets','subtotal'),('hqla','level2a_securities','Securities issued or guaranteed by sovereigns, central banks and PSEs (20% RWA)','normal'),('hqla','total_level2a','Total Level 2A Assets','subtotal'),('hqla','level2b_equities','Equities qualified as Level 2B','normal'),('hqla','total_level2b','Total Level 2B Assets','subtotal'),('hqla','level2b_cap','The 15% Cap on Level 2B Assets','adjustment'),('hqla','level2_cap','The 40% Cap on Level 2 Assets','adjustment'),('hqla','total_hqla','Total Stock of HQLA','subtotal'),
    ('outflows','section_retail','a) Retail Deposits','section'),('outflows','retail_stable','Stable Deposits – Retail','normal'),('outflows','retail_less_stable','Less Stable Deposits – Retail','normal'),('outflows','total_retail','Total retail outflows','subtotal'),('outflows','section_wholesale','b) Wholesale Deposits and funding','section'),('outflows','wholesale_operational','Operational deposits','normal'),('outflows','wholesale_non_operational','Non-operational deposits','normal'),('outflows','secured_funding','Secured funding and repo transactions','normal'),('outflows','other_outflows','Other contractual and contingent outflows','normal'),('outflows','total_outflows','Total cash outflows','subtotal'),
    ('inflows','inflow_financial','Inflows from financial institutions','normal'),('inflows','inflow_customer','Inflows from customers and other counterparties','normal'),('inflows','total_inflows','Total cash inflows before cap','subtotal'),('inflows','inflow_cap','75% inflow cap','adjustment'),('inflows','eligible_inflows','Eligible cash inflows','subtotal'),('result','net_cash_outflows','Total net cash outflows','subtotal'),('result','lcr','Liquidity Coverage Ratio','ratio'),
]

def _d(value): return D(str(value or 0))

def lcr_report_from_positions(positions, entity, as_of_date=None, source_count=None, basis=None):
    values={key:{'exposure':D(0),'weighted':D(0),'factor':None} for _section,key,_label,_kind in LCR_LINE_SPEC}
    for position in positions:
        category=position.get('lcr_category') if isinstance(position,dict) else position.lcr_category
        row=values.get(category)
        if row is None: continue
        balance=_d(position.get('balance') if isinstance(position,dict) else position.balance);factor=_d(position.get('lcr_factor') if isinstance(position,dict) else position.lcr_factor)
        row['exposure']+=balance;row['weighted']+=balance*factor;row['factor']=factor
    def weighted(*keys): return sum((values[key]['weighted'] for key in keys),D(0))
    def exposure(*keys): return sum((values[key]['exposure'] for key in keys),D(0))
    values['total_level1'].update(exposure=exposure('level1_coins','level1_reserves','level1_sovereign'),weighted=weighted('level1_coins','level1_reserves','level1_sovereign'))
    values['total_level2a'].update(exposure=values['level2a_securities']['exposure'],weighted=values['level2a_securities']['weighted']);values['total_level2b'].update(exposure=values['level2b_equities']['exposure'],weighted=values['level2b_equities']['weighted'])
    l1=values['total_level1']['weighted'];l2a=values['total_level2a']['weighted'];l2b=values['total_level2b']['weighted'];cap2b=max(l2b-D('15')/D('85')*(l1+l2a),l2b-D('15')/D('60')*l1,D(0));cap2=max((l2a+l2b-cap2b)-D(2)/D(3)*l1,D(0));values['level2b_cap']['weighted']=cap2b;values['level2_cap']['weighted']=cap2;values['total_hqla']['weighted']=l1+l2a+l2b-cap2b-cap2;values['total_hqla']['exposure']=values['total_hqla']['weighted']
    values['total_retail'].update(exposure=exposure('retail_stable','retail_less_stable'),weighted=weighted('retail_stable','retail_less_stable'));outflow_keys=('retail_stable','retail_less_stable','wholesale_operational','wholesale_non_operational','secured_funding','other_outflows');values['total_outflows'].update(exposure=exposure(*outflow_keys),weighted=weighted(*outflow_keys));values['total_inflows'].update(exposure=exposure('inflow_financial','inflow_customer'),weighted=weighted('inflow_financial','inflow_customer'));values['inflow_cap']['weighted']=values['total_outflows']['weighted']*D('.75');values['eligible_inflows']['weighted']=min(values['total_inflows']['weighted'],values['inflow_cap']['weighted']);values['eligible_inflows']['exposure']=values['eligible_inflows']['weighted'];values['net_cash_outflows']['weighted']=values['total_outflows']['weighted']-values['eligible_inflows']['weighted'];values['net_cash_outflows']['exposure']=values['net_cash_outflows']['weighted'];nco=values['net_cash_outflows']['weighted'];values['lcr']['weighted']=values['total_hqla']['weighted']/nco if nco else D(0)
    rows=[]
    for section,key,label,kind in LCR_LINE_SPEC:
        value=values[key];rows.append({'section':section,'key':key,'label':label,'kind':kind,'factor':None if value['factor'] is None else str(value['factor']),'exposure':str(value['exposure']),'weighted':str(value['weighted'])})
    return {'entity':entity.slug,'entity_name':entity.name,'currency':entity.base_currency,'as_of_date':as_of_date.isoformat() if as_of_date else None,'source_position_count':source_count if source_count is not None else len(positions),'rows':rows,'lcr':str(values['lcr']['weighted']),'hqla':str(values['total_hqla']['weighted']),'net_cash_outflows':str(nco),'total_outflows':str(values['total_outflows']['weighted']),'total_inflows':str(values['total_inflows']['weighted']),'eligible_inflows':str(values['eligible_inflows']['weighted']),'basis':basis or 'Deterministic LCR calculation from mapped source positions.'}

def ncr_report(entity):
    positions=RegulatorySourcePosition.objects.filter(entity=entity,active=True)
    return lcr_report_from_positions(list(positions),entity,source_count=positions.count(),basis='Deterministic LCR/NCR calculation from mapped source positions; original currency; mock source data until bank integration.')

def nsfr_report_from_lines(lines, entity, as_of_date=None, basis=None):
    rows=[];asf=D(0);rsf=D(0)
    for line in lines:
        direction=line['direction'];values=[];weighted=D(0);factors=[_d(x) for x in line.get('factors',[0,0,0])]
        for field in ('jod','usd','other'):
            numbers=[_d(x) for x in line.get(field,[0,0,0])];values.append([str(x) for x in numbers]);weighted+=sum((numbers[index]*factors[index] for index in range(3)),D(0))
        if direction=='asf':asf+=weighted
        else:rsf+=weighted
        rows.append({'section':direction,'code':line['code'],'label':line['label'],'jod':values[0],'usd':values[1],'other':values[2],'factors':[str(x) for x in factors],'weighted':str(weighted),'kind':'normal'})
    rows += [{'section':'asf','code':'','label':'Total Available Stable Funding','jod':['','',''],'usd':['','',''],'other':['','',''],'factors':['','',''],'weighted':str(asf),'kind':'subtotal'},{'section':'rsf','code':'','label':'Total Required Stable Funding','jod':['','',''],'usd':['','',''],'other':['','',''],'factors':['','',''],'weighted':str(rsf),'kind':'subtotal'},{'section':'result','code':'','label':'Net Stable Funding Ratio','jod':['','',''],'usd':['','',''],'other':['','',''],'factors':['','',''],'weighted':str(asf/rsf if rsf else D(0)),'kind':'ratio'}]
    return {'entity':entity.slug,'entity_name':entity.name,'currency':entity.base_currency,'as_of_date':as_of_date.isoformat() if as_of_date else None,'rows':rows,'asf':str(asf),'rsf':str(rsf),'nsfr':str(asf/rsf if rsf else D(0)),'basis':basis or 'Deterministic NSFR calculation from mapped source positions.'}

def snapshot_for(entity,as_of=None):
    snapshots=RegulatorySnapshot.objects.filter(entity=entity)
    return snapshots.filter(as_of_date=as_of).first() if as_of else snapshots.first()

def regulatory_report(entity,report_type,as_of=None):
    snapshot=snapshot_for(entity,as_of)
    if snapshot:
        data=snapshot.source_data;basis=f'{snapshot.source}; {"mock source data" if snapshot.is_mock else "mapped source data"}.'
        return lcr_report_from_positions(data.get('lcr_positions',[]),entity,snapshot.as_of_date,basis=basis) if report_type=='lcr' else nsfr_report_from_lines(data.get('nsfr_lines',[]),entity,snapshot.as_of_date,basis=basis)
    return ncr_report(entity) if report_type=='lcr' else nsfr_report_from_lines([],entity,basis='No NSFR source snapshot is available.')

def regulatory_series(entity,report_type):
    output=[]
    for snapshot in RegulatorySnapshot.objects.filter(entity=entity).order_by('as_of_date'):
        report=regulatory_report(entity,report_type,snapshot.as_of_date)
        if report_type=='lcr':output.append({'as_of_date':snapshot.as_of_date.isoformat(),'ratio':report['lcr'],'primary':report['hqla'],'secondary':report['net_cash_outflows']})
        else:output.append({'as_of_date':snapshot.as_of_date.isoformat(),'ratio':report['nsfr'],'primary':report['asf'],'secondary':report['rsf']})
    return output

def regulatory_drivers(entity,report_type,as_of):
    snapshots=list(RegulatorySnapshot.objects.filter(entity=entity,as_of_date__lte=as_of).order_by('-as_of_date')[:2]);current=regulatory_report(entity,report_type,as_of)
    if len(snapshots)<2:return {'comparison_date':None,'drivers':[],'reconciled':True}
    prior=regulatory_report(entity,report_type,snapshots[1].as_of_date)
    if report_type=='lcr':
        old_ratio=_d(prior['lcr']);new_ratio=_d(current['lcr']);old_denominator=_d(prior['net_cash_outflows']);new_numerator=_d(current['hqla']);first='hqla';second='net_cash_outflows';first_label='Change in HQLA';second_label='Change in net cash outflows'
    else:
        old_ratio=_d(prior['nsfr']);new_ratio=_d(current['nsfr']);old_denominator=_d(prior['rsf']);new_numerator=_d(current['asf']);first='asf';second='rsf';first_label='Change in available stable funding';second_label='Change in required stable funding'
    new_denominator=_d(current[second]);numerator_impact=(new_numerator-_d(prior[first]))/old_denominator if old_denominator else D(0);denominator_impact=new_numerator/new_denominator-new_numerator/old_denominator if old_denominator and new_denominator else D(0)
    drivers=[{'label':first_label,'amount':str(new_numerator-_d(prior[first])),'ratio_impact':str(numerator_impact),'detail_key':first},{'label':second_label,'amount':str(_d(current[second])-_d(prior[second])),'ratio_impact':str(denominator_impact),'detail_key':second}]
    return {'comparison_date':snapshots[1].as_of_date.isoformat(),'drivers':drivers,'reconciled':abs(sum((_d(driver['ratio_impact']) for driver in drivers),D(0))-(new_ratio-old_ratio))<D('.0001')}

def _source_rows_by_key(rows):
    output={}
    for row in rows:
        for key in (row.get('key'),row.get('lcr_category'),row.get('code'),row.get('label')):
            if key:
                output[key]=row
    return output

def _lcr_driver_components(current, prior, detail_key):
    current_rows={row['key']:row for row in current['rows']}
    prior_rows={row['key']:row for row in prior['rows']}
    current_source=_source_rows_by_key(snapshot_for(current['_entity'],current['_as_of']).source_data.get('lcr_positions',[]))
    prior_source=_source_rows_by_key(snapshot_for(prior['_entity'],prior['_as_of']).source_data.get('lcr_positions',[]))
    hqla_keys=('level1_coins','level1_reserves','level1_sovereign','level2a_securities','level2b_equities','level2b_cap','level2_cap')
    outflow_keys=('retail_stable','retail_less_stable','wholesale_operational','wholesale_non_operational','secured_funding','other_outflows')
    inflow_keys=('inflow_financial','inflow_customer')
    components=[]
    if detail_key=='hqla':
        for key in hqla_keys:
            current_row=current_rows[key];prior_row=prior_rows[key]
            current_source_row=current_source.get(key,{});prior_source_row=prior_source.get(key,{})
            components.append({
                'id':key,'source_line_item':current_source_row.get('label') or prior_source_row.get('label') or current_row['label'],
                'classification':'Regulatory adjustment' if current_row['kind']=='adjustment' else 'HQLA',
                'prior_balance':_d(prior_source_row.get('balance',prior_row['weighted'])),
                'current_balance':_d(current_source_row.get('balance',current_row['weighted'])),
                'factor':current_source_row.get('lcr_factor',current_row['factor']),
                'prior_contribution':_d(prior_row['weighted']),'current_contribution':_d(current_row['weighted']),
            })
        denominator=_d(prior['net_cash_outflows'])
        for component in components:
            component['metric_impact']=((component['current_contribution']-component['prior_contribution'])/denominator*D(100)) if denominator else D(0)
    elif detail_key=='net_cash_outflows':
        for key in outflow_keys+inflow_keys:
            current_row=current_rows[key];prior_row=prior_rows[key]
            current_source_row=current_source.get(key,{});prior_source_row=prior_source.get(key,{})
            is_inflow=key in inflow_keys
            components.append({
                'id':key,'source_line_item':current_source_row.get('label') or prior_source_row.get('label') or current_row['label'],
                'classification':'Cash inflow' if is_inflow else 'Cash outflow',
                'prior_balance':_d(prior_source_row.get('balance',prior_row['weighted'])),
                'current_balance':_d(current_source_row.get('balance',current_row['weighted'])),
                'factor':current_source_row.get('lcr_factor',current_row['factor']),
                'prior_contribution':-_d(prior_row['weighted']) if is_inflow else _d(prior_row['weighted']),
                'current_contribution':-_d(current_row['weighted']) if is_inflow else _d(current_row['weighted']),
            })
        current_raw_inflows=sum((-component['current_contribution'] for component in components if component['classification']=='Cash inflow'),D(0))
        prior_raw_inflows=sum((-component['prior_contribution'] for component in components if component['classification']=='Cash inflow'),D(0))
        current_eligible=_d(current['eligible_inflows']);prior_eligible=_d(prior['eligible_inflows'])
        if current_raw_inflows!=current_eligible or prior_raw_inflows!=prior_eligible:
            components.append({'id':'inflow_cap_adjustment','source_line_item':'75% regulatory inflow cap adjustment','classification':'Regulatory adjustment','prior_balance':prior_raw_inflows-prior_eligible,'current_balance':current_raw_inflows-current_eligible,'factor':None,'prior_contribution':prior_raw_inflows-prior_eligible,'current_contribution':current_raw_inflows-current_eligible})
        old_denominator=_d(prior['net_cash_outflows']);new_denominator=_d(current['net_cash_outflows']);numerator=_d(current['hqla'])
        for component in components:
            delta=component['current_contribution']-component['prior_contribution']
            component['metric_impact']=(-numerator*delta/(old_denominator*new_denominator)*D(100)) if old_denominator and new_denominator else D(0)
    else:
        raise ValueError('Unsupported LCR driver')
    return components

def _nsfr_driver_components(current, prior, detail_key):
    current_source=_source_rows_by_key(snapshot_for(current['_entity'],current['_as_of']).source_data.get('nsfr_lines',[]))
    prior_source=_source_rows_by_key(snapshot_for(prior['_entity'],prior['_as_of']).source_data.get('nsfr_lines',[]))
    direction='asf' if detail_key=='asf' else 'rsf'
    keys=sorted(set(current_source)|set(prior_source))
    components=[]
    for key in keys:
        current_line=current_source.get(key,{});prior_line=prior_source.get(key,{})
        if (current_line.get('direction') or prior_line.get('direction'))!=direction:
            continue
        def totals(line):
            values=sum((_d(value) for field in ('jod','usd','other') for value in line.get(field,[0,0,0])),D(0))
            factors=line.get('factors',[0,0,0]);weighted=sum((_d(value)*_d(factors[index]) for field in ('jod','usd','other') for index,value in enumerate(line.get(field,[0,0,0]))),D(0))
            return values,weighted
        prior_balance,prior_weighted=totals(prior_line);current_balance,current_weighted=totals(current_line)
        factors=current_line.get('factors') or prior_line.get('factors') or []
        components.append({'id':key,'source_line_item':current_line.get('label') or prior_line.get('label') or key,'classification':'ASF' if direction=='asf' else 'RSF','code':current_line.get('code') or prior_line.get('code') or '', 'prior_balance':prior_balance,'current_balance':current_balance,'factor':' / '.join(str(value) for value in factors),'prior_contribution':prior_weighted,'current_contribution':current_weighted})
    old_denominator=_d(prior['rsf']);new_denominator=_d(current['rsf']);new_numerator=_d(current['asf'])
    for component in components:
        delta=component['current_contribution']-component['prior_contribution']
        component['metric_impact']=(delta/old_denominator*D(100)) if detail_key=='asf' and old_denominator else (-new_numerator*delta/(old_denominator*new_denominator)*D(100)) if old_denominator and new_denominator else D(0)
    return components

def regulatory_driver_detail(entity, report_type, as_of, detail_key):
    """Exact component bridge behind one of the two headline ratio drivers."""
    snapshots=list(RegulatorySnapshot.objects.filter(entity=entity,as_of_date__lte=as_of).order_by('-as_of_date')[:2])
    if len(snapshots)<2:
        return {'comparison_date':None,'items':[],'reconciled':True}
    current=regulatory_report(entity,report_type,snapshots[0].as_of_date)
    prior=regulatory_report(entity,report_type,snapshots[1].as_of_date)
    current['_entity']=prior['_entity']=entity;current['_as_of']=snapshots[0].as_of_date;prior['_as_of']=snapshots[1].as_of_date
    drivers=regulatory_drivers(entity,report_type,snapshots[0].as_of_date)
    driver=next((item for item in drivers['drivers'] if item['detail_key']==detail_key),None)
    if not driver:
        raise ValueError('Unsupported regulatory driver')
    components=_lcr_driver_components(current,prior,detail_key) if report_type=='lcr' else _nsfr_driver_components(current,prior,detail_key)
    total_impact=_d(driver['ratio_impact'])*D(100)
    raw_total=sum((component['metric_impact'] for component in components),D(0))
    scale=total_impact/raw_total if raw_total else D(0)
    total_ratio_change=(_d(current['lcr'] if report_type=='lcr' else current['nsfr'])-_d(prior['lcr'] if report_type=='lcr' else prior['nsfr']))*D(100)
    items=[]
    for component in components:
        impact=component['metric_impact']*scale
        items.append({'id':component['id'],'source_line_item':component['source_line_item'],'classification':component['classification'],'code':component.get('code',''),'prior_balance':str(component['prior_balance']),'current_balance':str(component['current_balance']),'balance_change':str(component['current_balance']-component['prior_balance']),'factor':None if component['factor'] in (None,'') else str(component['factor']),'prior_contribution':str(component['prior_contribution']),'current_contribution':str(component['current_contribution']),'contribution_change':str(component['current_contribution']-component['prior_contribution']),'metric_impact_pp':str(impact),'share_of_movement':None if not total_ratio_change else str(impact/total_ratio_change*D(100))})
    items.sort(key=lambda item:abs(_d(item['metric_impact_pp'])),reverse=True)
    return {'report_type':report_type,'detail_key':detail_key,'label':driver['label'],'as_of_date':snapshots[0].as_of_date.isoformat(),'comparison_date':snapshots[1].as_of_date.isoformat(),'driver_impact_pp':str(total_impact),'ratio_change_pp':str(total_ratio_change),'currency':entity.base_currency,'items':items,'reconciled':abs(sum((_d(item['metric_impact_pp']) for item in items),D(0))-total_impact)<D('.0001'),'data_status':'Mock source data' if snapshots[0].is_mock else 'Mapped source data'}

def regulatory_movement_history(entity, report_type):
    """Return every available month-on-month explanation for the report UI."""
    snapshots=list(RegulatorySnapshot.objects.filter(entity=entity).order_by('as_of_date'))
    movements=[]
    for index, snapshot in enumerate(snapshots):
        if index == 0:
            continue
        report=regulatory_report(entity,report_type,snapshot.as_of_date)
        prior_report=regulatory_report(entity,report_type,snapshots[index-1].as_of_date)
        ratio_key='lcr' if report_type=='lcr' else 'nsfr'
        drivers=regulatory_drivers(entity,report_type,snapshot.as_of_date)
        ranked=sorted(drivers['drivers'],key=lambda driver:abs(_d(driver['ratio_impact'])),reverse=True)
        movements.append({
            'as_of_date':snapshot.as_of_date.isoformat(),
            'comparison_date':snapshots[index-1].as_of_date.isoformat(),
            'ratio':report[ratio_key],
            'delta_pp':str((_d(report[ratio_key])-_d(prior_report[ratio_key]))*D(100)),
            'primary_driver':ranked[0] if ranked else None,
            'drivers':drivers['drivers'],
            'reconciled':drivers['reconciled'],
        })
    return movements
