import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {useNavigate} from 'react-router-dom';
import {Alert,Box,Button,Card,Chip,Divider,LinearProgress,MenuItem,Select,Stack,ToggleButton,ToggleButtonGroup,Typography} from '@mui/material';
import {ArrowForwardRounded,AddRounded,CheckCircleOutlineRounded,InsightsRounded,TrendingDownRounded} from '@mui/icons-material';
import {Bar,BarChart,CartesianGrid,Cell,Legend,Line,LineChart,ReferenceLine,ResponsiveContainer,Tooltip,XAxis,YAxis} from 'recharts';
import {useRuns,useWorkspace} from '../context';
import {api,compact,dateLabel,money} from '../api';
import {buildLiquidityProfile,comparableBucket,ladderFor,lineMovement,type CashFlowBasis,type CashFlowMode} from '../liquidityMetrics';
import {movementNarrative,movementSummary} from '../regulatoryNarrative';
import {Empty,ErrorMessage,Loading,PageHeading,SectionHead} from '../components/Common';

const good='#157D70',bad='#BF5C61',blue='#3869C9';
const percent=(value:string)=>`${(Number(value)*100).toFixed(1)}%`;

function Signal({label,value,detail,color,onClick}:{label:string;value:string;detail:string;color:string;onClick?:()=>void}) {
 return <Card onClick={onClick} sx={{p:2.3,minWidth:0,cursor:onClick?'pointer':'default',transition:'transform .15s,box-shadow .15s','&:hover':onClick?{transform:'translateY(-2px)',boxShadow:'0 12px 30px #1B3A5814'}:{}}}>
  <Typography variant="caption" color="text.secondary" fontWeight={650}>{label}</Typography>
  <Typography title={value} sx={{fontSize:{xs:22,md:27},lineHeight:1.28,fontWeight:750,letterSpacing:-.8,color,mt:1.1,overflowWrap:'anywhere'}}>{value}</Typography>
  <Typography variant="caption" color="text.secondary" display="block" mt={.65}>{detail}</Typography>
 </Card>;
}

export default function Overview(){
 const {entity}=useWorkspace(),runs=useRuns(),nav=useNavigate();
 const [chosenCurrency,setCurrency]=useState('');
 const [basis,setBasis]=useState<CashFlowBasis>('contractual');
 const [mode,setMode]=useState<CashFlowMode>('principal');
 const latest=runs.data?.runs.find(run=>['completed','completed_with_exceptions'].includes(run.status));
 const priorRun=runs.data?.runs.filter(run=>['completed','completed_with_exceptions'].includes(run.status)&&run.as_of_date<(latest?.as_of_date||'')).sort((a,b)=>b.as_of_date.localeCompare(a.as_of_date))[0];
 const detail=useQuery({queryKey:['run',latest?.id],queryFn:()=>api.run(latest!.id),enabled:!!latest});
 const priorDetail=useQuery({queryKey:['run',priorRun?.id],queryFn:()=>api.run(priorRun!.id),enabled:!!priorRun});
 const lcr=useQuery({queryKey:['overview-lcr',entity?.slug],queryFn:()=>api.lcrReport(entity!.slug),enabled:!!entity});
 const nsfr=useQuery({queryKey:['overview-nsfr',entity?.slug],queryFn:()=>api.nsfrReport(entity!.slug),enabled:!!entity});
 const lcrSeries=useQuery({queryKey:['overview-lcr-series',entity?.slug],queryFn:()=>api.regulatorySeries(entity!.slug,'lcr'),enabled:!!entity});
 const nsfrSeries=useQuery({queryKey:['overview-nsfr-series',entity?.slug],queryFn:()=>api.regulatorySeries(entity!.slug,'nsfr'),enabled:!!entity});
 const lcrHistory=useQuery({queryKey:['overview-lcr-movement',entity?.slug],queryFn:()=>api.regulatoryMovementHistory(entity!.slug,'lcr'),enabled:!!entity});
 const nsfrHistory=useQuery({queryKey:['overview-nsfr-movement',entity?.slug],queryFn:()=>api.regulatoryMovementHistory(entity!.slug,'nsfr'),enabled:!!entity});
 const stressPreview=useQuery({queryKey:['overview-lcr-stress',entity?.slug,lcr.data?.as_of_date],queryFn:()=>api.lcrStressPreview(entity!.slug,lcr.data!.as_of_date!),enabled:!!entity&&!!lcr.data?.as_of_date,staleTime:60_000});
 if(runs.isLoading||detail.isLoading)return <Loading/>;
 const result=detail.data?.result;
 const currency=result?.currencies.includes(chosenCurrency)?chosenCurrency:
  result?.currencies.includes(entity?.base_currency||'')?entity!.base_currency:result?.currencies[0]||entity?.base_currency||'JOD';
 const availableBehavioral=!!result?.behavioral_bank_ladder?.[currency];
 const effectiveBasis=basis==='behavioral'&&availableBehavioral?'behavioral':'contractual';
 const profile=result?buildLiquidityProfile(ladderFor(result,currency,effectiveBasis),mode):null;
 const principalProfile=result?buildLiquidityProfile(ladderFor(result,currency,effectiveBasis),'principal'):null;
 const weakest=profile?.buckets.reduce((min,point)=>point.cumulativeAfter<min.cumulativeAfter?point:min,profile.buckets[0]);
 const firstDeficit=profile?.buckets.find(point=>point.cumulativeAfter<0);
 const largestObligation=profile?.buckets.reduce((max,point)=>point.outflows+point.offBalance>max.outflows+max.offBalance?point:max,profile.buckets[0]);
 const older=priorDetail.data?.result;
 const oldProfile=older?buildLiquidityProfile(ladderFor(older,currency,effectiveBasis),mode):null;
 const sameBucket=profile&&weakest?comparableBucket(profile,oldProfile,weakest.code):null;
 const gapChange=sameBucket&&weakest?weakest.cumulativeAfter-sameBucket.cumulativeAfter:null;
 const topLine=profile&&oldProfile&&sameBucket&&weakest?lineMovement(profile.ladder,oldProfile.ladder,weakest.index,mode)[0]:null;
 const unreconciled=result?.controls.filter(control=>!control.passed).length||0;
 const incomplete=!!result&&(result.rejected_count>0||unreconciled>0||!profile?.reconciled);
 const lcrMove=lcrHistory.data?.movements.find(move=>move.as_of_date===lcr.data?.as_of_date);
 const nsfrMove=nsfrHistory.data?.movements.find(move=>move.as_of_date===nsfr.data?.as_of_date);
 const stressRows=stressPreview.data?.results.results||[];
 const worstStress=[...stressRows].sort((a,b)=>Number(a.lcr)-Number(b.lcr))[0];
 const stressLimit=Number(stressPreview.data?.results.limit||1)*100;
 const stressChart=[
  {label:'Baseline LCR',value:Number(stressPreview.data?.results.baseline.lcr||lcr.data?.lcr||0)*100,color:'#3869C9'},
  ...(worstStress?[{label:`Worst stress · ${worstStress.scenario}`,value:Number(worstStress.lcr)*100,color:Number(worstStress.lcr)*100>=stressLimit?'#248A77':'#BF5C61'}]:[]),
 ];
 const regulatoryTrend:{as_of_date:string;label:string;lcr?:number;nsfr?:number}[]=[];
 for(const item of lcrSeries.data?.points||[]) regulatoryTrend.push({as_of_date:item.as_of_date,label:dateLabel(item.as_of_date),lcr:Number(item.ratio)*100});
 for(const item of nsfrSeries.data?.points||[]){const point=regulatoryTrend.find(value=>value.as_of_date===item.as_of_date);if(point)point.nsfr=Number(item.ratio)*100;else regulatoryTrend.push({as_of_date:item.as_of_date,label:dateLabel(item.as_of_date),nsfr:Number(item.ratio)*100});}
 regulatoryTrend.sort((a,b)=>a.as_of_date.localeCompare(b.as_of_date));
 const analytics=(bucket?:string)=>nav(`/analytics${bucket?`?bucket=${encodeURIComponent(bucket)}`:''}`);
 const ladder=()=>nav(`/results/${latest!.id}?tab=ladder&currency=${currency}&basis=${effectiveBasis}&mode=${mode}`);

 return <>
  <PageHeading title="Overview" subtitle="The liquidity position, what changed, and where management should look next." action={<Button variant="contained" startIcon={<AddRounded/>} onClick={()=>nav('/new')}>New calculation</Button>}/>
  <ErrorMessage error={runs.error||detail.error}/>
  {(lcr.error||nsfr.error||lcrSeries.error||nsfrSeries.error)&&<Alert severity="warning" sx={{mb:2}}>A regulatory report is unavailable. Cash-flow results remain accessible; open LCR or NSFR for details.</Alert>}
  {!result?<Empty title="No completed cash-flow run yet" description="Run a calculation to populate the liquidity position. Regulatory reports remain available from navigation." action={<Button variant="contained" onClick={()=>nav('/new')}>Start calculation</Button>}/>:<>
   <Card sx={{p:{xs:2.4,md:3},mb:2.5,color:'white',border:0,background:'linear-gradient(117deg,#102A41 0%,#174E5C 62%,#227D75 100%)',position:'relative',overflow:'hidden'}}>
    <Box sx={{position:'absolute',width:360,height:360,border:'65px solid #FFFFFF0D',borderRadius:'50%',right:-150,top:-200,pointerEvents:'none'}}/>
    <Stack direction={{xs:'column',md:'row'}} gap={2} alignItems={{md:'center'}} justifyContent="space-between" position="relative">
     <Box><Typography variant="overline" sx={{color:'#A9DDD5',letterSpacing:1.5}}>MANAGEMENT SNAPSHOT · {entity?.name?.toUpperCase()}</Typography>
      <Typography variant="h5" fontWeight={750} mt={.5}>{!profile?'No comparable ladder available':firstDeficit?`Shortfall begins in ${firstDeficit.label}`:incomplete?'Position requires validation':'No modelled cumulative shortfall'}</Typography>
      <Typography variant="body2" sx={{color:'#D3E4E5',mt:1,maxWidth:650}}>Cash-flow run dated {dateLabel(result.as_of_date)} · {currency} original currency. A modelled gap is not an opening cash-balance forecast or regulatory LCR.</Typography>
     </Box>
     <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center"><Chip size="small" label={entity?.is_mock?'DEMO DATA':'BANK DATA'} sx={{color:'#144B52',bgcolor:'#B8E7DC',fontWeight:750}}/><Chip size="small" label={incomplete?'REVIEW CONTROLS':'RUN RECONCILED'} sx={{bgcolor:incomplete?'#FFDCB8':'#DEF2E8',color:incomplete?'#8A4A19':'#146357',fontWeight:750}}/></Stack>
    </Stack>
   </Card>
   <Stack direction={{xs:'column',md:'row'}} gap={1.5} mb={2.5} alignItems={{md:'center'}} flexWrap="wrap">
    <Select size="small" value={currency} onChange={event=>setCurrency(event.target.value)} inputProps={{'aria-label':'Original currency'}} sx={{minWidth:160,bgcolor:'white'}}>{result.currencies.map(item=><MenuItem key={item} value={item}>{item} · original</MenuItem>)}</Select>
    <ToggleButtonGroup size="small" exclusive value={effectiveBasis} onChange={(_,value:CashFlowBasis|null)=>value&&setBasis(value)}><ToggleButton value="contractual">Contractual</ToggleButton><ToggleButton value="behavioral" disabled={!availableBehavioral}>Behavioural</ToggleButton></ToggleButtonGroup>
    <ToggleButtonGroup size="small" exclusive value={mode} onChange={(_,value:CashFlowMode|null)=>value&&setMode(value)}><ToggleButton value="principal">Principal</ToggleButton><ToggleButton value="total">Principal + interest</ToggleButton></ToggleButtonGroup>
    <Typography variant="caption" color="text.secondary" sx={{ml:{md:'auto'}}}>Run {latest?.id.slice(0,8)} · {result.accepted_count.toLocaleString()} accepted</Typography>
   </Stack>
   {!profile?<Alert severity="info" sx={{mb:3}}>This run has no compatible bank-format ladder for {currency}. Create a new run to enable reconciled liquidity analytics.</Alert>:<>
    <Box sx={{display:'grid',gridTemplateColumns:{xs:'repeat(2,minmax(0,1fr))',lg:'repeat(3,minmax(0,1fr))',xl:'repeat(6,minmax(0,1fr))'},gap:1.6,mb:3}}>
     <Signal label="LCR" value={lcr.data?percent(lcr.data.lcr):'Unavailable'} color={blue} detail={`Regulatory · ${dateLabel(lcr.data?.as_of_date||'')||'no snapshot'} · all currencies`} onClick={()=>nav('/lcr')}/>
     <Signal label="NSFR" value={nsfr.data?percent(nsfr.data.nsfr):'Unavailable'} color={blue} detail={`Regulatory · ${dateLabel(nsfr.data?.as_of_date||'')||'no snapshot'} · all currencies`} onClick={()=>nav('/nsfr')}/>
     <Signal label="Lowest cumulative gap" value={money(weakest?.cumulativeAfter||0,currency)} color={(weakest?.cumulativeAfter||0)<0?bad:good} detail={`${weakest?.label} · after capacity`} onClick={()=>analytics(weakest?.code)}/>
     <Signal label="First shortfall" value={firstDeficit?.label||'None modelled'} color={firstDeficit?bad:good} detail="Cumulative gap after capacity" onClick={()=>analytics(firstDeficit?.code)}/>
     <Signal label="Counterbalancing position" value={money(profile.capacityBalance,currency)} color={blue} detail={`Balance as of ${dateLabel(result.as_of_date)} · principal only`} onClick={ladder}/>
     <Signal label="Largest obligations" value={money((largestObligation?.outflows||0)+(largestObligation?.offBalance||0),currency)} color="#A17437" detail={`${largestObligation?.label} · outflows + off-balance-sheet`} onClick={()=>analytics(largestObligation?.code)}/>
    </Box>
    <Card sx={{mb:2.5}}><SectionHead title="Regulatory trend" subtitle="LCR and NSFR over the loaded month-end snapshots · open a report to explore any month" action={<Stack direction="row" gap={1}><Button size="small" onClick={()=>nav('/lcr')}>LCR</Button><Button size="small" onClick={()=>nav('/nsfr')}>NSFR</Button></Stack>}/>
     <Box sx={{height:315,px:{xs:1,md:2},pb:1}}><ResponsiveContainer width="100%" height="100%"><LineChart data={regulatoryTrend} margin={{top:10,right:28,bottom:8,left:0}}><CartesianGrid vertical={false} stroke="#E8EEF3" strokeDasharray="3 4"/><XAxis dataKey="label" tick={{fontSize:10}} interval="preserveStartEnd"/><YAxis tickFormatter={(value:number)=>`${value.toFixed(0)}%`} width={58} tick={{fontSize:10}}/><ReferenceLine y={100} stroke="#BF5C61" strokeDasharray="4 4" label={{value:'100% minimum',position:'insideTopRight',fontSize:10,fill:'#9C3E44'}}/><Tooltip formatter={(value)=>`${Number(value).toFixed(1)}%`}/><Legend wrapperStyle={{fontSize:11}}/><Line type="monotone" connectNulls dataKey="lcr" name="LCR" stroke="#3869C9" strokeWidth={3} dot={{r:3}} activeDot={{r:6}}/><Line type="monotone" connectNulls dataKey="nsfr" name="NSFR" stroke="#248A77" strokeWidth={3} dot={{r:3}} activeDot={{r:6}}/></LineChart></ResponsiveContainer></Box>
     <Divider/><Typography variant="caption" color="text.secondary" display="block" px={2.5} py={1.5}>Ratios are calculated from saved regulatory source snapshots. The 100% line is a regulatory minimum, not a complete risk-appetite assessment.</Typography>
    </Card>
    <Card sx={{mb:2.5}}><SectionHead title="Maturity pressure" subtitle="Full-width scheduled inflows, outflows, off-balance-sheet exposure and capacity by maturity bucket" action={<Button size="small" onClick={()=>analytics()} endIcon={<ArrowForwardRounded/>}>Explore</Button>}/>
     <Box sx={{height:325,px:{xs:1,md:2},pb:1}}><ResponsiveContainer width="100%" height="100%"><BarChart data={profile.buckets} onClick={state=>{const item=(state as {activePayload?:{payload?:{code:string}}[]})?.activePayload?.[0]?.payload;if(item)analytics(item.code)}} margin={{top:10,right:20,bottom:8,left:4}}><CartesianGrid vertical={false} stroke="#E8EEF3" strokeDasharray="3 4"/><XAxis dataKey="label" tick={{fontSize:10}} interval="preserveStartEnd"/><YAxis tickFormatter={(value:number)=>compact(value)} width={68} tick={{fontSize:10}}/><Tooltip formatter={(value)=>money(Number(value),currency)}/><Legend wrapperStyle={{fontSize:11}}/><Bar dataKey="inflows" name="Inflows" fill="#198473" maxBarSize={38}/><Bar dataKey="outflows" name="Outflows" fill="#6688C9" maxBarSize={38}/><Bar dataKey="offBalance" name="Off-balance sheet" fill="#C18B50" maxBarSize={38}/><Bar dataKey="capacity" name="Capacity" fill="#54ACC4" maxBarSize={38}/></BarChart></ResponsiveContainer></Box>
     <Divider/><Typography variant="caption" color="text.secondary" display="block" px={2.5} py={1.5}>A management view from the bank-format ladder. Capacity eligibility, encumbrance and reuse need separate validation.</Typography>
    </Card>
    <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',lg:'minmax(0,1.35fr) minmax(330px,1fr)'},gap:2.5,mb:2.5}}>
     <Card>
      <SectionHead title="Principal gap ratio by bucket" subtitle="Principal gap including capacity ÷ signed as-of outflow and off-balance-sheet balances · not LCR" action={<Button size="small" onClick={ladder} endIcon={<ArrowForwardRounded/>}>Open ladder</Button>}/>
      <Box p={2.3} pt={0}>
       <Box sx={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(92px,1fr))',gap:1}}>
        {(principalProfile?.buckets||[]).map(bucket=>{
         const value=bucket.cushionPercent;
         const tone=value===null?'#EFF2F6':value<0?'#FBE7E8':value<10?'#FFF2DE':'#E6F4EF';
         const color=value===null?'text.secondary':value<0?'error.main':value<10?'#9A6A24':'success.main';
         return <Box key={bucket.code} onClick={()=>analytics(bucket.code)} sx={{cursor:'pointer',minWidth:0,p:1.15,borderRadius:1.5,bgcolor:tone,border:'1px solid #E2E8EF','&:hover':{transform:'translateY(-1px)',boxShadow:'0 6px 16px #1B3A5814'}}}>
          <Typography variant="caption" fontWeight={700} noWrap display="block">{bucket.label}</Typography>
          <Typography variant="body2" fontWeight={800} color={color} mt={.45}>{value===null?'N/A':`${value.toFixed(1)}%`}</Typography>
          <Typography variant="caption" color="text.secondary" noWrap display="block">{money(bucket.gapAfter,currency)}</Typography>
         </Box>;
        })}
       </Box>
       <Typography variant="caption" display="block" color="text.secondary" mt={1.5}>Positive is a modelled surplus; negative is a modelled shortfall. This is a liquidity-management indicator, not an approved limit.</Typography>
      </Box>
     </Card>
     <Card><SectionHead title="Stress resilience" subtitle="Baseline LCR compared with the lowest calculated stress result" action={<Button size="small" onClick={()=>nav('/lcr-stress')} endIcon={<ArrowForwardRounded/>}>Stress testing</Button>}/>{stressPreview.isLoading?<LinearProgress/>:stressPreview.error?<Box p={2.4}><Alert severity="info">A stress preview is unavailable for this regulatory snapshot. Open Stress testing to review or run the approved scenarios.</Alert></Box>:worstStress?<><Stack direction="row" gap={1.1} p={2.2} pb={0} flexWrap="wrap"><Chip label={`Worst result · ${percent(worstStress.lcr)}`} color={Number(worstStress.lcr)*100>=stressLimit?'success':'error'} variant="outlined"/><Chip label={worstStress.severity} size="small" variant="outlined"/><Chip label={`Limit · ${stressLimit.toFixed(0)}%`} size="small" variant="outlined"/></Stack><Box height={176} px={1.5} pb={1}><ResponsiveContainer width="100%" height="100%"><BarChart layout="vertical" data={stressChart} margin={{top:8,right:25,bottom:5,left:28}}><CartesianGrid horizontal={false} stroke="#E8EEF3" strokeDasharray="3 4"/><XAxis type="number" tickFormatter={(value:number)=>`${value.toFixed(0)}%`} tick={{fontSize:10}}/><YAxis type="category" dataKey="label" width={148} tick={{fontSize:10}}/><ReferenceLine x={stressLimit} stroke="#BF5C61" strokeDasharray="4 4"/><Tooltip formatter={(value)=>`${Number(value).toFixed(1)}%`}/><Bar dataKey="value" radius={[0,4,4,0]}>{stressChart.map(item=><Cell key={item.label} fill={item.color}/>)}</Bar></BarChart></ResponsiveContainer></Box><Typography variant="caption" display="block" color="text.secondary" px={2.4} pb={2.2}>Worst selected result: {worstStress.scenario} · {worstStress.severity}. This is calculated from the selected LCR source snapshot.</Typography></>:<Box p={2.4}><Typography variant="body2" color="text.secondary">No enabled stress result is available for this regulatory snapshot.</Typography></Box>}</Card>
    </Box>
    <Card sx={{mb:2.5}}><SectionHead title="Movement from last month" subtitle="Click a card to open the selected LCR or NSFR report and inspect the underlying components."/><Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',lg:'1fr 1fr'},gap:1.3,p:2.2,pt:0}}>{([['lcr','LCR',lcrMove,'/lcr'],['nsfr','NSFR',nsfrMove,'/nsfr']] as const).map(([kind,label,movement,path])=><Box key={label} onClick={()=>nav(`${path}${movement?`?as_of=${movement.as_of_date}`:''}`)} sx={{cursor:'pointer',p:2,borderRadius:2,border:'1px solid #E5EAF1',bgcolor:'#FBFCFE','&:hover':{bgcolor:'#F3F7FF',borderColor:'#BFD0F6'}}}><Stack direction="row" justifyContent="space-between" alignItems="start" gap={1}><Box><Typography variant="subtitle2" fontWeight={800}>{label}</Typography><Typography variant="caption" color="text.secondary">{movement?.comparison_date?`${dateLabel(movement.comparison_date)} → ${dateLabel(movement.as_of_date)}`:'No prior comparison'}</Typography></Box><ArrowForwardRounded sx={{fontSize:18,color:'primary.main'}}/></Stack><Typography variant="body2" sx={{color:Number(movement?.delta_pp||0)<0?bad:good,mt:1}} fontWeight={800}>{movementSummary(kind,movement,entity?.base_currency||'JOD')}</Typography><Typography variant="body2" color="text.secondary" mt={.8} sx={{lineHeight:1.55}}>{movementNarrative(kind,movement,entity?.base_currency||'JOD',entity?.name)}</Typography></Box>)}</Box></Card>
    <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',lg:'minmax(0,1.1fr) minmax(320px,1fr)'},gap:2.5,mb:2.5}}>
      <Card><SectionHead title="Liquidity movement" subtitle="Comparable cash-flow run"/><Box px={2.5} pb={2.5}><Box onClick={()=>analytics(weakest?.code)} sx={{cursor:'pointer',p:1.5,borderRadius:2,bgcolor:'#F5F8FA','&:hover':{bgcolor:'#ECF3F8'}}}><Stack direction="row" justifyContent="space-between"><Typography variant="body2" fontWeight={750}>Cumulative gap · {weakest?.label} · {priorRun?`${dateLabel(priorRun.as_of_date)} → ${dateLabel(result.as_of_date)}`:'No prior run'}</Typography><ArrowForwardRounded sx={{fontSize:17,color:'text.secondary'}}/></Stack><Typography variant="body2" sx={{color:(gapChange||0)<0?bad:good,mt:.5}} fontWeight={750}>{gapChange===null?'No comparable historical position':`${gapChange>0?'+':''}${money(gapChange,currency)} ${currency}`}</Typography><Typography variant="caption" color="text.secondary">{topLine?`Largest movement within this bucket: ${topLine.label}. Open analysis for the complete bridge.`:'Comparison requires matching buckets and currency.'}</Typography></Box></Box></Card>
      <Card><SectionHead title="Needs attention" subtitle="Evidence-based checks for this saved run"/><Stack px={2.5} pb={2.5} gap={1.2}>
       {firstDeficit&&<Alert severity="warning" action={<Button size="small" onClick={()=>analytics(firstDeficit.code)}>Inspect</Button>}>First modelled deficit: {firstDeficit.label} ({money(firstDeficit.cumulativeAfter,currency)}).</Alert>}
       {result.rejected_count>0&&<Alert severity="warning" action={<Button size="small" onClick={()=>nav(`/results/${latest!.id}?tab=controls`)}>Review</Button>}>{result.rejected_count} contracts excluded from this run.</Alert>}
       {(unreconciled>0||!profile.reconciled)&&<Alert severity="error" action={<Button size="small" onClick={()=>nav(`/results/${latest!.id}?tab=controls`)}>Controls</Button>}>Calculation or ladder reconciliation requires review.</Alert>}
       {!firstDeficit&&!incomplete&&<Stack direction="row" gap={1} alignItems="center"><CheckCircleOutlineRounded color="success"/><Typography variant="body2">No negative modelled cumulative bucket; run checks passed. Bank appetite has not been assessed.</Typography></Stack>}
     </Stack></Card>
    </Box>
    <Card sx={{p:2.3,mb:3,bgcolor:'#F5F8FA'}}><Stack direction={{xs:'column',md:'row'}} alignItems={{md:'center'}} justifyContent="space-between" gap={2}><Box><Typography variant="subtitle1" fontWeight={750}>Take the next step</Typography><Typography variant="body2" color="text.secondary">Inspect a weak bucket, open an approved regulatory report, or review validation before discussing this position at ALCO.</Typography></Box><Stack direction="row" gap={1} flexWrap="wrap"><Button variant="contained" startIcon={<InsightsRounded/>} onClick={()=>analytics(weakest?.code)}>Investigate liquidity</Button><Button variant="outlined" onClick={ladder}>Bank-format ladder</Button><Button variant="text" onClick={()=>nav(`/results/${latest!.id}?tab=controls`)}>Controls</Button></Stack></Stack></Card>
   </>}
  </>}
 </>;
}
