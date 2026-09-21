import type {RegulatoryMovement} from './types';
import {dateLabel,money} from './api';

type Kind='lcr'|'nsfr';

const labels:{[K in Kind]:{ratio:string;components:Record<string,{subject:string;increase:string;decrease:string}>}}={
 lcr:{ratio:'LCR',components:{
  hqla:{subject:'high-quality liquid assets',increase:'increased',decrease:'decreased'},
  net_cash_outflows:{subject:'net cash outflows',increase:'increased',decrease:'decreased'},
 }},
 nsfr:{ratio:'NSFR',components:{
  asf:{subject:'available stable funding',increase:'increased',decrease:'decreased'},
  rsf:{subject:'required stable funding',increase:'increased',decrease:'decreased'},
 }},
};

function componentFor(kind:Kind,key:string){
 if(kind==='lcr') return key==='hqla'?labels.lcr.components.hqla:labels.lcr.components.net_cash_outflows;
 return key==='asf'?labels.nsfr.components.asf:labels.nsfr.components.rsf;
}

function driverKey(kind:Kind,driver:RegulatoryMovement['drivers'][number]){
 if(kind==='lcr') return driver.detail_key==='hqla'?'hqla':'net_cash_outflows';
 return driver.detail_key==='asf'?'asf':'rsf';
}

export function movementNarrative(kind:Kind,movement:RegulatoryMovement|undefined,currency:string,entityName?:string){
 if(!movement) return `A month-on-month explanation will be available after a second ${kind.toUpperCase()} snapshot is loaded.`;
 const ratio=labels[kind].ratio;
 const changed=Number(movement.delta_pp), up=changed>=0;
 const subject=entityName?`${entityName}'s ${ratio}`:`${ratio}`;
 const headline=`${subject} ${up?'increased':'decreased'} by ${Math.abs(changed).toFixed(1)} percentage points, from ${dateLabel(movement.comparison_date)} to ${dateLabel(movement.as_of_date)}.`;
 const ranked=[...movement.drivers].sort((a,b)=>Math.abs(Number(b.ratio_impact))-Math.abs(Number(a.ratio_impact))).slice(0,2);
 if(!ranked.length) return headline;
 const detail=ranked.map((driver,index)=>{
  const amount=Number(driver.amount), impact=Number(driver.ratio_impact)*100;
  const component=componentFor(kind,driverKey(kind,driver));
  const verb=amount>=0?component.increase:component.decrease;
  const effect=impact>=0?'added':'reduced';
  const prefix=index===0?'The main contributor was':'The other material contributor was';
  return `${prefix} ${component.subject} ${verb} by ${money(Math.abs(amount),currency)}, which ${effect} ${ratio} by ${Math.abs(impact).toFixed(2)} pp.`;
 }).join(' ');
 return `${headline} ${detail}`;
}

export function movementSummary(kind:Kind,movement:RegulatoryMovement|undefined,currency:string){
 if(!movement) return 'No prior month is available for comparison.';
 const changed=Number(movement.delta_pp), first=[...movement.drivers].sort((a,b)=>Math.abs(Number(b.ratio_impact))-Math.abs(Number(a.ratio_impact)))[0];
 if(!first) return `${changed>=0?'+':''}${changed.toFixed(1)} pp.`;
 const component=componentFor(kind,driverKey(kind,first));
 return `${changed>=0?'+':''}${changed.toFixed(1)} pp · ${component.subject} ${Number(first.amount)>=0?component.increase:component.decrease} ${money(Math.abs(Number(first.amount)),currency)}`;
}
