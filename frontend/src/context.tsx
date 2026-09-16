import {createContext,useContext,useState,useEffect,type ReactNode} from 'react';
import {useQuery} from '@tanstack/react-query';
import {api} from './api';
import type {Entity,Session} from './types';
interface Context {entities:Entity[];entity:Entity|undefined;selectEntity:(s:string)=>void;session:Session|undefined;loading:boolean;error:string;}
const Workspace=createContext<Context>({entities:[],entity:undefined,selectEntity:()=>{},session:undefined,loading:true,error:''});
export const useWorkspace=()=>useContext(Workspace);
export function WorkspaceProvider({children}:{children:ReactNode}){
 const entities=useQuery({queryKey:['entities'],queryFn:api.entities});
 const session=useQuery({queryKey:['session'],queryFn:api.session});
 const [slug,setSlug]=useState(localStorage.getItem('alm-entity')||'jordan-mock');
 const list=entities.data||[];const entity=list.find(e=>e.slug===slug)||list[0];
 useEffect(()=>{if(entity)localStorage.setItem('alm-entity',entity.slug);},[entity]);
 return <Workspace.Provider value={{entities:list,entity,selectEntity:setSlug,session:session.data,loading:entities.isLoading||session.isLoading,error:entities.error?.message||session.error?.message||''}}>{children}</Workspace.Provider>;
}
export function usePortfolio(){const {entity}=useWorkspace();return useQuery({queryKey:['portfolio',entity?.slug],queryFn:()=>api.portfolio(entity!.slug),enabled:!!entity});}
export function useRuns(){const {entity}=useWorkspace();return useQuery({queryKey:['runs',entity?.slug],queryFn:()=>api.runs(entity!.slug),enabled:!!entity,refetchInterval:q=>q.state.data?.runs.some(r=>['queued','running'].includes(r.status))?1500:false});}
