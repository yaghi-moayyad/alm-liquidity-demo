import {useMemo,useState} from 'react';
import type {ReactNode} from 'react';
import {useQuery} from '@tanstack/react-query';
import {
  Alert,Box,Button,Card,Chip,Divider,FormControlLabel,MenuItem,Select,Stack,Switch,
  Table,TableBody,TableCell,TableHead,TableRow,ToggleButton,ToggleButtonGroup,Typography,
} from '@mui/material';
import {
  AccountBalanceWalletRounded,ArrowDownwardRounded,ArrowForwardRounded,ArrowUpwardRounded,
  CalendarMonthRounded,CheckCircleRounded,CompareArrowsRounded,ErrorOutlineRounded,
  InsightsRounded,LayersRounded,ShieldOutlined,SouthEastRounded,WarningAmberRounded,
} from '@mui/icons-material';
import {Bar,BarChart,CartesianGrid,ComposedChart,Line,ReferenceLine,ResponsiveContainer,Tooltip as ChartTooltip,XAxis,YAxis} from 'recharts';
import {api,compact,dateLabel,money} from '../api';
import {useWorkspace} from '../context';
import {ErrorMessage,Loading,PageHeading,SectionHead} from '../components/Common';
import type {BankLadder,LadderDetail,LadderRow,Run} from '../types';

type CashFlowMode='principal'|'total';
type AnalyticsBasis='contractual'|'behavioral';
type Horizon='all'|'30d'|'1y';
type ValuedRow=Pick<LadderRow,'principal'|'total'>|Pick<LadderDetail,'principal'|'total'>;

const n=(value:string|number|undefined|null)=>Number(value||0);
const sum=(values:number[])=>values.reduce((total,value)=>total+value,0);
const percent=(value:number,total:number)=>total?`${(100*value/total).toFixed(1)}%`:'—';
const signedMoney=(value:number,currency:string)=>`${value>0?'+':''}${money(value,currency)}`;

function values(row:ValuedRow|undefined,mode:CashFlowMode){return row?(mode==='principal'?row.principal:row.total).map(n):[];}
function rowByKey(ladder:BankLadder,key:string){return ladder.rows.find(row=>row.key===key);}

type BucketPoint={
  code:string;label:string;inflows:number;outflows:number;offBalance:number;net:number;
  cumulative:number;capacity:number;afterCapacity:number;
};
type Driver={label:string;category:string;amount:number;share:number};
type LiquidityMetrics={
  ladder:BankLadder;rows:LadderRow[];bucketData:BucketPoint[];capacityRows:LadderRow[];
  buffer:number;worstPoint:BucketPoint;worstAfterPoint:BucketPoint;firstNegative?:BucketPoint;
  shortTermOutflows:number;topMaturity:BucketPoint;fundingRows:LadderRow[];fundingTotal:number;
  drivers:Driver[];
};

function buildMetrics(ladder:BankLadder|undefined,mode:CashFlowMode):LiquidityMetrics|undefined{
  if(!ladder?.buckets?.length)return undefined;
  const row=(key:string)=>rowByKey(ladder,key);
  const inflows=values(row('total_inflows'),mode);
  const outflows=values(row('total_outflows'),mode);
  const offBalance=values(row('total_off_balance_sheet'),mode);
  const net=values(row('contractual_gap'),mode);
  const cumulative=values(row('cumulative_contractual_gap'),mode);
  const capacity=values(row('total_counterbalancing_capacity'),mode);
  const afterCapacity=values(row('cumulative_gap_including_capacity'),mode);
  const bucketData=ladder.buckets.map((bucket,index)=>({
    code:bucket.code,label:bucket.label,inflows:inflows[index]||0,outflows:outflows[index]||0,
    offBalance:offBalance[index]||0,net:net[index]||0,cumulative:cumulative[index]||0,
    capacity:capacity[index]||0,afterCapacity:afterCapacity[index]||0,
  }));
  const worstPoint=bucketData.reduce((lowest,point)=>point.cumulative<lowest.cumulative?point:lowest,bucketData[0]);
  const worstAfterPoint=bucketData.reduce((lowest,point)=>point.afterCapacity<lowest.afterCapacity?point:lowest,bucketData[0]);
  const firstNegative=bucketData.find(point=>point.cumulative<0);
  const capacityRows=['cash_central_bank','marketable_securities','government_capacity']
    .map(key=>row(key)).filter((item):item is LadderRow=>{
      if(!item)return false;
      return n(item.balance)>0||values(item,mode).some(value=>value!==0);
    });
  const buffer=n(row('total_counterbalancing_capacity')?.balance)||sum(capacityRows.map(item=>n(item.balance)));
  const oneMonthIndex=Math.max(0,ladder.buckets.findIndex(bucket=>bucket.code==='1m'));
  const shortTermOutflows=sum(bucketData.slice(0,oneMonthIndex+1).map(point=>point.outflows+point.offBalance));
  const topMaturity=bucketData.reduce((largest,point)=>point.outflows+point.offBalance>largest.outflows+largest.offBalance?point:largest,bucketData[0]);
  const fundingRows=ladder.rows.filter(item=>item.section==='outflows'&&item.kind==='normal'&&n(item.balance)>0)
    .sort((left,right)=>n(right.balance)-n(left.balance));
  const fundingTotal=sum(fundingRows.map(item=>n(item.balance)));
  const driverRows=ladder.rows.filter(item=>(item.section==='outflows'||item.section==='off_balance_sheet')&&item.kind==='normal');
  const throughLowPoint=bucketData.indexOf(worstPoint);
  const rawDrivers=driverRows.flatMap(item=>{
    const children=item.children?.length?item.children:[item];
    return children.map(child=>({
      label:child.label,category:item.section==='off_balance_sheet'?'Off-balance sheet':item.label,
      amount:sum(values(child,mode).slice(0,throughLowPoint+1)),
    }));
  }).filter(item=>item.amount>0).sort((left,right)=>right.amount-left.amount);
  const driverTotal=sum(rawDrivers.map(item=>item.amount));
  const drivers=rawDrivers.slice(0,6).map(item=>({...item,share:driverTotal?item.amount/driverTotal:0}));
  return {ladder,rows:ladder.rows,bucketData,capacityRows,buffer,worstPoint,worstAfterPoint,firstNegative,
    shortTermOutflows,topMaturity,fundingRows,fundingTotal,drivers};
}

function currentRunLabel(run:Run){return `${dateLabel(run.as_of_date)} · ${run.id.slice(0,8)}`;}

function MetricTile({label,value,detail,tone='blue',icon:Icon}:{label:string;value:string;detail:string;tone?:'blue'|'green'|'amber'|'red';icon:typeof InsightsRounded}){
  const palette={blue:{main:'#2D5BDE',soft:'#EAF0FF'},green:{main:'#168B6C',soft:'#E8F5EF'},amber:{main:'#B77728',soft:'#FFF3DF'},red:{main:'#C84F54',soft:'#FCEBED'}}[tone];
  return <Card sx={{p:2.35,minWidth:0,position:'relative',overflow:'hidden','&:before':{content:'""',position:'absolute',left:0,top:0,bottom:0,width:4,bgcolor:palette.main}}}>
    <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1}><Typography sx={{fontSize:11.5,color:'text.secondary',fontWeight:600}}>{label}</Typography><Box sx={{display:'flex',p:.8,borderRadius:1.8,bgcolor:palette.soft,color:palette.main}}><Icon sx={{fontSize:17}}/></Box></Stack>
    <Typography sx={{fontSize:{xs:22,md:28},fontWeight:680,letterSpacing:-.8,mt:1.6,color:palette.main,fontVariantNumeric:'tabular-nums'}}>{value}</Typography>
    <Typography variant="caption" color="text.secondary" sx={{display:'block',mt:.7,lineHeight:1.45}}>{detail}</Typography>
  </Card>;
}

function Indicator({children,tone='neutral'}:{children:ReactNode;tone?:'neutral'|'success'|'warning'|'error'}){
  const colors={neutral:{bg:'#EEF3FC',fg:'#4167C7'},success:{bg:'#E8F5EF',fg:'#168B6C'},warning:{bg:'#FFF3DF',fg:'#A66E20'},error:{bg:'#FCEBED',fg:'#B9474D'}}[tone];
  return <Chip size="small" label={children} sx={{bgcolor:colors.bg,color:colors.fg,fontWeight:700}}/>;
}

function RunwayChart({data,currency,worstLabel,horizon}:{data:BucketPoint[];currency:string;worstLabel:string;horizon:Horizon}){
  const end=horizon==='30d'?Math.max(1,data.findIndex(point=>point.code==='1m')+1):horizon==='1y'?Math.max(1,data.findIndex(point=>point.code==='1y')+1):data.length;
  const visible=data.slice(0,end);
  const low=visible.find(point=>point.label===worstLabel);
  return <Box>
    <Stack direction="row" gap={2} sx={{px:3,pb:1.5,flexWrap:'wrap'}}>
      {[["#168E81","Inflows"],["#C5D2F2","Outflows + OBS"],["#4167C7","Cumulative gap"],["#168B6C","After capacity"]].map(([color,label])=><Stack direction="row" alignItems="center" gap={.7} key={label}><Box sx={{width:8,height:8,bgcolor:color,borderRadius:'2px'}}/><Typography variant="caption" color="text.secondary">{label}</Typography></Stack>)}
    </Stack>
    <Box sx={{height:326,px:1}} role="img" aria-label={`Liquidity runway in ${currency}`}>
      <ResponsiveContainer width="100%" height="100%"><ComposedChart data={visible} margin={{top:12,right:12,left:0,bottom:8}}>
        <CartesianGrid strokeDasharray="3 4" vertical={false} stroke="#EBEFF4"/>
        <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{fill:'#8A98A9',fontSize:9}} interval="preserveStartEnd"/>
        <YAxis yAxisId="flows" tickFormatter={value=>compact(value)} axisLine={false} tickLine={false} tick={{fill:'#8A98A9',fontSize:10}} width={65}/>
        <YAxis yAxisId="gap" orientation="right" tickFormatter={value=>compact(value)} axisLine={false} tickLine={false} tick={{fill:'#8394B0',fontSize:10}} width={65}/>
        <ReferenceLine yAxisId="gap" y={0} stroke="#AAB6C3" strokeDasharray="3 3"/>
        {low&&<ReferenceLine x={low.label} stroke="#C84F54" strokeDasharray="2 3"/>}
        <ChartTooltip content={({active,payload,label})=>active&&payload?.length?<Box sx={{bgcolor:'white',boxShadow:'0 8px 30px #122B4022',p:1.8,border:'1px solid #E3EAF2',borderRadius:2,minWidth:205}}><Typography variant="subtitle2" mb={.9}>{label} · {currency}</Typography>{payload.filter(point=>point.dataKey!=='net').map(point=><Stack key={String(point.dataKey)} direction="row" justifyContent="space-between" gap={2}><Typography variant="caption" sx={{color:point.color}}>{point.name}</Typography><Typography variant="caption" fontWeight={700}>{money(Number(point.value),currency)}</Typography></Stack>)}</Box>:null}/>
        <Bar isAnimationActive={false} yAxisId="flows" dataKey="inflows" name="Inflows" fill="#168E81" radius={[3,3,0,0]} maxBarSize={17}/>
        <Bar isAnimationActive={false} yAxisId="flows" dataKey="outflows" name="Outflows + OBS" fill="#C5D2F2" stackId="outflows" radius={[3,3,0,0]} maxBarSize={17}/>
        <Bar isAnimationActive={false} yAxisId="flows" dataKey="offBalance" name="Off-balance sheet" fill="#A7B8DD" stackId="outflows" maxBarSize={17}/>
        <Line isAnimationActive={false} yAxisId="gap" dataKey="cumulative" name="Cumulative gap" stroke="#4167C7" strokeWidth={2.4} dot={false} type="monotone"/>
        <Line isAnimationActive={false} yAxisId="gap" dataKey="afterCapacity" name="After capacity" stroke="#168B6C" strokeWidth={2.4} strokeDasharray="6 4" dot={false} type="monotone"/>
      </ComposedChart></ResponsiveContainer>
    </Box>
  </Box>;
}

function AmountBar({label,value,total,currency,color,caption}:{label:string;value:number;total:number;currency:string;color:string;caption?:string}){
  return <Box><Stack direction="row" justifyContent="space-between" alignItems="baseline" gap={1}><Box><Typography variant="body2" fontWeight={650}>{label}</Typography>{caption&&<Typography variant="caption" color="text.secondary">{caption}</Typography>}</Box><Typography variant="body2" fontWeight={700} sx={{fontVariantNumeric:'tabular-nums',whiteSpace:'nowrap'}}>{money(value,currency)}</Typography></Stack><Box sx={{height:7,bgcolor:'#EDF1F5',borderRadius:99,overflow:'hidden',mt:.8}}><Box sx={{height:'100%',width:`${total?Math.min(100,100*value/total):0}%`,bgcolor:color,borderRadius:99}}/></Box></Box>;
}

function Change({label,value,currency,invert=false}:{label:string;value:number;currency:string;invert?:boolean}){
  const good=invert?value>0:value<0;
  const neutral=Math.abs(value)<0.00001;
  const color=neutral?'text.primary':good?'success.main':'error.main';
  return <Box sx={{p:1.35,borderRadius:2,bgcolor:'#FAFBFD',border:'1px solid #EEF1F5'}}><Typography variant="caption" color="text.secondary">{label}</Typography><Stack direction="row" alignItems="center" gap={.5} mt={.4}><Box sx={{display:'flex',color}}>{neutral?<CompareArrowsRounded sx={{fontSize:15}}/>:value>0?<ArrowUpwardRounded sx={{fontSize:15}}/>:<ArrowDownwardRounded sx={{fontSize:15}}/>}</Box><Typography variant="body2" fontWeight={750} color={color}>{signedMoney(value,currency)}</Typography></Stack></Box>;
}

export default function LiquidityAnalytics(){
  const {entity}=useWorkspace();
  const runs=useQuery({queryKey:['runs',entity?.slug],queryFn:()=>api.runs(entity!.slug),enabled:!!entity});
  const [chosenRunId,setChosenRunId]=useState('');
  const [chosenCurrency,setChosenCurrency]=useState('');
  const [mode,setMode]=useState<CashFlowMode>('total');
  const [basis,setBasis]=useState<AnalyticsBasis>('contractual');
  const [horizon,setHorizon]=useState<Horizon>('all');
  const [compare,setCompare]=useState(false);
  const completed=useMemo(()=>[...(runs.data?.runs||[])]
    .filter(run=>['completed','completed_with_exceptions'].includes(run.status))
    .sort((left,right)=>new Date(right.finished||right.created).getTime()-new Date(left.finished||left.created).getTime()),[runs.data?.runs]);
  const activeRunId=completed.some(run=>run.id===chosenRunId)?chosenRunId:completed[0]?.id;
  const run=useQuery({queryKey:['run',activeRunId],queryFn:()=>api.run(activeRunId!),enabled:!!activeRunId});
  const activeIndex=completed.findIndex(item=>item.id===activeRunId);
  const comparisonCandidate=activeIndex>=0?completed[activeIndex+1]:undefined;
  const comparisonRun=useQuery({queryKey:['run',comparisonCandidate?.id],queryFn:()=>api.run(comparisonCandidate!.id),enabled:compare&&!!comparisonCandidate});

  if(runs.isLoading||run.isLoading)return <Loading/>;
  if(runs.error||run.error)return <ErrorMessage error={runs.error||run.error}/>;
  if(!entity||!activeRunId||!run.data?.result)return <><PageHeading title="Liquidity analytics" subtitle="Management-ready buffer, gap and concentration analytics from saved calculation snapshots."/><Alert severity="info">Run a liquidity calculation first. This page will analyse the completed run without changing its result.</Alert></>;

  const result=run.data.result;
  const currencies=result.currencies?.length?result.currencies:Object.keys(result.bank_ladder||{});
  const currency=currencies.includes(chosenCurrency)?chosenCurrency:(currencies.includes(entity.base_currency)?entity.base_currency:currencies[0]||entity.base_currency);
  const behaviouralAvailable=Boolean(result.behavioral_bank_ladder?.[currency]);
  const activeBasis:AnalyticsBasis=basis==='behavioral'&&behaviouralAvailable?'behavioral':'contractual';
  const ladder=activeBasis==='behavioral'?result.behavioral_bank_ladder?.[currency]:result.bank_ladder?.[currency];
  const metrics=buildMetrics(ladder,mode);
  if(!metrics)return <><PageHeading title="Liquidity analytics" subtitle={`${entity.name} · saved run ${run.data.id.slice(0,8)}`}/><Alert severity="info">This historical run was created before detailed liquidity analytics were available. Create a new run to view this cockpit.</Alert></>;

  const residual=metrics.worstAfterPoint.afterCapacity;
  const bufferDependent=metrics.worstPoint.cumulative<0&&residual>=0;
  const bufferCoverage=metrics.worstPoint.cumulative<0?Math.min(100,100*Math.max(0,metrics.buffer/Math.abs(metrics.worstPoint.cumulative))):100;
  const capacityAppliedAtLow=Math.max(0,metrics.worstPoint.afterCapacity-metrics.worstPoint.cumulative);
  const topFunding=metrics.fundingRows[0];
  const previousResult=comparisonRun.data?.result;
  const previousLadder=previousResult?(activeBasis==='behavioral'?previousResult.behavioral_bank_ladder?.[currency]:previousResult.bank_ladder?.[currency]):undefined;
  const previousMetrics=buildMetrics(previousLadder,mode);
  const currencyPositions=currencies.map(item=>{
    const candidate=activeBasis==='behavioral'&&result.behavioral_bank_ladder?.[item]?result.behavioral_bank_ladder[item]:result.bank_ladder?.[item];
    const itemMetrics=buildMetrics(candidate,mode);
    return {currency:item,metrics:itemMetrics};
  }).filter((item):item is {currency:string;metrics:LiquidityMetrics}=>Boolean(item.metrics));
  const riskTone=residual<0?'error':bufferDependent?'warning':'success';
  const basisLabel=activeBasis==='behavioral'?'behavioural':'contractual';
  const riskMessage=residual<0
    ?`Immediate attention: reported counterbalancing capacity leaves a ${money(Math.abs(residual),currency)} cumulative shortfall at ${metrics.worstAfterPoint.label}.`
    :bufferDependent
      ?`Buffer-dependent position: the ${basisLabel} low point at ${metrics.worstPoint.label} is covered by the saved counterbalancing capacity.`
      :`Stable ${basisLabel} profile: no negative cumulative gap appears across the saved ladder horizon.`;

  return <>
    <PageHeading title="Liquidity analytics" subtitle={`${entity.name} · ${dateLabel(run.data.as_of_date)} · management view built from a locked run snapshot`} action={<Indicator tone="neutral">Saved calculation · {run.data.id.slice(0,8)}</Indicator>}/>

    <Card sx={{mb:3,overflow:'hidden',borderColor:'#DCE6FA'}}>
      <Box sx={{p:{xs:2,md:2.6},background:'linear-gradient(112deg, #F4F7FF 0%, #FFFFFF 54%, #F0FAF7 100%)'}}>
        <Stack direction={{xs:'column',xl:'row'}} gap={2.5} justifyContent="space-between" alignItems={{xl:'end'}}>
          <Box><Stack direction="row" alignItems="center" gap={1} mb={.8}><Box sx={{display:'flex',p:.7,borderRadius:1.5,bgcolor:'#E7EEFF',color:'primary.main'}}><InsightsRounded sx={{fontSize:18}}/></Box><Typography variant="subtitle2">Liquidity risk position</Typography></Stack><Typography variant="body2" color="text.secondary" sx={{maxWidth:630}}>Use the controls to explore the persisted result by currency, cash-flow basis and horizon. Changing a control updates the analysis immediately; it never recalculates or overwrites the run.</Typography></Box>
          <Stack direction={{xs:'column',sm:'row'}} gap={1.2} flexWrap="wrap" alignItems={{sm:'end'}}>
            <Box><Typography variant="caption" color="text.secondary" display="block" mb={.5}>Saved calculation</Typography><Select size="small" value={activeRunId} onChange={event=>{setChosenRunId(event.target.value);setCompare(false)}} sx={{minWidth:205}} inputProps={{'aria-label':'Saved calculation'}}>{completed.map(item=><MenuItem key={item.id} value={item.id}>{currentRunLabel(item)}</MenuItem>)}</Select></Box>
            <Box><Typography variant="caption" color="text.secondary" display="block" mb={.5}>Original currency</Typography><Select size="small" value={currency} onChange={event=>setChosenCurrency(event.target.value)} sx={{minWidth:118}} inputProps={{'aria-label':'Original currency'}}>{currencies.map(item=><MenuItem key={item} value={item}>{item}</MenuItem>)}</Select></Box>
            <Box><Typography variant="caption" color="text.secondary" display="block" mb={.5}>Cash-flow basis</Typography><ToggleButtonGroup exclusive size="small" value={activeBasis} onChange={(_,value)=>value&&setBasis(value)}><ToggleButton value="contractual">Contractual</ToggleButton><ToggleButton value="behavioral" disabled={!behaviouralAvailable}>Behavioural</ToggleButton></ToggleButtonGroup></Box>
            <Box><Typography variant="caption" color="text.secondary" display="block" mb={.5}>Amounts shown</Typography><ToggleButtonGroup exclusive size="small" value={mode} onChange={(_,value)=>value&&setMode(value)}><ToggleButton value="principal">Principal</ToggleButton><ToggleButton value="total">Principal + interest</ToggleButton></ToggleButtonGroup></Box>
          </Stack>
        </Stack>
      </Box>
    </Card>

    <Card sx={{mb:3,p:{xs:2,md:2.5},borderColor:riskTone==='error'?'#F2D5D7':riskTone==='warning'?'#F0E0C6':'#D7EDE5',background:riskTone==='error'?'linear-gradient(100deg,#FFF9F9,#FFFFFF)':riskTone==='warning'?'linear-gradient(100deg,#FFFDF7,#FFFFFF)':'linear-gradient(100deg,#F6FCF9,#FFFFFF)'}}>
      <Stack direction={{xs:'column',md:'row'}} gap={2} alignItems={{md:'center'}}><Box sx={{display:'flex',p:1.05,borderRadius:2,bgcolor:riskTone==='error'?'#FCEBED':riskTone==='warning'?'#FFF3DF':'#E8F5EF',color:riskTone==='error'?'error.main':riskTone==='warning'?'warning.main':'success.main'}}>{riskTone==='error'?<ErrorOutlineRounded/>:riskTone==='warning'?<WarningAmberRounded/>:<CheckCircleRounded/>}</Box><Box flex={1}><Typography variant="subtitle2">Management readout</Typography><Typography variant="body2" color="text.secondary" mt={.35}>{riskMessage}</Typography></Box><Indicator tone={riskTone}>{riskTone==='error'?'Residual gap':riskTone==='warning'?'Buffer dependent':'Within reported capacity'}</Indicator></Stack>
    </Card>

    <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',sm:'repeat(2, minmax(0,1fr))',xl:'repeat(4, minmax(0,1fr)'},gap:2,mb:3}}>
      <MetricTile label="Worst cumulative gap" value={money(metrics.worstPoint.cumulative,currency)} detail={metrics.firstNegative?`${metrics.worstPoint.label} · first negative at ${metrics.firstNegative.label}`:`${metrics.worstPoint.label} · no negative point in the saved horizon`} tone={metrics.worstPoint.cumulative<0?'red':'green'} icon={SouthEastRounded}/>
      <MetricTile label="Position after capacity" value={money(residual,currency)} detail={`${metrics.worstAfterPoint.label} · lowest point after reported capacity`} tone={residual<0?'red':bufferDependent?'amber':'green'} icon={ShieldOutlined}/>
      <MetricTile label="Available liquidity buffer" value={money(metrics.buffer,currency)} detail={`${bufferCoverage.toFixed(0)}% of the pre-capacity low point covered`} tone="blue" icon={AccountBalanceWalletRounded}/>
      <MetricTile label="30-day outflow pressure" value={money(metrics.shortTermOutflows,currency)} detail="Open maturity through 1 month · includes off-balance-sheet items" tone="amber" icon={CalendarMonthRounded}/>
    </Box>

    <Card sx={{mb:3}}>
      <SectionHead title="Liquidity runway" subtitle="Net contractual flows and cumulative position across the selected reporting horizon." action={<ToggleButtonGroup exclusive size="small" value={horizon} onChange={(_,value)=>value&&setHorizon(value)}><ToggleButton value="30d">30 days</ToggleButton><ToggleButton value="1y">1 year</ToggleButton><ToggleButton value="all">Full horizon</ToggleButton></ToggleButtonGroup>}/>
      <RunwayChart data={metrics.bucketData} currency={currency} worstLabel={metrics.worstPoint.label} horizon={horizon}/>
      <Box sx={{px:3,py:1.6,bgcolor:'#FAFBFD',borderTop:'1px solid',borderColor:'divider'}}><Typography variant="caption" color="text.secondary">The blue line shows the cumulative contractual gap. The dashed green line reflects saved counterbalancing capacity at its reported timing. It is a liquidity-gap view, not a forecasted cash balance or regulatory LCR result.</Typography></Box>
    </Card>

    <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',xl:'minmax(0,1.14fr) minmax(0,.86fr)'},gap:3,mb:3}}>
      <Card>
        <SectionHead title="Liquidity buffer & contingency capacity" subtitle="Reported usable capacity available to offset the contractual ladder." action={<Indicator tone={residual<0?'error':'success'}>{residual<0?'Action required':'Coverage visible'}</Indicator>}/>
        <Box sx={{px:2.7,pb:2.7}}>
          <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',sm:'repeat(3,1fr)'},gap:1.3,mb:2.7}}>
            {[["Reported buffer",metrics.buffer,"#2D5BDE"],["Applied at low point",capacityAppliedAtLow,"#168B6C"],["Residual after capacity",Math.max(0,-residual),residual<0?'#C84F54':'#168B6C']].map(([label,value,color])=><Box key={String(label)} sx={{p:1.5,borderRadius:2,bgcolor:'#FAFBFD',border:'1px solid #EEF1F5'}}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" fontWeight={750} color={String(color)} mt={.35}>{money(Number(value),currency)}</Typography></Box>)}
          </Box>
          <Stack gap={2}>{metrics.capacityRows.map((item,index)=><AmountBar key={item.key} label={item.label} value={n(item.balance)} total={metrics.buffer} currency={currency} color={['#2D5BDE','#168E81','#7E75CC'][index]||'#7890B6'} caption={`${percent(n(item.balance),metrics.buffer)} of reported buffer`}/>)}</Stack>
          {!metrics.capacityRows.some(item=>n(item.balance))&&<Alert severity="info" sx={{mt:2}}>No counterbalancing capacity is reported in this saved run.</Alert>}
          <Alert severity={residual<0?'error':'info'} sx={{mt:2.4}}>{residual<0?'The saved capacity does not cover the low point. Use the contingency-funding plan and investigate the driver panel before management escalation.':'Capacity is displayed as reported in this run. Haircut, encumbrance and operational-readiness breakdowns become separately analytical when those source fields are populated and retained in the published feed.'}</Alert>
        </Box>
      </Card>

      <Card>
        <SectionHead title="Contingency funding view" subtitle="A clear management sequence based on available capacity."/>
        <Box sx={{px:2.7,pb:2.7}}>
          <Stack gap={1.65}>{[...metrics.capacityRows].sort((left,right)=>n(right.balance)-n(left.balance)).map((item,index)=><Stack key={item.key} direction="row" gap={1.2} alignItems="center"><Chip size="small" label={index+1} color="primary"/><Box flex={1}><Typography variant="body2" fontWeight={700}>{item.label}</Typography><Typography variant="caption" color="text.secondary">Deploy subject to eligibility, operational availability and internal policy.</Typography></Box><Typography variant="body2" fontWeight={750} sx={{whiteSpace:'nowrap'}}>{compact(item.balance)} {currency}</Typography></Stack>)}</Stack>
          {!metrics.capacityRows.length&&<Typography variant="body2" color="text.secondary">No capacity sources are available in this run.</Typography>}
          <Divider sx={{my:2.25}}/>
          <Stack direction="row" gap={1.1} alignItems="center"><Box sx={{display:'flex',color:residual<0?'error.main':'success.main'}}>{residual<0?<WarningAmberRounded/>:<CheckCircleRounded/>}</Box><Box><Typography variant="body2" fontWeight={700}>{residual<0?'Residual shortfall remains':'No residual gap after capacity'}</Typography><Typography variant="caption" color="text.secondary">{residual<0?`Residual low point: ${money(Math.abs(residual),currency)}.`:'Continue to monitor maturity concentration and currency positions.'}</Typography></Box></Stack>
        </Box>
      </Card>
    </Box>

    <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',xl:'minmax(0,1.06fr) minmax(0,.94fr)'},gap:3,mb:3}}>
      <Card>
        <SectionHead title="Cash-flow drivers to the low point" subtitle={`Largest outflows accumulated through ${metrics.worstPoint.label}. Product detail comes from the saved ladder hierarchy.`}/>
        <Box sx={{px:2.7,pb:2.7}}>{metrics.drivers.length?<Stack gap={1.65}>{metrics.drivers.map((driver,index)=><Box key={`${driver.category}-${driver.label}`}><Stack direction="row" justifyContent="space-between" gap={1} alignItems="baseline"><Box sx={{minWidth:0}}><Typography variant="body2" fontWeight={700} noWrap>{driver.label}</Typography><Typography variant="caption" color="text.secondary">{driver.category}</Typography></Box><Stack direction="row" alignItems="center" gap={.8}><Typography variant="caption" color="text.secondary">{(driver.share*100).toFixed(1)}%</Typography><Typography variant="body2" fontWeight={750} sx={{whiteSpace:'nowrap'}}>{money(driver.amount,currency)}</Typography></Stack></Stack><Box sx={{height:6,bgcolor:'#EEF1F5',borderRadius:99,overflow:'hidden',mt:.6}}><Box sx={{height:'100%',width:`${Math.max(5,driver.share*100)}%`,bgcolor:index===0?'#C84F54':'#7D91BF',borderRadius:99}}/></Box></Box>)}</Stack>:<Alert severity="info">No dated product-level outflow drivers are available in the selected run.</Alert>}</Box>
      </Card>

      <Card>
        <SectionHead title="Maturity concentration" subtitle="Where contractual outflow pressure is concentrated by bucket." action={<Indicator tone="warning">Peak · {metrics.topMaturity.label}</Indicator>}/>
        <Box sx={{height:268,px:1,pb:1}}><ResponsiveContainer width="100%" height="100%"><BarChart data={metrics.bucketData.map(point=>({...point,pressure:point.outflows+point.offBalance}))} margin={{top:12,right:12,left:0,bottom:6}}><CartesianGrid strokeDasharray="3 4" vertical={false} stroke="#EBEFF4"/><XAxis dataKey="label" axisLine={false} tickLine={false} tick={{fill:'#8A98A9',fontSize:9}} interval="preserveStartEnd"/><YAxis tickFormatter={value=>compact(value)} axisLine={false} tickLine={false} tick={{fill:'#8A98A9',fontSize:10}} width={65}/><ChartTooltip content={({active,payload,label})=>active&&payload?.[0]?<Box sx={{bgcolor:'white',boxShadow:'0 8px 30px #122B4022',p:1.5,border:'1px solid #E3EAF2',borderRadius:2}}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" fontWeight={750}>{money(Number(payload[0].value),currency)}</Typography></Box>:null}/><Bar isAnimationActive={false} dataKey="pressure" name="Outflows + OBS" fill="#B77728" radius={[4,4,0,0]} maxBarSize={28}/></BarChart></ResponsiveContainer></Box>
        <Box sx={{px:2.7,py:1.55,bgcolor:'#FFFBF5',borderTop:'1px solid #F3E8D7'}}><Typography variant="caption" color="text.secondary">Peak maturity pressure: <b>{money(metrics.topMaturity.outflows+metrics.topMaturity.offBalance,currency)}</b> in <b>{metrics.topMaturity.label}</b>. Assess this against the bank’s approved concentration and survival-horizon thresholds.</Typography></Box>
      </Card>
    </Box>

    <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',xl:'minmax(0,1.1fr) minmax(0,.9fr)'},gap:3,mb:3}}>
      <Card>
        <SectionHead title="Funding category concentration" subtitle="A transparent category-level view; single-name concentration is only shown when source counterparty data is published." action={topFunding?<Indicator tone="neutral">Largest · {percent(n(topFunding.balance),metrics.fundingTotal)}</Indicator>:undefined}/>
        {metrics.fundingRows.length?<Table size="small"><TableHead><TableRow><TableCell>Funding category</TableCell><TableCell align="right">As-of balance</TableCell><TableCell align="right">Share</TableCell></TableRow></TableHead><TableBody>{metrics.fundingRows.slice(0,6).map(item=><TableRow key={item.key} hover><TableCell><Typography variant="body2" fontWeight={650}>{item.label}</Typography></TableCell><TableCell align="right" sx={{fontVariantNumeric:'tabular-nums'}}>{money(item.balance,currency)}</TableCell><TableCell align="right"><Chip size="small" label={percent(n(item.balance),metrics.fundingTotal)} sx={{bgcolor:'#EEF3FC',color:'#4167C7'}}/></TableCell></TableRow>)}</TableBody></Table>:<Box p={2.7}><Alert severity="info">No dated funding positions are present in this run.</Alert></Box>}
        <Box sx={{px:2.7,py:1.6,bgcolor:'#FAFBFD',borderTop:'1px solid',borderColor:'divider'}}><Typography variant="caption" color="text.secondary">Counterparty and counterparty-group fields are accepted by the calculation input, but this view intentionally does not fabricate single-name concentration when they are not available in the saved result.</Typography></Box>
      </Card>

      <Card>
        <SectionHead title="Currency liquidity ladder" subtitle="Original-currency positions are deliberately not aggregated without FX translation."/>
        <Table size="small"><TableHead><TableRow><TableCell>Currency</TableCell><TableCell align="right">Worst gap</TableCell><TableCell align="right">After capacity</TableCell></TableRow></TableHead><TableBody>{currencyPositions.map(item=><TableRow key={item.currency} hover selected={item.currency===currency}><TableCell><Stack direction="row" gap={.8} alignItems="center"><Box sx={{width:8,height:8,borderRadius:'50%',bgcolor:item.metrics.worstAfterPoint.afterCapacity<0?'error.main':item.metrics.worstPoint.cumulative<0?'warning.main':'success.main'}}/><Typography variant="body2" fontWeight={750}>{item.currency}</Typography></Stack></TableCell><TableCell align="right" sx={{color:item.metrics.worstPoint.cumulative<0?'error.main':undefined,fontVariantNumeric:'tabular-nums'}}>{money(item.metrics.worstPoint.cumulative,item.currency)}</TableCell><TableCell align="right" sx={{color:item.metrics.worstAfterPoint.afterCapacity<0?'error.main':'success.main',fontVariantNumeric:'tabular-nums'}}>{money(item.metrics.worstAfterPoint.afterCapacity,item.currency)}</TableCell></TableRow>)}</TableBody></Table>
        <Box sx={{px:2.7,py:1.6,bgcolor:'#FAFBFD',borderTop:'1px solid',borderColor:'divider'}}><Typography variant="caption" color="text.secondary">Select a currency above to inspect its full cash-flow runway and concentrations.</Typography></Box>
      </Card>
    </Box>

    <Card sx={{mb:3}}>
      <SectionHead title="Movement versus prior run" subtitle="Compare reproducible snapshots to isolate changes in the liquidity position." action={<FormControlLabel sx={{mr:0}} control={<Switch size="small" checked={compare} disabled={!comparisonCandidate} onChange={event=>setCompare(event.target.checked)}/>} label={<Typography variant="caption" fontWeight={700}>Compare prior run</Typography>}/>}/>
      {!comparisonCandidate?<Box px={2.7} pb={2.7}><Alert severity="info">A second completed run is needed before movement analysis can be shown.</Alert></Box>:!compare?<Box px={2.7} pb={2.7}><Typography variant="body2" color="text.secondary">Turn on comparison to analyse the selected run against {currentRunLabel(comparisonCandidate)}. Both calculations remain unchanged and independently traceable.</Typography></Box>:comparisonRun.isLoading?<Box p={3}><Typography variant="body2" color="text.secondary">Loading the prior saved snapshot…</Typography></Box>:comparisonRun.error?<Box px={2.7} pb={2.7}><ErrorMessage error={comparisonRun.error}/></Box>:!previousMetrics?<Box px={2.7} pb={2.7}><Alert severity="info">The prior run has no matching {currency} {activeBasis} ladder to compare.</Alert></Box>:<Box px={2.7} pb={2.7}><Stack direction={{xs:'column',md:'row'}} gap={1.35} mb={2.3}>{[
        ['Worst cumulative gap',metrics.worstPoint.cumulative-previousMetrics.worstPoint.cumulative,true],
        ['Position after capacity',metrics.worstAfterPoint.afterCapacity-previousMetrics.worstAfterPoint.afterCapacity,true],
        ['Available buffer',metrics.buffer-previousMetrics.buffer,true],
        ['30-day outflow pressure',metrics.shortTermOutflows-previousMetrics.shortTermOutflows,false],
      ].map(([label,value,invert])=><Box flex={1} key={String(label)}><Change label={String(label)} value={Number(value)} currency={currency} invert={Boolean(invert)}/></Box>)}</Stack><Typography variant="caption" color="text.secondary">Compared with {currentRunLabel(comparisonCandidate)} in original currency. A higher cumulative position (less negative), a higher reported buffer, or lower short-term outflow pressure is displayed as an improvement.</Typography></Box>}
    </Card>

    <Card sx={{p:2.3,bgcolor:'#F7F9FC',borderColor:'#E3EAF2'}}><Stack direction={{xs:'column',md:'row'}} gap={2} alignItems={{md:'center'}}><Box sx={{display:'flex',p:.85,borderRadius:1.8,bgcolor:'#E8EEF8',color:'#476487'}}><LayersRounded sx={{fontSize:18}}/></Box><Box flex={1}><Typography variant="subtitle2">Evidence remains one click away</Typography><Typography variant="body2" color="text.secondary" mt={.35}>This cockpit is a senior-management interpretation layer. Use the detailed maturity ladder, contract schedules and reconciliation controls to validate every number before action.</Typography></Box><Button variant="outlined" endIcon={<ArrowForwardRounded/>} href={`/results/${run.data.id}`}>Open detailed ladder</Button></Stack></Card>
  </>;
}
