import type {RegulatoryMovement} from './types';
import {dateLabel} from './api';

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

function driverPhrase(driver:RegulatoryMovement['drivers'][number]){
 return `${Number(driver.amount)>=0?'higher':'lower'} ${driver.label}`;
}

function impactText(driver:RegulatoryMovement['drivers'][number]){
 const impact=Number(driver.ratio_impact)*100;
 return `${impact>=0?'+':''}${impact.toFixed(1)} pp`;
}

function rankedDrivers(movement:RegulatoryMovement){
 const drivers=movement.drivers.filter(driver=>Number.isFinite(Number(driver.ratio_impact))&&Number(driver.ratio_impact)!==0);
 const movementSign=Math.sign(Number(movement.delta_pp));
 const ranked=drivers.slice().sort((a,b)=>Math.abs(Number(b.ratio_impact))-Math.abs(Number(a.ratio_impact)));
 const main=ranked.find(driver=>movementSign===0||Math.sign(Number(driver.ratio_impact))===movementSign)||ranked[0];
 const offset=main?ranked.find(driver=>Math.sign(Number(driver.ratio_impact))!==Math.sign(Number(main.ratio_impact))):undefined;
 return {main,offset};
}

export function movementNarrative(kind:Kind,movement:RegulatoryMovement|undefined,currency:string,entityName?:string){
 if(!movement) return `A month-on-month explanation will be available after a second ${kind.toUpperCase()} snapshot is loaded.`;
 const ratio=labels[kind].ratio;
 const changed=Number(movement.delta_pp), up=changed>=0;
 const subject=entityName?`${entityName}'s ${ratio}`:`${ratio}`;
 const headline=`${subject} ${up?'increased':'decreased'} by ${Math.abs(changed).toFixed(1)} percentage points, from ${dateLabel(movement.comparison_date)} to ${dateLabel(movement.as_of_date)}.`;
 const {main,offset}=rankedDrivers(movement);
 if(!main) return headline;
 const detail=`Mainly ${driverPhrase(main)} (${impactText(main)})${offset?`; partly offset by ${driverPhrase(offset)} (${impactText(offset)}).`:'.'}`;
 return `${headline} ${detail}`;
}

export function movementSummary(kind:Kind,movement:RegulatoryMovement|undefined,currency:string){
 if(!movement) return 'No prior month is available for comparison.';
 const changed=Number(movement.delta_pp), {main}=rankedDrivers(movement);
 if(!main) return `${changed>=0?'+':''}${changed.toFixed(1)} pp.`;
 return `${changed>=0?'+':''}${changed.toFixed(1)} pp · ${driverPhrase(main)}`;
}

/** Compact, source-line explanation for a trend-chart hover tooltip. */
export function movementTooltipSummary(movement:RegulatoryMovement|undefined){
 if(!movement) return 'First available snapshot — no prior period to compare.';
 const {main,offset}=rankedDrivers(movement);
 if(!main) return 'No material source-line movement was identified.';
 return `Mainly ${driverPhrase(main)} (${impactText(main)})${offset?`; partly offset by ${driverPhrase(offset)} (${impactText(offset)}).`:'.'}`;
}
