import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {useNavigate} from 'react-router-dom';
import {Alert,Box,Button,Card,Chip,Divider,LinearProgress,MenuItem,Select,Stack,Table,TableBody,TableCell,TableContainer,TableHead,TableRow,Typography} from '@mui/material';
import {AccountBalanceWalletOutlined,ArrowForwardRounded,NorthEastRounded,QueryStatsRounded,SouthWestRounded,TrendingDownRounded,WarningAmberRounded} from '@mui/icons-material';
import {Area,AreaChart,Bar,BarChart,CartesianGrid,Cell,Legend,Pie,PieChart,ReferenceLine,ResponsiveContainer,Tooltip,XAxis,YAxis} from 'recharts';
import {useRuns,useWorkspace} from '../context';
import {api,compact,dateLabel,money} from '../api';
import type {BankLadder,Bucket} from '../types';
import {Empty,ErrorMessage,Loading,PageHeading,SectionHead} from '../components/Common';

const colours=['#217A70','#3869C9','#B88239','#8B5EAF','#3C8AA6','#C05C62'];
const n=(value:string|number|undefined)=>Number(value||0);
const ratio=(a:number,b:number)=>b?`${(100*a/b).toFixed(1)}%`:'—';
const status=(value:number,threshold:number)=>value>=threshold?{label:'Within appetite',color:'#168876',bg:'#E7F5EF'}:{label:'Attention required',color:'#BE555A',bg:'#FFF0F0'};

function Kpi({label,value,note,color,icon:Icon}:{label:string;value:string;note:string;color:string;icon:typeof AccountBalanceWalletOutlined}){
 return <Card sx={{p:2.3,minWidth:0,transition:'transform .18s ease, box-shadow .18s ease','&:hover':{transform:'translateY(-2px)',boxShadow:'0 12px 25px #17324B12'}}}><Stack direction="row" justifyContent="space-between" alignItems="flex-start"><Typography sx={{fontSize:11.5,fontWeight:650,color:'text.secondary'}}>{label}</Typography><Box sx={{p:.8,bgcolor:`${color}14`,color,borderRadius:1.6,display:'flex'}}><Icon sx={{fontSize:18}}/></Box></Stack><Typography sx={{fontSize:{xs:25,md:31},fontWeight:700,letterSpacing:-1.15,mt:1.4,color}}>{value}</Typography><Typography variant="caption" color="text.secondary" display="block" mt={.45}>{note}</Typography></Card>;
}

function ChartTooltip({active,payload,label,currency}:{active?:boolean;payload?:{name?:string;value?:number|string;color?:string}[];label?:string;currency:string}){
 if(!active||!payload?.length)return null;
 return <Box sx={{bgcolor:'background.paper',border:'1px solid #E0E8F0',boxShadow:'0 12px 28px #10243A1A',p:1.5,borderRadius:2,minWidth:180}}><Typography variant="subtitle2" mb={.75}>{label}</Typography>{payload.map(item=><Stack key={item.name} direction="row" justifyContent="space-between" gap={2}><Typography variant="caption" sx={{color:item.color}}>{item.name}</Typography><Typography variant="caption" fontWeight={700}>{money(n(item.value),currency)}</Typography></Stack>)}</Box>;
}

export default function LiquidityAnalytics(){
 const {entity}=useWorkspace(),runs=useRuns(),nav=useNavigate();
 const [chosenCurrency,setCurrency]=useState(''),[selectedBucket,setSelectedBucket]=useState<string>('');
 const latest=runs.data?.runs.find(run=>['completed','completed_with_exceptions'].includes(run.status));
 const detail=useQuery({queryKey:['analytics-run',latest?.id],queryFn:()=>api.run(latest!.id),enabled:!!latest});
 const lcr=useQuery({queryKey:['analytics-lcr',entity?.slug],queryFn:()=>api.lcrReport(entity!.slug),enabled:!!entity});
 const nsfr=useQuery({queryKey:['analytics-nsfr',entity?.slug],queryFn:()=>api.nsfrReport(entity!.slug),enabled:!!entity});
 if(runs.isLoading||detail.isLoading||lcr.isLoading||nsfr.isLoading)return <Loading/>;
 if(!latest)return <Empty title="No liquidity analytics yet" description="Run a calculation first. The analytics page then turns the saved cash-flow results into management-ready liquidity indicators." action={<Button variant="contained" onClick={()=>nav('/new')}>New calculation</Button>}/>;
 if(detail.error)return <ErrorMessage error={detail.error}/>;
 const result=detail.data?.result;
 if(!result)return <Empty title="Calculation still in progress" description="Analytics will appear as soon as the current calculation is complete." action={<Button variant="outlined" onClick={()=>nav('/runs')}>View run history</Button>}/>;
 const currency=result.currencies.includes(chosenCurrency)?chosenCurrency:result.currencies[0]||entity?.base_currency||'JOD';
 const rows=result.summary[currency]||[];
 const boundaries=result.bucket_days;
 const chartData=rows.map((row,index)=>({
  ...row,
  label:row.bucket|| (index<boundaries.length?`≤ ${boundaries[index]}d`:`> ${boundaries.at(-1)||0}d`),
  inflows:n(row.inflows),outflows:n(row.outflows),net:n(row.net_gap),cumulative:n(row.cumulative_gap),index,
 }));
 const ladder:BankLadder|undefined=result.bank_ladder?.[currency];
 const totals=(()=>{
  const inflow=chartData.reduce((sum,row)=>sum+row.inflows,0),outflow=chartData.reduce((sum,row)=>sum+row.outflows,0);
  const within30=chartData.filter((_,index)=>(boundaries[index]||Infinity)<=30);
  const inflow30=within30.reduce((sum,row)=>sum+row.inflows,0),outflow30=within30.reduce((sum,row)=>sum+row.outflows,0);
  const low=chartData.reduce((current,row)=>row.cumulative<current.cumulative?row:current,chartData[0]||{cumulative:0,label:'—'});
  const largestOutflow=chartData.reduce((current,row)=>row.outflows>current.outflows?row:current,chartData[0]||{outflows:0,label:'—'});
  return {inflow,outflow,inflow30,outflow30,low,largestOutflow};
 })();
 const productData=(()=>{
  const source=ladder?.rows.filter(row=>row.kind==='normal'&&(row.section==='inflows'||row.section==='outflows'))||[];
  const values=source.map(row=>({name:row.label.replace(/_/g,' '),value:Math.abs(n(row.balance)),direction:row.section==='inflows'?'Inflow':'Outflow'})).filter(row=>row.value>0).sort((a,b)=>b.value-a.value).slice(0,6);
  return values.length?values:[{name:'No grouped balance available',value:1,direction:'Inflow'}];
 })();
 const selected=chartData.find(row=>row.label===selectedBucket);
 const gapStatus=status(totals.low.cumulative,0),lcrValue=n(lcr.data?.lcr)*100,nsfrValue=n(nsfr.data?.nsfr)*100;
 const issues=[
  totals.low.cumulative<0?{title:'Cumulative gap turns negative',detail:`Lowest point: ${money(totals.low.cumulative,currency)} in ${totals.low.label}.`,severity:'error' as const}:{title:'No negative cumulative gap',detail:'The calculated contractual horizon remains positive.',severity:'success' as const},
  {title:'30-day cash-flow coverage',detail:`Inflows cover ${ratio(totals.inflow30,totals.outflow30)} of contractual outflows through 30 days.`,severity:totals.inflow30>=totals.outflow30?'success' as const:'warning' as const},
  {title:'Largest timing pressure',detail:`${totals.largestOutflow.label} carries ${money(totals.largestOutflow.outflows,currency)} of scheduled outflow.`,severity:'info' as const},
 ];
 return <><PageHeading title="Liquidity analytics" subtitle="Management-ready cash-flow intelligence from the selected calculation, with transparent contractual drivers." action={<Stack direction="row" gap={1}><Button variant="outlined" onClick={()=>nav(`/results/${latest.id}`)}>Open detailed ladder</Button><Button variant="contained" endIcon={<ArrowForwardRounded/>} onClick={()=>nav('/lcr')}>Open LCR</Button></Stack>}/>
 <ErrorMessage error={runs.error||lcr.error||nsfr.error}/>
 <Card sx={{p:{xs:2,md:2.5},mb:3,background:'linear-gradient(110deg,#11344A 0%,#1D5270 56%,#2A6B87 100%)',color:'white',border:'none',overflow:'hidden',position:'relative'}}><Box sx={{position:'absolute',right:-95,top:-145,width:320,height:320,borderRadius:'50%',border:'56px solid #7DD3C420'}}/><Stack direction={{xs:'column',md:'row'}} gap={2} justifyContent="space-between" alignItems={{md:'center'}} position="relative"><Box><Typography variant="overline" sx={{letterSpacing:1.5,color:'#A7D6D3'}}>LIQUIDITY INTELLIGENCE</Typography><Typography variant="h5" fontWeight={700}>What is driving the contractual position?</Typography><Typography variant="body2" sx={{color:'#D3E6EB',mt:.7}}>Click any maturity bucket to review its scheduled flows and cumulative position.</Typography></Box><Stack direction="row" gap={1.2} flexWrap="wrap"><Chip label={`${entity?.name||'Entity'} · ${dateLabel(result.as_of_date)}`} sx={{bgcolor:'#FFFFFF1A',color:'white',fontWeight:600}}/><Chip label={gapStatus.label} sx={{bgcolor:gapStatus.label==='Within appetite'?'#8FE1CF':'#FFD4D5',color:gapStatus.label==='Within appetite'?'#15594E':'#942B32',fontWeight:700}}/></Stack></Stack></Card>
 <Stack direction="row" alignItems="center" gap={1.25} mb={2.25} flexWrap="wrap"><Typography variant="body2" fontWeight={700}>Original currency</Typography><Select size="small" value={currency} onChange={event=>{setCurrency(event.target.value);setSelectedBucket('')}} sx={{minWidth:150}}>{result.currencies.map(item=><MenuItem key={item} value={item}>{item}</MenuItem>)}</Select><Typography variant="caption" color="text.secondary">Saved run · {dateLabel(result.as_of_date)} · contractual basis</Typography></Stack>
 <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr 1fr',xl:'repeat(4,1fr)'},gap:2,mb:3}}><Kpi label="30-day coverage" value={ratio(totals.inflow30,totals.outflow30)} note="Contractual inflows ÷ outflows" color={totals.inflow30>=totals.outflow30?'#168876':'#BE555A'} icon={AccountBalanceWalletOutlined}/><Kpi label="Lowest cumulative gap" value={compact(totals.low.cumulative)} note={`${totals.low.label} · ${currency}`} color={totals.low.cumulative>=0?'#168876':'#BE555A'} icon={TrendingDownRounded}/><Kpi label="LCR" value={lcr.data?`${lcrValue.toFixed(1)}%`:'—'} note="High-quality liquid assets / net outflows" color={lcrValue>=100?'#3869C9':'#BE555A'} icon={QueryStatsRounded}/><Kpi label="NSFR" value={nsfr.data?`${nsfrValue.toFixed(1)}%`:'—'} note="Available stable funding / required funding" color={nsfrValue>=100?'#3869C9':'#BE555A'} icon={AccountBalanceWalletOutlined}/></Box>
 <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',xl:'minmax(0,2.1fr) minmax(300px,.9fr)'},gap:3,mb:3}}><Card><SectionHead title="Cumulative liquidity position" subtitle="Click a point to select a maturity bucket."/><Box sx={{height:305,px:1.5,pb:1.5}}><ResponsiveContainer width="100%" height="100%"><AreaChart data={chartData} margin={{top:14,right:18,left:0,bottom:8}} onClick={state=>{const item=(state as unknown as {activePayload?:{payload?:typeof chartData[number]}[]})?.activePayload?.[0]?.payload;if(item)setSelectedBucket(item.label);}}><defs><linearGradient id="cumulativeGap" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#2C81B1" stopOpacity={.34}/><stop offset="100%" stopColor="#2C81B1" stopOpacity={.02}/></linearGradient></defs><CartesianGrid stroke="#E8EEF3" strokeDasharray="3 4" vertical={false}/><XAxis dataKey="label" tick={{fontSize:10,fill:'#7B8998'}} axisLine={false} tickLine={false} interval="preserveStartEnd"/><YAxis tickFormatter={value=>compact(value)} tick={{fontSize:10,fill:'#7B8998'}} axisLine={false} tickLine={false} width={68}/><ReferenceLine y={0} stroke="#B85A61" strokeDasharray="4 4"/><Tooltip content={<ChartTooltip currency={currency}/>}/><Area type="monotone" dataKey="cumulative" name="Cumulative gap" stroke="#286CCF" strokeWidth={3} fill="url(#cumulativeGap)" activeDot={{r:6,strokeWidth:2}}/></AreaChart></ResponsiveContainer></Box><Divider/><Box px={2.5} py={1.6}><Typography variant="caption" color="text.secondary">A negative area means contractual outflows exceed accumulated inflows. Opening cash, undated balances and management actions are excluded.</Typography></Box></Card>
 <Card sx={{display:'flex',flexDirection:'column'}}>
  <SectionHead title="Selected bucket" subtitle={selected?selected.label:'Select a point in the chart'}/>
  <Box sx={{p:2.5,pt:0,flex:1}}>
   {selected ? <>
    <Stack direction="row" justifyContent="space-between" alignItems="baseline"><Typography variant="h4" sx={{color:selected.cumulative<0?'error.main':'success.main'}}>{money(selected.cumulative,currency)}</Typography><Chip size="small" label={selected.cumulative<0?'Deficit':'Surplus'} color={selected.cumulative<0?'error':'success'} variant="outlined"/></Stack>
    <Typography variant="caption" color="text.secondary">Cumulative contractual gap</Typography>
    <Divider sx={{my:2}}/>
    {[['Inflows',selected.inflows,'#168876'],['Outflows',selected.outflows,'#5C78BD'],['Net cash flow',selected.net,selected.net<0?'#BE555A':'#168876']].map(([label,value,color])=><Stack key={String(label)} direction="row" justifyContent="space-between" mb={1.2}><Typography variant="body2" color="text.secondary">{label}</Typography><Typography variant="body2" fontWeight={700} sx={{color:String(color)}}>{money(Number(value),currency)}</Typography></Stack>)}
   </> : <Typography variant="body2" color="text.secondary">Choose any point in the cumulative chart to see its inflows, outflows and net timing pressure.</Typography>}
  </Box>
  {selected&&<Button onClick={()=>nav(`/results/${latest.id}`)} endIcon={<ArrowForwardRounded/>} sx={{m:1}}>Inspect in ladder</Button>}
 </Card></Box>
 <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',xl:'minmax(0,1.3fr) minmax(0,1.1fr) minmax(260px,.8fr)'},gap:3,mb:3}}><Card><SectionHead title="Inflows versus outflows" subtitle="Cash-flow timing by maturity bucket"/><Box sx={{height:270,px:1.5,pb:1.5}}><ResponsiveContainer width="100%" height="100%"><BarChart data={chartData} margin={{top:12,right:8,left:0,bottom:8}}><CartesianGrid stroke="#E8EEF3" strokeDasharray="3 4" vertical={false}/><XAxis dataKey="label" tick={{fontSize:9,fill:'#7B8998'}} axisLine={false} tickLine={false} interval="preserveStartEnd"/><YAxis tickFormatter={value=>compact(value)} tick={{fontSize:10,fill:'#7B8998'}} axisLine={false} tickLine={false} width={62}/><Tooltip content={<ChartTooltip currency={currency}/>}/><Legend wrapperStyle={{fontSize:11}}/><Bar dataKey="inflows" name="Inflows" fill="#188A79" radius={[4,4,0,0]} maxBarSize={21}/><Bar dataKey="outflows" name="Outflows" fill="#87A0D9" radius={[4,4,0,0]} maxBarSize={21}/></BarChart></ResponsiveContainer></Box></Card>
 <Card><SectionHead title="Balance-sheet mix" subtitle="Largest current principal balances by liquidity line"/><Box sx={{height:270,px:1.5,pb:1.5}}><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={productData} dataKey="value" nameKey="name" innerRadius={58} outerRadius={88} paddingAngle={2}>{productData.map((_,index)=><Cell key={index} fill={colours[index%colours.length]}/>)}</Pie><Tooltip formatter={(value)=>money(Number(value),currency)}/><Legend layout="vertical" verticalAlign="middle" align="right" wrapperStyle={{fontSize:10,maxWidth:145}}/></PieChart></ResponsiveContainer></Box></Card>
 <Card sx={{p:2.5}}><Stack direction="row" gap={1} alignItems="center"><WarningAmberRounded color="warning"/><Typography variant="subtitle1" fontWeight={700}>Decision cues</Typography></Stack><Stack gap={1.35} mt={2}>{issues.map(issue=><Alert key={issue.title} severity={issue.severity} variant="outlined" icon={false} sx={{py:.7}}><Typography variant="caption" fontWeight={750} display="block">{issue.title}</Typography><Typography variant="caption">{issue.detail}</Typography></Alert>)}</Stack></Card></Box>
 <Card><SectionHead title="Maturity pressure monitor" subtitle="The buckets that matter most for the next management conversation." action={<Button size="small" onClick={()=>nav(`/results/${latest.id}`)}>Full ladder <ArrowForwardRounded sx={{fontSize:15,ml:.4}}/></Button>}/><TableContainer><Table size="small"><TableHead><TableRow><TableCell>Bucket</TableCell><TableCell align="right">Contractual inflows</TableCell><TableCell align="right">Contractual outflows</TableCell><TableCell align="right">Net flow</TableCell><TableCell align="right">Cumulative gap</TableCell><TableCell>Signal</TableCell></TableRow></TableHead><TableBody>{[...chartData].sort((a,b)=>a.cumulative-b.cumulative).slice(0,5).map(row=><TableRow key={row.label} hover onClick={()=>setSelectedBucket(row.label)} sx={{cursor:'pointer'}}><TableCell sx={{fontWeight:650}}>{row.label}</TableCell><TableCell align="right">{money(row.inflows,currency)}</TableCell><TableCell align="right">{money(row.outflows,currency)}</TableCell><TableCell align="right" sx={{color:row.net<0?'error.main':'success.main',fontWeight:650}}>{money(row.net,currency)}</TableCell><TableCell align="right" sx={{color:row.cumulative<0?'error.main':'success.main',fontWeight:700}}>{money(row.cumulative,currency)}</TableCell><TableCell><Chip size="small" label={row.cumulative<0?'Liquidity deficit':'Positive position'} color={row.cumulative<0?'error':'success'} variant="outlined"/></TableCell></TableRow>)}</TableBody></Table></TableContainer></Card>
 </>;
}
