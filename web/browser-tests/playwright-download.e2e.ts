/** SP110: served Playwright runner ZIP must be real static content, not SPA. */
import {createHash} from "node:crypto";
import {expect,test} from "@playwright/test";

test("SmartPloy offers the exact reviewed local Playwright assistant",async ({request})=>{
  const response=await request.get("/smartploy-playwright-assistant.zip");
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).not.toContain("text/html");
  const bytes=await response.body();
  expect(bytes.length).toBeGreaterThan(6_000);
  expect(bytes.subarray(0,4)).toEqual(Buffer.from([0x50,0x4b,0x03,0x04]));
  const expected=createHash("sha256").update(bytes).digest("hex");
  const checksum=await request.get("/smartploy-playwright-assistant.zip.sha256");
  expect(checksum.status()).toBe(200);
  expect((await checksum.text()).trim()).toBe(
    expected+"  smartploy-playwright-assistant.zip"
  );
});

test("Playwright download is static without applicant cookies",async ({request})=>{
  const result=await request.get("/smartploy-playwright-assistant.zip",{
    headers:{Cookie:"",Authorization:""},
  });
  expect(result.status()).toBe(200);
  expect(result.headers()["content-type"]).not.toContain("text/html");
  expect(result.headers()["access-control-allow-origin"]).toBeUndefined();
});
