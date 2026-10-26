/** SP44: real Vite production build serves the same static extension ZIP
 * and its SHA-256 sidecar, never an HTML SPA fallback. No employer traffic. */
import {createHash} from "node:crypto";
import {expect,test} from "@playwright/test";

test("SmartPloy first-party extension URL downloads a real reviewed ZIP",async ({request})=>{
  const binary=await request.get("/smartploy-apply-companion.zip");
  expect(binary.status()).toBe(200);
  const bytes=await binary.body();
  expect(bytes.length).toBeGreaterThan(50_000);
  expect(bytes.subarray(0,4)).toEqual(Buffer.from([0x50,0x4b,0x03,0x04]));
  expect(binary.headers()["content-type"]).not.toContain("text/html");
  const sha=createHash("sha256").update(bytes).digest("hex");
  const checksum=await request.get("/smartploy-apply-companion.zip.sha256");
  expect(checksum.status()).toBe(200);
  expect((await checksum.text()).trim()).toBe(
    sha+"  smartploy-apply-companion.zip"
  );
});

test("companion download is same-origin static; no external dependency or signin",async ({request})=>{
  const response=await request.get("/smartploy-apply-companion.zip",{
    headers:{Cookie:"",Authorization:""},
  });
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).not.toContain("text/html");
  expect(response.headers()["access-control-allow-origin"]).toBeUndefined();
});
