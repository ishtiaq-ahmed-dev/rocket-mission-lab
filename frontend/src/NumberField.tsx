import {useEffect,useState} from 'react';

/**
 * A controlled number input that keeps in-progress text (for example "-" or a
 * partially typed value) out of application state. Only complete, in-range
 * numbers are committed; blur restores the last committed value.
 */
export default function NumberField({value,onCommit,label,min,max,step}:{
  value:number;onCommit:(value:number)=>void;label:string;min:number;max:number;step:number;
}){
  const [draft,setDraft]=useState(()=>String(value));
  useEffect(()=>{setDraft(String(value));},[value]);
  const change=(text:string)=>{
    setDraft(text);
    const parsed=Number(text);
    if(text.trim()!==''&&Number.isFinite(parsed)&&parsed>=min&&parsed<=max)onCommit(parsed);
  };
  return <input aria-label={label} type="number" min={min} max={max} step={step} value={draft} onChange={event=>change(event.target.value)} onBlur={()=>setDraft(String(value))}/>;
}
