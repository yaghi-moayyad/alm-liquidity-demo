import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {useNavigate,useSearchParams} from 'react-router-dom';
import {Accordion,AccordionDetails,AccordionSummary,Alert,Box,Button,Card,Chip,Divider,MenuItem,Select,Stack,Table,TableBody,TableCell,TableContainer,TableHead,TableRow,ToggleButton,ToggleButtonGroup,Typography} from '@mui/material';
import {ArrowForwardRounded,DownloadRounded,ExpandMoreRounded,InsightsRounded,OpenInNewRounded} from '@mui/icons-material';
import {Area,AreaChart,Bar,BarChart,CartesianGrid,Legend,ReferenceLine,ResponsiveContainer,Tooltip,XAxis,YAxis} from 'recharts';
import {api,compact,dateLabel,money} from '../api';
import {useRuns,useWorkspace} from '../context';
import {buildLiquidityProfile,bucketMovement,comparableBucket,ladderFor,lineContributors,lineMovement,liquidityCsv,type CashFlowBasis,type CashFlowMode} from '../liquidityMetrics';
import {Empty,ErrorMessage,Loading,PageHeading,SectionHead} from '../components/Common';

const green='#198473',navy='#205C82',red='#BA555F';
const sectionNames:Record<string,string>={inflows:'Inflows',outflows:'Outflows',off_balance_sheet:'Off-balance-sheet',counterbalancing_capacity:'Counterbalancing capacity'};
const sectionOrder=['inflows','outflows','off_balance_sheet','counterbalancing_capacity'];

function Figure({label,value,note,tone=navy,full}:{label:string;value:string;note:string;tone?:string;full?:string}){
 return <Card sx={{p:2.1,minWidth:0,borderTop:`3px solid ${tone}`}}><Typography variant="caption" color="text.secondary" fontWeight={650}>{label}</Typography><Typography title={full||value} sx={{fontSize:{xs:21,md:26},fontWeight:760,color:tone,letterSpacing:-.6,mt:1,overflowWrap:'anywhere'}}>{value}</Typography><Typography variant="caption" color="text.secondary">{note}</Typography></Card>;
}

export default function LiquidityAnalytics(){
 const {entity}=useWorkspace(),runs=useRuns(),nav=useNavigate(),[searchParams]=useSearchParams();
 const [chosenRun,setRun]=useState(''),[chosenCurrency,setCurrency]=useState('');
 const [basis,setBasis]=useState<CashFlowBasis>('contractual'),[mode,setMode]=useState<CashFlowMode>('principal');
 const [comparisonChoice,setComparisonChoice]=useState('auto');
 const [selectedCode,setSelectedCode]=useState(searchParams.get('bucket')||'');
 const [showAll,setShowAll]=useState(false);
 const completed=runs.data?.runs.filter(run=>['completed','completed_with_exceptions'].includes(run.status)).sort((a,b)=>b.as_of_date.localeCompare(a.as_of_date)||b.created.localeCompare(a.created))||[];
 const currentRun=completed.find(run=>run.id===chosenRun)||completed[0];
 const current=useQuery({queryKey:['run',currentRun?.id],queryFn:()=>api.run(currentRun!.id),enabled:!!currentRun});
 const priorOptions=completed.filter(run=>run.id!==currentRun?.id&&run.as_of_date<=(currentRun?.as_of_date||''));
 const priorRun=comparisonChoice==='none'?undefined:comparisonChoice==='auto'?priorOptions.find(run=>run.as_of_date!==currentRun?.as_of_date):priorOptions.find(run=>run.id===comparisonChoice);
 const previous=useQuery({queryKey:['run',priorRun?.id],queryFn:()=>api.run(priorRun!.id),enabled:!!priorRun});
 if(runs.isLoading||current.isLoading)return <Loading/>;
 if(!currentRun)return <Empty title="No completed liquidity calculation" description="Create a cash-flow run to investigate its bank-format ladder." action={<Button variant="contained" onClick={()=>nav('/new')}>New calculation</Button>}/>;
 if(current.error)return <ErrorMessage error={current.error}/>;
 const result=current.data?.result;
 if(!result)return <Empty title="Liquidity calculation not available" description="Return to run history and check the calculation status." action={<Button onClick={()=>nav('/runs')}>Run history</Button>}/>;
 const currency=result.currencies.includes(chosenCurrency)?chosenCurrency:result.currencies.includes(entity?.base_currency||'')?entity!.base_currency:result.currencies[0]||'JOD';
 const availableBehavioral=!!result.behavioral_bank_ladder?.[currency];
 const effectiveBasis=basis==='behavioral'&&availableBehavioral?'behavioral':'contractual';
 const profile=buildLiquidityProfile(ladderFor(result,currency,effectiveBasis),mode);
 const priorResult=previous.data?.result;
 const priorProfile=priorResult?buildLiquidityProfile(ladderFor(priorResult,currency,effectiveBasis),mode):null;
 const weakest=profile?.buckets.reduce((min,bucket)=>bucket.cumulativeAfter<min.cumulativeAfter?bucket:min,profile.buckets[0]);
 const selected=profile?.buckets.find(bucket=>bucket.code===selectedCode)||weakest;
 const firstDeficit=profile?.buckets.find(bucket=>bucket.cumulativeAfter<0);
 const biggest=profile?.buckets.reduce((max,bucket)=>bucket.outflows+bucket.offBalance>max.outflows+max.offBalance?bucket:max,profile.buckets[0]);
 const priorBucket=profile&&selected?comparableBucket(profile,priorProfile,selected.code):null;
 const compare=priorBucket&&selected?bucketMovement(selected,priorBucket):[];
 const movements=priorBucket&&profile&&priorProfile&&selected?lineMovement(profile.ladder,priorProfile.ladder,selected.index,mode):[];
 const contributors=profile&&selected?lineContributors(profile.ladder,selected.index,mode):[];
 const ladderLink=(row?:string)=>`/results/${currentRun.id}?tab=ladder&currency=${encodeURIComponent(currency)}&basis=${effectiveBasis}&mode=${mode}&bucket=${encodeURIComponent(selected?.code||'')}${row?`&row=${encodeURIComponent(row)}`:''}`;
 const exportCsv=()=>{
  if(!profile)return;
  const blob=new Blob([liquidityCsv(profile,currency,effectiveBasis,mode,result.as_of_date)],{type:'text/csv;charset=utf-8'});
  const href=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=href;link.download=`liquidity-analytics-${result.as_of_date}-${currency}-${effectiveBasis}-${mode}.csv`;
  document.body.appendChild(link);link.click();link.remove();window.setTimeout(()=>URL.revokeObjectURL(href),1000);
 };

 return <>
  <PageHeading title="Liquidity analytics" subtitle="Trace a maturity-bucket position from its source lines to the approved bank-format ladder." action={<Stack direction="row" gap={1} flexWrap="wrap"><Button variant="outlined" startIcon={<DownloadRounded/>} disabled={!profile} onClick={exportCsv}>Export view</Button><Button variant="contained" endIcon={<ArrowForwardRounded/>} onClick={()=>nav(ladderLink())}>Open ladder</Button></Stack>}/>
  <ErrorMessage error={runs.error||previous.error}/>
  {result.rejected_count>0&&<Alert severity="warning" sx={{mb:2}}>{result.rejected_count} contracts were excluded. <Button size="small" onClick={()=>nav(`/results/${currentRun.id}?tab=controls`)}>Review controls</Button></Alert>}
  <Card sx={{p:{xs:2.2,md:2.8},mb:2.4,color:'white',background:'linear-gradient(115deg,#102B42 0%,#185568 55%,#257F77 100%)',border:0}}><Stack direction={{xs:'column',md:'row'}} justifyContent="space-between" alignItems={{md:'center'}} gap={1.5}><Box><Typography variant="overline" sx={{color:'#B5E7DC',letterSpacing:1.5}}>POSITION INTELLIGENCE</Typography><Typography variant="h5" fontWeight={750}>Where is the liquidity pressure building?</Typography><Typography variant="body2" sx={{color:'#D6E8E9',mt:.65}}>Select a bucket in the chart or table. Its numbers, product lines and historical bridge update together.</Typography></Box><Chip label={`${entity?.name||'Entity'} · ${dateLabel(result.as_of_date)}${entity?.is_mock?' · demo':''}`} sx={{bgcolor:'#D9F2E9',color:'#175C57',fontWeight:700}}/></Stack></Card>
  <Card sx={{p:2,mb:2.4}}><Stack direction="row" gap={1.4} flexWrap="wrap" alignItems="center">
   <Select size="small" value={currentRun.id} onChange={event=>{setRun(event.target.value);setSelectedCode('');setComparisonChoice('auto')}} inputProps={{'aria-label':'Calculation date'}} sx={{minWidth:185}}>{completed.map(run=><MenuItem key={run.id} value={run.id}>{dateLabel(run.as_of_date)} · {run.id.slice(0,8)}</MenuItem>)}</Select>
   <Select size="small" value={currency} onChange={event=>{setCurrency(event.target.value);setSelectedCode('')}} inputProps={{'aria-label':'Original currency'}} sx={{minWidth:130}}>{result.currencies.map(item=><MenuItem key={item} value={item}>{item} · original</MenuItem>)}</Select>
   <ToggleButtonGroup exclusive size="small" value={effectiveBasis} onChange={(_,value:CashFlowBasis|null)=>{if(value){setBasis(value);setSelectedCode('')}}}><ToggleButton value="contractual">Contractual</ToggleButton><ToggleButton value="behavioral" disabled={!availableBehavioral}>Behavioural</ToggleButton></ToggleButtonGroup>
   <ToggleButtonGroup exclusive size="small" value={mode} onChange={(_,value:CashFlowMode|null)=>value&&setMode(value)}><ToggleButton value="principal">Principal</ToggleButton><ToggleButton value="total">Principal + interest</ToggleButton></ToggleButtonGroup>
   <Select size="small" value={comparisonChoice} onChange={event=>setComparisonChoice(event.target.value)} inputProps={{'aria-label':'Compare with previous run'}} sx={{minWidth:180,ml:{lg:'auto'}}}><MenuItem value="auto">Compare previous date</MenuItem><MenuItem value="none">No comparison</MenuItem>{priorOptions.filter(run=>run.as_of_date!==currentRun.as_of_date).map(run=><MenuItem key={run.id} value={run.id}>{dateLabel(run.as_of_date)} · {run.id.slice(0,8)}</MenuItem>)}</Select>
  </Stack></Card>
  {!profile?<Alert severity="info">This run does not contain a compatible bank-format ladder for {currency}. Recalculate to unlock reconciled analysis.</Alert>:<>
   {!profile.reconciled&&<Alert severity="error" sx={{mb:2}}>The ladder totals do not reconcile to its gap rows. Investigate the saved result before using this analysis.</Alert>}
   <Box sx={{display:'grid',gridTemplateColumns:{xs:'repeat(2,minmax(0,1fr))',lg:'repeat(5,minmax(0,1fr))'},gap:1.5,mb:2.5}}>
    <Figure label="Lowest cumulative gap" value={compact(weakest?.cumulativeAfter||0)} full={money(weakest?.cumulativeAfter||0,currency)} note={`${weakest?.label} · ${currency} · after capacity`} tone={(weakest?.cumulativeAfter||0)<0?red:green}/>
    <Figure label="First negative bucket" value={firstDeficit?.label||'None modelled'} note="Cumulative after capacity" tone={firstDeficit?red:green}/>
    <Figure label="Peak obligations" value={compact((biggest?.outflows||0)+(biggest?.offBalance||0))} full={money((biggest?.outflows||0)+(biggest?.offBalance||0),currency)} note={`${biggest?.label} · ${currency} · outflows + off-balance-sheet`}/>
    <Figure label="Capacity position" value={compact(profile.capacityBalance)} full={money(profile.capacityBalance,currency)} note={`${currency} · Balance as of ${dateLabel(result.as_of_date)} · principal only`}/>
    <Figure label="Principal gap ratio" value={selected?.cushionPercent===null||!selected?'N/A':`${selected.cushionPercent.toFixed(1)}%`} note={`${selected?.label||'—'} · management metric, not LCR`} tone={(selected?.cushionPercent||0)<0?red:green}/>
   </Box>
   <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',lg:'minmax(0,1.8fr) minmax(340px,1fr)'},gap:2.5,mb:2.5}}>
    <Card><SectionHead title="Maturity runway" subtitle="Cumulative gap before and after counterbalancing capacity"/>
     <Box height={310} px={1.2} pb={1}><ResponsiveContainer width="100%" height="100%"><AreaChart data={profile.buckets} onClick={state=>{const point=(state as {activePayload?:{payload?:{code:string}}[]})?.activePayload?.[0]?.payload;if(point)setSelectedCode(point.code)}} margin={{left:0,right:18,bottom:5}}><defs><linearGradient id="liquidityAfterCapacity" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#298D7E" stopOpacity={.27}/><stop offset="100%" stopColor="#298D7E" stopOpacity={.01}/></linearGradient></defs><CartesianGrid vertical={false} stroke="#E7EEF3" strokeDasharray="3 4"/><XAxis dataKey="label" tick={{fontSize:10}} interval="preserveStartEnd"/><YAxis width={65} tickFormatter={(value:number)=>compact(value)} tick={{fontSize:10}}/><ReferenceLine y={0} stroke={red} strokeDasharray="4 4"/><Tooltip formatter={(value)=>money(Number(value),currency)}/><Legend wrapperStyle={{fontSize:11}}/><Area dataKey="cumulativeBefore" name="Before capacity" type="monotone" stroke="#8294A8" fill="transparent" strokeWidth={2} activeDot={{r:5}}/><Area dataKey="cumulativeAfter" name="After capacity" type="monotone" stroke={green} fill="url(#liquidityAfterCapacity)" strokeWidth={3} activeDot={{r:6}}/></AreaChart></ResponsiveContainer></Box>
     <Divider/><Typography variant="caption" color="text.secondary" px={2.3} py={1.3} display="block">The cumulative view sums scheduled bucket contributions. Capacity availability, encumbrance and reuse are not independently verified here.</Typography>
    </Card>
    <Card><SectionHead title={`Explain ${selected?.label||'bucket'}`} subtitle="Every amount comes from the same saved ladder"/>
     <Stack px={2.4} pb={2.4} gap={1.15}>{selected&&<>
      {([['Inflows',selected.inflows],['− Outflows',-selected.outflows],['− Off-balance-sheet',-selected.offBalance],['+ Counterbalancing capacity',selected.capacity]] as const).map(([label,value])=><Stack key={label} direction="row" justifyContent="space-between" gap={1}><Typography variant="body2" color="text.secondary">{label}</Typography><Typography variant="body2" fontWeight={700}>{money(value,currency)}</Typography></Stack>)}
      <Divider/><Stack direction="row" justifyContent="space-between"><Typography variant="body2" fontWeight={750}>Bucket gap after capacity</Typography><Typography variant="body2" fontWeight={800} color={selected.gapAfter<0?red:green}>{money(selected.gapAfter,currency)}</Typography></Stack>
      <Stack direction="row" justifyContent="space-between"><Typography variant="body2" color="text.secondary">Cumulative after capacity</Typography><Typography variant="body2" fontWeight={700}>{money(selected.cumulativeAfter,currency)}</Typography></Stack>
      <Typography variant="caption" color="text.secondary">Principal gap ratio = principal gap including capacity ÷ (as-of total outflow balance + signed as-of off-balance-sheet balance). {selected.cushionPercent===null?'The signed denominator is not positive, so the percentage is N/A.':'This is not regulatory LCR.'}</Typography>
      <Button variant="outlined" size="small" sx={{alignSelf:'start',mt:1}} endIcon={<OpenInNewRounded/>} onClick={()=>nav(ladderLink())}>Locate bucket in ladder</Button>
     </>}</Stack>
    </Card>
   </Box>
   <Card sx={{mb:2.5}}><SectionHead title="Scheduled flows and capacity" subtitle="Full-width maturity profile · select a bar to inspect that bucket"/>
    <Box height={315} px={{xs:1,md:2}} pb={1.5}><ResponsiveContainer width="100%" height="100%"><BarChart data={profile.buckets} onClick={state=>{const point=(state as {activePayload?:{payload?:{code:string}}[]})?.activePayload?.[0]?.payload;if(point)setSelectedCode(point.code)}} margin={{top:12,right:18,bottom:8,left:10}}><CartesianGrid vertical={false} stroke="#E7EEF3" strokeDasharray="3 4"/><XAxis dataKey="label" tick={{fontSize:10}} interval="preserveStartEnd"/><YAxis tickFormatter={(value:number)=>compact(value)} tick={{fontSize:10}} width={70}/><Tooltip formatter={(value)=>money(Number(value),currency)}/><Legend wrapperStyle={{fontSize:11}}/><Bar dataKey="inflows" name="Inflows" fill={green} maxBarSize={38}/><Bar dataKey="outflows" name="Outflows" fill="#6688C9" maxBarSize={38}/><Bar dataKey="offBalance" name="Off-balance-sheet" fill="#C18B50" maxBarSize={38}/><Bar dataKey="capacity" name="Capacity" fill="#54ACC4" maxBarSize={38}/></BarChart></ResponsiveContainer></Box>
   </Card>
   <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',lg:'minmax(0,1.15fr) minmax(0,1fr)'},gap:2.5,mb:2.5}}>
    <Card><SectionHead title="Movement bridge" subtitle={priorBucket?`${dateLabel(priorRun!.as_of_date)} → ${dateLabel(currentRun.as_of_date)} · ${selected?.label}`:'Compare with an earlier date to see what changed'}/>
     <Box px={2.4} pb={2.5}>{comparisonChoice==='none'?<Alert severity="info">Historical comparison is switched off.</Alert>:previous.isLoading?<Typography variant="body2">Loading prior run…</Typography>:!priorRun?<Alert severity="info">No earlier completed reporting date is available.</Alert>:!priorBucket?<Alert severity="info">The earlier run has a different currency, bucket configuration or missing ladder. It cannot be compared safely.</Alert>:<>
      <Stack direction="row" justifyContent="space-between" mb={1.6}><Typography variant="body2">Prior bucket gap</Typography><Typography variant="body2" fontWeight={700}>{money(priorBucket.gapAfter,currency)}</Typography></Stack>
      {compare.map(item=><Stack key={item.label} direction="row" justifyContent="space-between" gap={1} mb={1.3}><Typography variant="body2" color="text.secondary">{item.label} effect</Typography><Typography variant="body2" fontWeight={700} color={item.movement<0?red:green}>{money(item.movement,currency)}</Typography></Stack>)}
      <Divider sx={{my:1.5}}/><Stack direction="row" justifyContent="space-between"><Typography variant="body2" fontWeight={750}>Current bucket gap</Typography><Typography variant="body2" fontWeight={750}>{money(selected!.gapAfter,currency)}</Typography></Stack>
      {priorResult?.behavioral_assumption_set?.version!==result.behavioral_assumption_set?.version&&effectiveBasis==='behavioral'&&<Alert severity="warning" sx={{mt:2}}>Assumption-set versions differ; movement may reflect rule changes.</Alert>}
      <Typography variant="caption" color="text.secondary" display="block" mt={1.5}>The bridge is an exact arithmetic breakdown, not a claim about the business cause.</Typography>
     </>}</Box>
    </Card>
   </Box>
   <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',lg:'minmax(0,1.25fr) minmax(0,.75fr)'},gap:2.5,mb:2.5}}>
    <Card><SectionHead title="What makes up this bucket?" subtitle={`${selected?.label} · click a line to inspect its product types`} action={<Chip size="small" icon={<InsightsRounded/>} label="Ladder-backed"/>}/>
     <Box px={2} pb={2.2}>{sectionOrder.map(section=>{const lines=contributors?.filter(item=>item.section===section)||[];if(!lines.length)return null;return <Accordion key={`${selected?.code}-${section}`} disableGutters elevation={0} sx={{border:'1px solid #E6EBF1',borderRadius:'8px !important',mb:1,'&:before':{display:'none'}}}><AccordionSummary expandIcon={<ExpandMoreRounded/>}><Stack direction="row" justifyContent="space-between" width="100%" pr={1}><Typography variant="subtitle2">{sectionNames[section]}</Typography><Typography variant="body2" fontWeight={750}>{money(lines.reduce((sum,item)=>sum+item.amount,0),currency)}</Typography></Stack></AccordionSummary><AccordionDetails sx={{pt:0}}>{lines.map(line=><Box key={line.key} sx={{py:1,borderTop:'1px solid #EEF1F4'}}><Stack direction="row" justifyContent="space-between" gap={1} alignItems="center"><Button size="small" onClick={()=>nav(ladderLink(line.key))} endIcon={<ArrowForwardRounded sx={{fontSize:14}}/>} sx={{textTransform:'none',justifyContent:'start',textAlign:'left'}}>{line.label}</Button><Typography variant="body2" fontWeight={700}>{money(line.amount,currency)}</Typography></Stack>{line.childrenInBucket.map(child=><Stack key={child.key} direction="row" justifyContent="space-between" pl={2.2} py={.3}><Typography variant="caption" color="text.secondary">{child.label}</Typography><Typography variant="caption" fontWeight={650}>{money(child.amount,currency)}</Typography></Stack>)}</Box>)}</AccordionDetails></Accordion>})}{!contributors?.length&&<Typography variant="body2" color="text.secondary">No scheduled product line is present in this bucket.</Typography>}</Box>
    </Card>
    <Card><SectionHead title="Largest line movements" subtitle="Same bucket versus selected earlier run"/>
     <Stack px={2.4} pb={2.5} gap={1.4}>{priorBucket?movements.slice(0,6).map(item=><Box key={item.key}><Stack direction="row" justifyContent="space-between" gap={1}><Typography variant="body2">{item.label}</Typography><Typography variant="body2" fontWeight={750} color={item.contribution<0?red:green}>{money(item.contribution,currency)}</Typography></Stack><Typography variant="caption" color="text.secondary">{sectionNames[item.section]} · change in gap contribution</Typography></Box>):<Typography variant="body2" color="text.secondary">Select a comparable earlier run to see individual movements.</Typography>}{priorBucket&&!movements.length&&<Typography variant="body2" color="text.secondary">No product-line movement in this bucket.</Typography>}</Stack>
    </Card>
   </Box>
   <Card sx={{mb:3}}><SectionHead title="Maturity pressure monitor" subtitle="Choose a row to update every chart and explanation" action={<Button size="small" onClick={()=>setShowAll(!showAll)}>{showAll?'Show key buckets':'Show all buckets'}</Button>}/>
    <TableContainer><Table size="small"><TableHead><TableRow>{['Bucket','Inflows','Outflows + off-balance-sheet','Capacity','Gap after capacity','Cumulative after capacity','Cushion %'].map((heading,index)=><TableCell key={heading} align={index?'right':'left'}>{heading}</TableCell>)}</TableRow></TableHead><TableBody>{(showAll?profile.buckets:[...profile.buckets].sort((a,b)=>a.cumulativeAfter-b.cumulativeAfter).slice(0,6)).map(bucket=><TableRow key={bucket.code} hover selected={bucket.code===selected?.code} onClick={()=>setSelectedCode(bucket.code)} sx={{cursor:'pointer'}}><TableCell sx={{fontWeight:750}}>{bucket.label}</TableCell><TableCell align="right">{money(bucket.inflows,currency)}</TableCell><TableCell align="right">{money(bucket.outflows+bucket.offBalance,currency)}</TableCell><TableCell align="right">{money(bucket.capacity,currency)}</TableCell><TableCell align="right" sx={{color:bucket.gapAfter<0?red:green,fontWeight:650}}>{money(bucket.gapAfter,currency)}</TableCell><TableCell align="right" sx={{color:bucket.cumulativeAfter<0?red:green,fontWeight:750}}>{money(bucket.cumulativeAfter,currency)}</TableCell><TableCell align="right">{bucket.cushionPercent===null?'N/A':`${bucket.cushionPercent.toFixed(1)}%`}</TableCell></TableRow>)}</TableBody></Table></TableContainer>
   </Card>
   <Typography variant="caption" color="text.secondary" display="block" mb={2}>Cash-flow basis changes timing, not the underlying portfolio population. Balance as of {dateLabel(result.as_of_date)} is principal only. These indicators are management measures, not LCR, NSFR or an approved risk-appetite test.</Typography>
  </>}
 </>;
}
