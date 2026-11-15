import test from "node:test";
import assert from "node:assert/strict";
import {createHash, webcrypto} from "node:crypto";
import {attachReviewedPdf} from "../page-attachment.mjs";

const listing = "https://jobs.lever.co/synthetic/12345678-aaaa-bbbb-cccc-123456789abc";
const application = listing + "/apply";
const pdf = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n");
const digest = createHash("sha256").update(pdf).digest("hex");
const globalNames = ["document","location","window","crypto","atob","File",
  "DataTransfer","Event","CSS","getComputedStyle"];

async function withEmployerUpload({kind="cv", mutate=()=>{}, foreignOwner=false,
  wrongApplicationForm=false}={}) {
  const saved = new Map(globalNames.map(key =>
    [key,Object.getOwnPropertyDescriptor(globalThis,key)]));
  const state = {hidden:false,disabled:false, events:[],form:{},controls:[]};
  const label = kind === "cv" ? "CV" : "Cover letter";
  const input = {
    tagName:"INPUT",type:"file",id:kind+"_file",name:kind+"_file",
    accept:"application/pdf",readOnly:false,multiple:false,isConnected:true,
    labels:[{innerText:label}],files:[],
    getAttribute:()=>"",
    getClientRects:()=>state.hidden ? [] : [{}],
    matches:(selector)=>selector === ":disabled" && state.disabled,
    closest:(selector)=>selector === "form" ? state.form :
      selector === "[hidden],[aria-hidden='true'],[inert]" && state.hidden ? {} : null,
    dispatchEvent:(event)=>{state.events.push(event.type);return true;},
  };
  state.controls=[input];
  input.form=foreignOwner ? {} : state.form;
  state.submitForm=wrongApplicationForm ? {} : state.form;
  const submitButton={
    innerText:"Submit application",disabled:false,
    getAttribute:()=>"",
    getClientRects:()=>[{}],
    get form(){return state.submitForm;},
    closest:(selector)=>selector === "form" ? state.submitForm : null,
  };
  const frame={};
  frame.top=frame; frame.self=frame;
  const stubs = {
    location:{href:application},
    window:frame,
    document:{
      querySelectorAll:(selector)=>selector === 'button,input[type="submit"]' ?
        [submitButton] : state.controls,
      querySelector:()=>null,
    },
    crypto:{subtle:{
      digest:async (...args)=>{
        mutate(input,state);
        return webcrypto.subtle.digest(...args);
      },
    }},
    atob:(encoded)=>Buffer.from(encoded,"base64").toString("binary"),
    File:class {
      constructor(parts,name,options){
        this.name=name;
        this.type=options.type;
        this.size=parts.reduce((total,p)=>total+p.byteLength,0);
      }
    },
    DataTransfer:class {
      constructor(){
        this.files=[];
        this.items={add:(file)=>this.files.push(file)};
      }
    },
    Event:class {
      constructor(type){this.type=type;}
    },
    CSS:{escape:(value)=>value},
    getComputedStyle:()=>({display:state.hidden?"none":"block",
      visibility:"visible"}),
  };
  for(const [key,value] of Object.entries(stubs)){
    Object.defineProperty(globalThis,key,{configurable:true,writable:true,value});
  }
  const payload={
    kind,index:0,application_url:listing,inspected_url:application,
    expected_id:input.id,expected_name:input.name,
    expected_label:label,expected_accept:input.accept,
    file_name:kind === "cv" ? "SmartPloy-CV.pdf" : "SmartPloy-Cover-Letter.pdf",
    base64:pdf.toString("base64"),sha256:digest,size:pdf.length,
  };
  try {
    const result=await attachReviewedPdf(payload);
    return {result,files:input.files,events:[...state.events]};
  } finally {
    for(const [key,desc] of saved){
      if(desc)Object.defineProperty(globalThis,key,desc);
      else delete globalThis[key];
    }
  }
}

test("unchanged reviewed CV and cover-letter fields attach locally without submit",async()=>{
  for(const kind of ["cv","letter"]){
    const r=await withEmployerUpload({kind});
    assert.equal(r.result.status,"attached_locally",kind);
    assert.equal(r.files.length,1,kind);
    assert.deepEqual(r.events,["input","change"],kind);
  }
});

test("a talent-pool form cannot receive either reviewed PDF",async()=>{
  for(const kind of ["cv","letter"]){
    const prior=await withEmployerUpload({kind,wrongApplicationForm:true});
    assert.equal(prior.result.status,"blocked",kind);
    assert.equal(prior.files.length,0,kind);
    const moved=await withEmployerUpload({kind,mutate:(_input,state)=>{
      state.submitForm={};
    }});
    assert.equal(moved.result.status,"blocked",kind);
    assert.equal(moved.files.length,0,kind);
    assert.deepEqual(moved.events,[],kind);
  }
});

test("an already foreign-owned PDF field refuses any transfer",async()=>{
  for(const kind of ["cv","letter"]){
    const r=await withEmployerUpload({kind,foreignOwner:true});
    assert.equal(r.result.status,"blocked",kind);
    assert.equal(r.files.length,0,kind);
    assert.deepEqual(r.events,[],kind);
  }
});

test("reactive upload-field repurposing during SHA-256 blocks before FileList transfer",async()=>{
  const mutations=[
    ["label",(input)=>{input.labels[0].innerText="Passport photo";}],
    ["id",(input)=>{input.id="id_document";}],
    ["name",(input)=>{input.name="identity_photo";}],
    ["accept",(input)=>{input.accept="image/jpeg";}],
    ["visibility",(_input,state)=>{state.hidden=true;}],
    ["form",(_input,state)=>{state.form={};}],
    ["form owner",(input)=>{input.form={};}],
    ["type",(input)=>{input.type="text";}],
    ["disabled",(_input,state)=>{state.disabled=true;}],
    ["reordered",(_input,state)=>{state.controls.unshift({});}],
  ];
  for(const kind of ["cv","letter"]){
    for(const [name,mutate] of mutations){
      const r=await withEmployerUpload({kind,mutate});
      assert.equal(r.result.status,"blocked",kind+" "+name);
      assert.equal(r.result.reason,
        "The employer form changed during PDF validation.",kind+" "+name);
      assert.equal(r.files.length,0,kind+" "+name);
      assert.deepEqual(r.events,[],kind+" "+name);
    }
  }
});
