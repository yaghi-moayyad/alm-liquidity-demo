import type {Entity,Portfolio,Input,Run,Flow,BehavioralFlow,Validation,Session,EntitySettings,BucketProfile,RunContract,LiquidityAssumptionSet,LiquidityAssumption,ProductCatalogueChoice,RegulatoryConfig,RegulatoryMapping,RegulatoryCalculation,RegulatoryContribution} from './types';
export function csrf(){return decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=')[1]||'');}
export async function request<T>(path:string,options:RequestInit={}):Promise<T>{
 const headers=new Headers(options.headers);headers.set('Accept','application/json');
 if(options.method&&options.method!=='GET'){headers.set('Content-Type','application/json');headers.set('X-CSRFToken',csrf());}
 const response=await fetch('/api/v1'+path,{credentials:'same-origin',...options,headers});
 const data=await response.json();
 if(!response.ok){if(response.status===401||response.status===403){if(String(data.error).includes('credentials'))window.location.href='/accounts/login/?next=/';}
 throw new Error(data.details?Object.entries(data.details).map(([k,v])=>`${k}: ${Array.isArray(v)?v.join(', '):String(v)}`).join(' · '):(data.error||'Request failed'));}
 return data;
}
export const api={
 session:()=>request<Session>('/session'),
 entities:()=>request<Entity[]>('/entities'),
 createEntity:(data:Pick<Entity,'name'|'slug'|'country'|'base_currency'|'is_mock'>)=>request<Entity>('/entities',{method:'POST',body:JSON.stringify(data)}),
 portfolio:(entity:string)=>request<Portfolio>(`/entities/${entity}/portfolio`),
 settings:(entity:string)=>request<EntitySettings>(`/entities/${entity}/settings`),
 saveSettings:(entity:string,data:Pick<EntitySettings,'interest_projection'|'forward_curve'>)=>request<EntitySettings>(`/entities/${entity}/settings`,{method:'PUT',body:JSON.stringify(data)}),
 bucketProfile:(entity:string)=>request<BucketProfile>(`/entities/${entity}/bucket-profile`),
 saveBucketProfile:(entity:string,bucket_days:number[])=>request<BucketProfile>(`/entities/${entity}/bucket-profile`,{method:'PUT',body:JSON.stringify({bucket_days})}),
 assumptions:(entity:string)=>request<LiquidityAssumptionSet>(`/entities/${entity}/assumptions`),
 productCatalogue:(entity:string)=>request<ProductCatalogueChoice[]>(`/entities/${entity}/product-catalogue`),
 saveProductTreatment:(entity:string,id:number,cashflow_treatment:ProductCatalogueChoice['cashflow_treatment'])=>request<ProductCatalogueChoice>(`/entities/${entity}/product-catalogue/${id}`,{method:'PATCH',body:JSON.stringify({cashflow_treatment})}),
 addAssumption:(entity:string,data:Omit<LiquidityAssumption,'id'|'updated'>)=>request<LiquidityAssumptionSet>(`/entities/${entity}/assumptions`,{method:'POST',body:JSON.stringify(data)}),
 saveAssumption:(entity:string,id:number,data:Partial<LiquidityAssumption>)=>request<LiquidityAssumptionSet>(`/entities/${entity}/assumptions/${id}`,{method:'PATCH',body:JSON.stringify(data)}),
 deleteAssumption:(entity:string,id:number)=>request<LiquidityAssumptionSet>(`/entities/${entity}/assumptions/${id}`,{method:'DELETE'}),
 savePortfolio:(input:Input,revision:number)=>request<Portfolio>(`/entities/${input.entity}/portfolio`,{method:'PUT',body:JSON.stringify({...input,expected_revision:revision})}),
 validate:(input:Input)=>request<Validation>('/validate',{method:'POST',body:JSON.stringify(input)}),
 runs:(entity:string)=>request<{runs:Run[]}>(`/runs?entity=${entity}`),
 run:(id:string)=>request<Run>(`/runs/${id}`),
 submit:(input:Input,key:string)=>request<{id:string;status:string}>('/runs',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify(input)}),
 flows:(id:string,contract:string,offset=0)=>request<{total:number;cashflows:Flow[]}>(`/runs/${id}/cashflows?contract_id=${encodeURIComponent(contract)}&limit=100&offset=${offset}`),
 behavioralFlows:(id:string,contract:string,offset=0)=>request<{total:number;cashflows:BehavioralFlow[]}>(`/runs/${id}/behavioral-cashflows?contract_id=${encodeURIComponent(contract)}&limit=100&offset=${offset}`),
 contracts:(id:string,q:string)=>request<{query:string;contracts:RunContract[]}>(`/runs/${id}/contracts?q=${encodeURIComponent(q)}&limit=25`),
 input:(id:string)=>request<Input>(`/runs/${id}/input`),
 regulatoryConfig:(entity:string)=>request<RegulatoryConfig>(`/entities/${entity}/regulatory/config`),
 saveRegulatoryConfig:(entity:string,data:Partial<RegulatoryConfig>)=>request<RegulatoryConfig>(`/entities/${entity}/regulatory/config`,{method:'PUT',body:JSON.stringify(data)}),
 regulatoryMappings:(entity:string)=>request<RegulatoryMapping[]>(`/entities/${entity}/regulatory/mappings`),
 saveRegulatoryMapping:(entity:string,id:number,data:Partial<RegulatoryMapping>)=>request<RegulatoryMapping>(`/entities/${entity}/regulatory/mappings/${id}`,{method:'PATCH',body:JSON.stringify(data)}),
 regulatoryCalculations:(entity:string)=>request<RegulatoryCalculation[]>(`/entities/${entity}/regulatory/calculations`),
 calculateRegulatory:(entity:string)=>request<RegulatoryCalculation>(`/entities/${entity}/regulatory/calculations`,{method:'POST',body:JSON.stringify({})}),
 regulatoryContributions:(entity:string,id:string,metric:string,line='')=>request<RegulatoryContribution[]>(`/entities/${entity}/regulatory/calculations/${id}/contributions?metric=${metric}${line?`&line=${encodeURIComponent(line)}`:''}`),
};
export const money=(value:string|number,currency='JOD')=>Number(value).toLocaleString('en-US',{minimumFractionDigits:currency==='JOD'?3:2,maximumFractionDigits:currency==='JOD'?3:2});
export const compact=(value:string|number)=>new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:2}).format(Number(value));
export const dateLabel=(s:string)=>s?new Date(s+'T00:00:00').toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'}):'—';
export const timeLabel=(s:string)=>new Date(s).toLocaleString('en-GB',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
export const productLabel=(s:string)=>({loan:'Loan',term_deposit:'Term deposit',bond:'Bond',interbank_asset:'Interbank placement',cash_central_bank:'Cash & central bank',borrowing:'Borrowing',demand_deposit:'Demand deposit'}[s]||s);
export const toInput=(p:Portfolio):Input=>({entity:p.entity.slug,as_of_date:p.as_of_date,bucket_days:p.bucket_days,contracts:p.contracts});
