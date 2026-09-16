import {createTheme} from '@mui/material/styles';
export const theme=createTheme({
 palette:{primary:{main:'#2D5BDE',dark:'#1E43AE',light:'#EAF0FF'},secondary:{main:'#168E81'},background:{default:'#F5F7FA',paper:'#FFFFFF'},text:{primary:'#192D40',secondary:'#718095'},divider:'#E6EBF1',success:{main:'#168B6C'},warning:{main:'#B77728'},error:{main:'#C84F54'}},
 typography:{fontFamily:'Inter, sans-serif',fontSize:13,h4:{fontSize:'1.9rem',fontWeight:650,letterSpacing:'-.9px'},h5:{fontSize:'1.4rem',fontWeight:650,letterSpacing:'-.5px'},h6:{fontSize:'1rem',fontWeight:650},subtitle2:{fontWeight:600},button:{textTransform:'none',fontWeight:600},body2:{fontSize:'.8rem',lineHeight:1.65},caption:{fontSize:'.7rem'}},
 shape:{borderRadius:12},
 components:{MuiCssBaseline:{styleOverrides:{body:{fontFeatureSettings:'"cv11", "ss01"'},a:{color:'inherit'},'*':{boxSizing:'border-box'},'::selection':{background:'#DDE8FF'}}},
 MuiButton:{defaultProps:{disableElevation:true},styleOverrides:{root:{borderRadius:8,padding:'9px 16px',whiteSpace:'nowrap'},outlined:{borderColor:'#DCE3ED'}}},
 MuiPaper:{defaultProps:{elevation:0},styleOverrides:{root:{backgroundImage:'none'}}},
 MuiCard:{styleOverrides:{root:{border:'1px solid #E6EBF1',boxShadow:'0 3px 10px #162C4603'}}},
 MuiOutlinedInput:{styleOverrides:{root:{fontSize:13,borderRadius:8,backgroundColor:'#fff'},notchedOutline:{borderColor:'#DCE3ED'}}},
 MuiTableCell:{styleOverrides:{head:{fontSize:10.5,fontWeight:650,textTransform:'uppercase',letterSpacing:'.55px',color:'#788799',background:'#FAFBFD',borderBottom:'1px solid #E6EBF1'},root:{padding:'14px 18px',borderBottom:'1px solid #EEF1F5'},body:{fontSize:12}}},
 MuiChip:{styleOverrides:{root:{fontSize:10.5,fontWeight:600,borderRadius:6},sizeSmall:{height:24}}},
 MuiTabs:{styleOverrides:{root:{minHeight:44},indicator:{height:3,borderRadius:4}}},MuiTab:{styleOverrides:{root:{fontSize:12,textTransform:'none',minHeight:44,fontWeight:600}}},
 MuiTooltip:{defaultProps:{arrow:true}},MuiDialog:{styleOverrides:{paper:{borderRadius:16}}}
 }});
