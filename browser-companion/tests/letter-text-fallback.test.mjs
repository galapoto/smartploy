import test from "node:test";
import assert from "node:assert/strict";
import {verifyReviewedCoverLetterText} from "../page-attachment.mjs";

const JOB="https://jobs.lever.co/synthetic/job123/apply";
const TEXT="I reviewed the complete content of this truthful application letter before permitting the employer form to receive it.";
const globals=["window","location","document","getComputedStyle","CSS"];

function withEmployer(options={}) {
  const old=new Map(globals.map(name=>
    [name,Object.getOwnPropertyDescriptor(globalThis,name)]));
  const state={};
  const form={
    closest:()=>null,
    getClientRects:()=>[{}]
  };
  const labelNode={innerText:options.label || "Cover letter"};
  const text={
    tagName:"TEXTAREA",type:"textarea",
    name:options.nameless ? "" : "coverLetterText",
    id:"cover_letter",labels:[labelNode],
    value:options.value ?? TEXT,
    disabled:!!options.disabled,readOnly:!!options.readonly,
    isConnected:!options.disconnected,
    form:options.foreignForm ? {} : form,
    matches:(selector)=>selector===":disabled" && !!options.ancestorDisabled,
    closest:(selector)=>selector==="form" ? form :
      selector==="[hidden],[aria-hidden='true'],[inert]" && options.hidden ? {} : null,
    getAttribute:()=>null,
    getClientRects:()=>options.hidden ? [] : [{}],
  };
  const inputs=[text];
  if(options.duplicate) inputs.push({...text,id:"other",name:"otherLetter"});
  if(options.file)inputs.push({
    tagName:"INPUT",type:"file",name:"letter",id:"letter",
    labels:[{innerText:"Cover letter"}],getAttribute:()=>null
  });
  const button={
    innerText:"Submit application",disabled:false,
    getAttribute:()=>null,getClientRects:()=>[{}],
    closest:(selector)=>selector==="form" ? form : null
  };
  const frame={};frame.top=frame;frame.self=frame;
  const values={
    location:{href:options.url ?? JOB},
    window:options.iframe ? {top:{},self:{}} : frame,
    CSS:{escape:x=>x},
    document:{
      querySelectorAll:(selector)=>selector==='button,input[type="submit"]' ?
        [button] : inputs,
      querySelector:()=>null,
    },
    getComputedStyle:(el)=>({
      display:options.hidden && el===text ? "none" : "block",
      visibility:"visible"
    })
  };
  for(const [key,value] of Object.entries(values))
    Object.defineProperty(globalThis,key,{configurable:true,value,writable:true});
  try {
    return verifyReviewedCoverLetterText(
      options.packetUrl ?? JOB,options.inspectedUrl ?? (options.url ?? JOB),
      options.expected ?? TEXT
    );
  } finally {
    for(const [key,desc] of old){
      if(desc)Object.defineProperty(globalThis,key,desc);
      else delete globalThis[key];
    }
  }
}

test("only exact reviewed letter text on the unique submitted Lever form qualifies",()=>{
  const result=withEmployer();
  assert.deepEqual(result,{ready:true,mode:"reviewed_cover_letter_text"});
  assert.equal("value" in result,false);
});

test("missing, changed, hidden, duplicate, readonly, and non-submitted letter text fail closed",()=>{
  for(const opts of [
    {value:""},{value:"Employer wrote a different letter"},
    {duplicate:true},{hidden:true},{disabled:true},{readonly:true},
    {ancestorDisabled:true},{disconnected:true},{nameless:true},
    {foreignForm:true},{label:"Visa and cover letter"},
    {label:"Salary and cover letter"},
    {file:true},
  ]) {
    const result=withEmployer(opts);
    assert.equal(result.ready,false,JSON.stringify(opts));
  }
});

test("wrong origin, sibling job, HTTPS downgrade, altered URL and iframe block text mode",()=>{
  for(const opts of [
    {url:"https://jobs.lever.co/synthetic/another/apply"},
    {url:"https://jobs.lever.co/synthetic/job123/apply?changed=yes"},
    {url:"http://jobs.lever.co/synthetic/job123/apply"},
    {url:"https://jobs.lever.co.evil.invalid/synthetic/job123/apply"},
    {packetUrl:"https://jobs.lever.co/synthetic/other"},
    {iframe:true},
  ]) assert.equal(withEmployer(opts).ready,false,JSON.stringify(opts));
});

test("short/unreviewed text is never promoted to approved letter",()=>{
  assert.equal(withEmployer({expected:"short"}).ready,false);
  assert.equal(withEmployer({expected:TEXT+" changed"}).ready,false);
});
