import {describe,expect,it} from "vitest";
import {chromeWebStoreUrlFromId} from "./chromeStoreLink";

describe("verified official store link",()=>{
  it("constructs only the approved Chrome Web Store origin",()=>{
    const id="abcdefghijklmnopabcdefghijklmnop";
    expect(chromeWebStoreUrlFromId(id)).toBe(
      "https://chromewebstore.google.com/detail/"+id
    );
  });
  it("rejects malformed, hostile, absent and redirected IDs",()=>{
    for(const candidate of [undefined,null,"",123,"a".repeat(31),"z".repeat(32),
      "A".repeat(32),"a".repeat(32)+"/other","a".repeat(32)+"?token=private",
      "https://chromewebstore.google.com/detail/"+"a".repeat(32),
      "javascript:alert(1)"]){
      expect(chromeWebStoreUrlFromId(candidate)).toBeNull();
    }
  });
});
