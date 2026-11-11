/** Run the actual serialized popup function against reactive employer form fixtures.
 * No employer network, account or real CV is touched; no final submit exists.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {runInNewContext} from "node:vm";

const source=readFileSync(new URL("../popup.mjs",import.meta.url),"utf8");
const begin=source.indexOf("async function fillPlanned(actions, exactUrl) {");
const end=source.indexOf("\nfunction inspectFinalSubmit(",begin);
assert.ok(begin>0&&end>begin,"the production extension fill function must exist");
const snippet=source.slice(begin,end);
const job="https://jobs.lever.co/example/job/apply";

function field(id,label,type="text") {
  return {id,name:id,label,type,value:""};
}
function simulate({rows=[field("name","Full name"),field("email","Email","email")],
  onInput=()=>{},onSettle=()=>{}}={}) {
  class FakeInput {
    constructor(model) {
      this.model=model;
      this.id=model.id;
      this.name=model.name;
      this.type=model.type;
      this.tagName="INPUT";
      this.labels=[{innerText:model.label}];
      this.disabled=false;
      this.readOnly=false;
      this.isConnected=true;
      this.maxLength=-1;
      this.events=[];
    }
    get value(){return this.model.value}
    set value(next){this.model.value=next}
    getAttribute(name){return name==="placeholder"?"":name==="autocomplete"?"":null}
    closest(){return null}
    getClientRects(){return [{}]}
    dispatchEvent(event){this.events.push(event.type);if(event.type==="input")onInput(this)}
  }
  const inputs=rows.map(x=>new FakeInput(x));
  const current=inputs.slice();
  let settleCount=0;
  const location={href:job};
  const context={
    location,URL,HTMLInputElement:FakeInput,HTMLTextAreaElement:FakeInput,
    Event:class {constructor(type){this.type=type}},
    CSS:{escape:x=>x},
    getComputedStyle:()=>({display:"block",visibility:"visible"}),
    document:{querySelectorAll:()=>current.slice()},
    setTimeout(fn,ms){assert.equal(ms,150);settleCount++;onSettle({inputs,current,location});fn()}
  };
  runInNewContext(snippet+"\nthis.actualFill=fillPlanned;",context);
  const actions=inputs.map((el,index)=>({
    index,expected_id:el.id,expected_name:el.name,expected_type:el.type,
    label:el.model.label,value:index===0?"Test Candidate":"person@example.org"
  }));
  return {fill:()=>context.actualFill(actions,job),inputs,location,current,rows,settles:()=>settleCount};
}

test("persisted contact values count only after two settled checks",async()=>{
  const f=simulate();
  const result=await f.fill();
  assert.equal(result.blocker,"");
  assert.equal(result.filled,2);
  assert.equal(f.settles(),2);
  assert.equal(f.inputs[0].value,"Test Candidate");
  assert.equal(f.inputs[1].value,"person@example.org");
  assert.deepEqual(f.inputs[0].events,["input","change"]);
  assert.deepEqual(f.inputs[1].events,["input","change"]);
});

test("employer React handler clearing an input after dispatch stops with zero verified writes",async()=>{
  let delayed=false;
  const f=simulate({
    onInput:el=>{if(el.id==="name") delayed=true},
    onSettle:({inputs})=>{if(delayed)inputs[0].value="";delayed=false}
  });
  const result=await f.fill();
  assert.equal(result.filled,0);
  assert.match(result.blocker,/cleared a reviewed value/);
  assert.equal(f.settles(),1);
  assert.equal(f.inputs[1].value,"");
  assert.equal(f.inputs[0].events.filter(x=>x==="input").length,1);
});

test("navigation after a single input invalidates the attempt without retry or next field",async()=>{
  const f=simulate({onSettle:({location})=>{location.href="https://evil.invalid/other"}});
  const result=await f.fill();
  assert.equal(result.filled,0);
  assert.ok(result.blocker);
  assert.equal(f.inputs[1].events.length,0);
});

test("reactive replacement of an inspected field cannot become a success",async()=>{
  const f=simulate({onSettle:({current})=>{current[0]={...current[0]}}});
  const result=await f.fill();
  assert.equal(result.filled,0);
  assert.ok(result.blocker);
  assert.equal(f.inputs[1].value,"");
});

test("changed contact field to a sensitive employer question cannot become success",async()=>{
  const f=simulate({onSettle:({inputs})=>{inputs[0].name="visaStatus"}});
  const result=await f.fill();
  assert.equal(result.filled,0);
  assert.ok(result.blocker);
  assert.equal(f.inputs[1].value,"");
});

test("no approved contact actions writes nothing and does not wait",async()=>{
  const f=simulate();
  const g=f.fill;
  const empty=await (()=>{
    const a=snippet+"\nthis.noContact=fillPlanned;";
    const cx={URL,location:{href:job},document:{querySelectorAll:()=>[]}};
    runInNewContext(a,cx);
    return cx.noContact([],job);
  })();
  assert.equal(empty.filled,0);
  assert.equal(empty.blocker,"");
  assert.equal(f.settles(),0);
  assert.equal(typeof g,"function");
});
