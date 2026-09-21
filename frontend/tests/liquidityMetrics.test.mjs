import assert from 'node:assert/strict';
import test from 'node:test';
import {buildLiquidityProfile,bucketMovement,comparableBucket,lineContributors,liquidityCsv} from '../src/liquidityMetrics.ts';

function ladder({inflows=[120,0],outflows=[80,100],off=[20,20],capacity=[30,0],interest=0,outflowBalance=1000,offBalance=200}={}){
 const rows=[];
 const add=(key,section,principal,kind='subtotal',children=[],balance='0')=>rows.push({key,section,label:key,kind,balance:String(balance),principal:principal.map(String),interest:[String(interest),String(interest)],total:principal.map(value=>String(value+interest)),children});
 add('retail_time_out','outflows',outflows,'normal',[{key:'retail_time_out:fixed',label:'Fixed',balance:'100',principal:outflows.map(String),interest:['0','0'],total:outflows.map(String)}]);
 add('total_inflows','inflows',inflows);
 add('total_outflows','outflows',outflows,'subtotal',[],outflowBalance);
 add('total_off_balance_sheet','off_balance_sheet',off,'subtotal',[],offBalance);
 add('total_counterbalancing_capacity','counterbalancing_capacity',capacity);
 const before=inflows.map((amount,index)=>amount-outflows[index]-off[index]);
 const after=before.map((amount,index)=>amount+capacity[index]);
 add('contractual_gap','gap',before,'gap');
 add('contractual_gap_including_capacity','gap',after,'gap');
 add('cumulative_contractual_gap','gap',[before[0],before[0]+before[1]],'cumulative');
 add('cumulative_gap_including_capacity','gap',[after[0],after[0]+after[1]],'cumulative');
 return {buckets:[{code:'overnight',label:'Overnight'},{code:'1w',label:'1w'}],rows};
}

test('principal gap ratio uses signed as-of outflow and off-balance-sheet balances',()=>{
 const profile=buildLiquidityProfile(ladder(),'principal');
 assert.equal(profile.reconciled,true);
 assert.deepEqual(profile.buckets.map(point=>point.gapAfter),[50,-120]);
 assert.deepEqual(profile.buckets.map(point=>point.cumulativeAfter),[50,-70]);
 assert.ok(Math.abs(profile.buckets[0].cushionPercent-(50/1200*100))<1e-10);
 assert.ok(lineContributors(profile.ladder,1,'principal').some(line=>line.key==='retail_time_out'&&line.childrenInBucket[0].label==='Fixed'));
});

test('zero obligations yield N/A and principal+interest is independent from as-of balance',()=>{
 const none=buildLiquidityProfile(ladder({outflows:[0,0],off:[0,0],outflowBalance:0,offBalance:0}),'principal');
 assert.equal(none.buckets[0].cushionPercent,null);
 const withInterest=buildLiquidityProfile(ladder({interest:1}),'total');
 assert.equal(withInterest.capacityBalance,0);
 assert.equal(withInterest.buckets[0].inflows,121);
});

test('prior run comparison only accepts matching bucket configurations and reconciles its bridge',()=>{
 const current=buildLiquidityProfile(ladder(),'principal');
 const prior=buildLiquidityProfile(ladder({inflows:[110,0],outflows:[90,100],off:[10,20],capacity:[25,0]}),'principal');
 const bucket=comparableBucket(current,prior,'overnight');
 const movement=bucketMovement(current.buckets[0],bucket);
 assert.equal(movement.reduce((total,item)=>total+item.movement,0),current.buckets[0].gapAfter-bucket.gapAfter);
 prior.buckets[0].code='different';
 assert.equal(comparableBucket(current,prior,'overnight'),null);
});

test('ladder mismatch is flagged and exported CSV distinguishes the gap ratio from regulatory LCR',()=>{
 const altered=ladder();
 altered.rows.find(row=>row.key==='contractual_gap_including_capacity').principal[0]='999';
 const profile=buildLiquidityProfile(altered,'principal');
 assert.equal(profile.reconciled,false);
 assert.match(liquidityCsv(profile,'JOD','contractual','principal','2026-09-21'),/Principal gap ratio \/ signed as-of outflow balance % \(not LCR\)/);
 assert.equal(buildLiquidityProfile({buckets:altered.buckets,rows:[]},'principal'),null);
});
