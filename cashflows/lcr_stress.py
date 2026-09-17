"""Source-driven implementation of the legacy LCR Stress Testing rule library."""
from copy import deepcopy
from decimal import Decimal
from io import BytesIO
from openpyxl import Workbook
from .regulatory import lcr_report_from_positions

D=Decimal
DEFAULTS=[
 {'id':'deposit_withdrawal','name':'Deposit Withdrawal','description':'This shock simulates a situation where a percentage of the bank’s deposits is withdrawn, increasing stressed cash outflows.','enabled':True,'system_default':True,'protected':True,'levels':[{'id':'moderate','label':'10%'},{'id':'medium','label':'20%'},{'id':'severe','label':'30%'}],'rules':[{'name':'Stable retail and SME deposits','target':'stable_deposits','operation':'rate_floor','values':{'moderate':.05,'medium':.10,'severe':.20}},{'name':'Less-stable retail and SME deposits','target':'less_stable_deposits','operation':'rate_floor','values':{'moderate':.10,'medium':.20,'severe':.30}}]},
 {'id':'unused_facilities','name':'Unused Facilities Withdrawal','description':'This scenario assumes that a percentage of unused committed credit and liquidity facilities is drawn.','enabled':True,'system_default':True,'protected':True,'levels':[{'id':'moderate','label':'20%'},{'id':'medium','label':'40%'},{'id':'severe','label':'100%'}],'rules':[{'name':'Committed credit and liquidity facilities','target':'unused_facilities','operation':'rate_floor','values':{'moderate':.20,'medium':.40,'severe':1}}]},
 {'id':'top_depositors','name':'Top Depositors Withdrawal','description':'This shock considers the effect of withdrawals by the bank’s largest depositors using aggregate withdrawal inputs.','enabled':True,'system_default':True,'protected':True,'levels':[{'id':'moderate','label':'Top 1'},{'id':'medium','label':'Top 3'},{'id':'severe','label':'Top 5'}],'rules':[{'name':'Aggregate top-depositor withdrawal','target':'manual_top_depositors','operation':'additional_outflow','value_source':'manual_top_depositors','values':{'moderate':0,'medium':0,'severe':0}}]},
 {'id':'hqla_haircut','name':'HQLA Haircut','description':'A percentage haircut is applied to the value of high-quality liquid assets.','enabled':True,'system_default':True,'protected':True,'levels':[{'id':'moderate','label':'10%'},{'id':'medium','label':'20%'},{'id':'severe','label':'40%'}],'rules':[{'name':'Reduce HQLA component amounts','target':'hqla_components','operation':'amount_haircut','values':{'moderate':.10,'medium':.20,'severe':.40}}]},
 {'id':'credit_default','name':'Credit Default','description':'This shock applies a percentage credit-default rate to expected cash inflows from fully performing loans.','enabled':True,'system_default':True,'protected':True,'levels':[{'id':'moderate','label':'10%'},{'id':'medium','label':'15%'},{'id':'severe','label':'20%'}],'rules':[{'name':'Reduce performing-loan inflows','target':'credit_inflows','operation':'amount_haircut','values':{'moderate':.10,'medium':.15,'severe':.20}}]},
]
DEFAULT_TOP={'moderate':180000,'medium':420000,'severe':680000}
OPERATIONS={'rate_floor','rate_cap','rate_set','rate_add','rate_subtract','rate_increase_pct','rate_decrease_pct','amount_haircut','amount_decrease_pct','amount_increase_pct','amount_multiplier','amount_add','amount_subtract','amount_set','set_zero','additional_outflow','additional_inflow'}

def default_configuration(): return {'version':'2.0','inflow_cap':.75,'lcr_limit':1,'lcr_tolerance':1.2,'scenarios':deepcopy(DEFAULTS)}
def normalise(config):
    value=deepcopy(config or default_configuration());value.setdefault('version','2.0');value.setdefault('inflow_cap',.75);value.setdefault('lcr_limit',1);value.setdefault('lcr_tolerance',1.2);scenarios=value.setdefault('scenarios',[]);found={x.get('id') for x in scenarios}
    for scenario in DEFAULTS:
        if scenario['id'] not in found: scenarios.append(deepcopy(scenario))
    return value
def groups(position):
    category=position.get('lcr_category','');key=position.get('key','')
    output={'all_input_elements'}
    if category.startswith('level'): output|={'hqla_components'}
    if category=='retail_stable': output|={'stable_deposits','outflows'}
    if category=='retail_less_stable': output|={'less_stable_deposits','outflows'}
    if category in ('wholesale_operational','wholesale_non_operational','secured_funding','other_outflows'): output|={'outflows'}
    if category=='other_outflows' or key in ('unused_facilities','contingent'): output|={'unused_facilities'}
    if category.startswith('inflow'): output|={'inflows'}
    if category=='inflow_customer' or key in ('customer_inflows','credit_inflows'): output|={'credit_inflows'}
    return output
def value(rule,level): return D(str(rule.get('values',{}).get(level,0)))
def apply_operation(position,operation,amount):
    balance=D(str(position.get('balance',0)));factor=D(str(position.get('lcr_factor',0)))
    if operation=='rate_floor': factor=max(factor,amount)
    elif operation=='rate_cap': factor=min(factor,amount)
    elif operation=='rate_set': factor=max(D(0),amount)
    elif operation=='rate_add': factor=max(D(0),factor+amount)
    elif operation=='rate_subtract': factor=max(D(0),factor-amount)
    elif operation=='rate_increase_pct': factor=max(D(0),factor*(1+amount))
    elif operation=='rate_decrease_pct': factor=max(D(0),factor*(1-amount))
    elif operation in ('amount_haircut','amount_decrease_pct'): balance=max(D(0),balance*(1-amount))
    elif operation=='amount_increase_pct': balance=max(D(0),balance*(1+amount))
    elif operation=='amount_multiplier': balance=max(D(0),balance*amount)
    elif operation=='amount_add': balance=max(D(0),balance+amount)
    elif operation=='amount_subtract': balance=max(D(0),balance-amount)
    elif operation=='amount_set': balance=max(D(0),amount)
    elif operation=='set_zero': balance=D(0)
    else: raise ValueError(f'Unsupported operation: {operation}')
    position['balance']=str(balance);position['lcr_factor']=str(factor)
def calculate(entity,as_of,source,configuration,top_amounts):
    config=normalise(configuration);baseline=lcr_report_from_positions(source,entity,as_of_date=as_of,basis='Source-driven LCR stress testing baseline.')
    baseline_lcr=D(baseline['lcr']);results=[];audit=[]
    for scenario in (x for x in config['scenarios'] if x.get('enabled',True)):
        for level in scenario.get('levels',[]):
            positions=deepcopy(source);additional_outflow=D(0);additional_inflow=D(0)
            for rule in scenario.get('rules',[]):
                operation=rule.get('operation');amount=value(rule,level['id'])
                if operation in ('additional_outflow','additional_inflow'):
                    applied=D(str(top_amounts.get(level['id'],0))) if rule.get('value_source')=='manual_top_depositors' or rule.get('target')=='manual_top_depositors' else amount
                    if operation=='additional_outflow': additional_outflow+=applied
                    else: additional_inflow+=applied
                    audit.append({'scenario':scenario['name'],'severity':level['label'],'rule':rule.get('name',''),'operation':operation,'target':rule.get('target',''),'element':'Independent cash-flow adjustment','baseline_amount':'0','stressed_amount':str(applied),'weighted_delta':str(applied if operation=='additional_outflow' else -applied)})
                    continue
                for position in positions:
                    selected=rule.get('target') in groups(position) or position.get('key') in rule.get('element_ids',[]) or position.get('lcr_category') in rule.get('element_ids',[])
                    if not selected: continue
                    before=D(str(position.get('balance',0)))*D(str(position.get('lcr_factor',0)));old_balance=position.get('balance',0);old_factor=position.get('lcr_factor',0)
                    apply_operation(position,operation,amount);after=D(str(position['balance']))*D(str(position['lcr_factor']))
                    if before!=after: audit.append({'scenario':scenario['name'],'severity':level['label'],'rule':rule.get('name',''),'operation':operation,'target':rule.get('target',''),'element':position.get('label') or position.get('key'),'baseline_amount':str(old_balance),'baseline_rate':str(old_factor),'stressed_amount':position['balance'],'stressed_rate':position['lcr_factor'],'weighted_delta':str(after-before)})
            if additional_outflow: positions.append({'key':'stress_additional_outflow','label':'Independent additional cash outflow','balance':str(additional_outflow),'lcr_category':'other_outflows','lcr_factor':'1'})
            if additional_inflow: positions.append({'key':'stress_additional_inflow','label':'Independent additional cash inflow','balance':str(additional_inflow),'lcr_category':'inflow_customer','lcr_factor':'1'})
            report=lcr_report_from_positions(positions,entity,as_of_date=as_of,basis='Deterministic source-driven LCR stress calculation.')
            lcr=D(report['lcr']);limit=D(str(config['lcr_limit']));tolerance=D(str(config['lcr_tolerance']));status='Below Limit' if lcr<limit else 'Tolerance' if lcr<tolerance else 'Within Appetite'
            results.append({'scenario_id':scenario['id'],'scenario':scenario['name'],'description':scenario.get('description',''),'type':'System Default' if scenario.get('system_default') else 'Custom','severity_id':level['id'],'severity':level['label'],'hqla':report['hqla'],'weighted_outflows':report['total_outflows'],'gross_weighted_inflows':report['total_inflows'],'inflow_cap':str(D(report['total_outflows'])*D(str(config['inflow_cap']))),'recognized_inflows':report['eligible_inflows'],'net_cash_outflow':report['net_cash_outflows'],'lcr':report['lcr'],'movement':str(lcr-baseline_lcr),'risk_status':status})
    return {'baseline':{'hqla':baseline['hqla'],'weighted_outflows':baseline['total_outflows'],'gross_weighted_inflows':baseline['total_inflows'],'inflow_cap':str(D(baseline['total_outflows'])*D(str(config['inflow_cap']))),'recognized_inflows':baseline['eligible_inflows'],'net_cash_outflow':baseline['net_cash_outflows'],'lcr':baseline['lcr'],'risk_status':'Within Appetite' if baseline_lcr>=D(str(config['lcr_tolerance'])) else 'Tolerance' if baseline_lcr>=D(str(config['lcr_limit'])) else 'Below Limit'},'results':results,'audit':audit,'limit':str(config['lcr_limit']),'tolerance':str(config['lcr_tolerance']),'inflow_cap':str(config['inflow_cap'])}
def xlsx(run):
    wb=Workbook();ws=wb.active;ws.title='Summary';ws.append(['LCR Stress Testing — Management Summary']);ws.append(['Limit',run['results']['limit'],'Tolerance',run['results']['tolerance']]);ws.append(['Baseline LCR',run['results']['baseline']['lcr']]);ws.append([]);ws.append(['Scenario','Severity','LCR','Movement','Risk status','Description'])
    for row in run['results']['results']: ws.append([row['scenario'],row['severity'],float(row['lcr']),float(row['movement']),row['risk_status'],row['description']])
    rs=wb.create_sheet('Results');rs.append(['Scenario','Severity','HQLA','Weighted Outflows','Gross Inflows','75% Inflow Cap','Recognized Inflows','Net Cash Outflow','LCR','Movement','Risk Status'])
    for row in run['results']['results']: rs.append([row['scenario'],row['severity'],float(row['hqla']),float(row['weighted_outflows']),float(row['gross_weighted_inflows']),float(row['inflow_cap']),float(row['recognized_inflows']),float(row['net_cash_outflow']),float(row['lcr']),float(row['movement']),row['risk_status']])
    audit=wb.create_sheet('Rule Impact Audit');audit.append(['Scenario','Severity','Rule','Operation','Target','Element','Baseline Amount','Stressed Amount','Weighted Delta'])
    for row in run['results']['audit']: audit.append([row.get(key,'') for key in ('scenario','severity','rule','operation','target','element','baseline_amount','stressed_amount','weighted_delta')])
    for sheet in wb.worksheets:
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        for cell in sheet[1]: cell.font=cell.font.copy(bold=True,color='FFFFFF');cell.fill=cell.fill.copy(fgColor='183B57',fill_type='solid')
        for column in sheet.columns: sheet.column_dimensions[column[0].column_letter].width=min(42,max(12,max(len(str(c.value or '')) for c in column)+2))
    output=BytesIO();wb.save(output);return output.getvalue()
