/** Real Chromium rendering of the production first-party Chrome popup.
 * Fixture is local source HTML/CSS with the extension controller excluded;
 * no employer, account or network permissions are fabricated.
 */
import {readFileSync} from "node:fs";
import {expect,test} from "@playwright/test";

const html=readFileSync(new URL("../../browser-companion/popup.html",import.meta.url),"utf8")
  .replace(/<link rel="stylesheet" href="popup.css"\s*\/>/,"")
  .replace(/<script src="popup.mjs" type="module"><\/script>/,"")
  .replace(/<img src="smartploy-mark-v2.svg"[^>]*\/>/,"");
const css=readFileSync(new URL("../../browser-companion/popup.css",import.meta.url),"utf8");

test("a previously claimed employer attempt cannot resemble an enabled final action",async({page})=>{
  await page.setContent(html);
  await page.addStyleTag({content:css});
  // Reproduce the REAL post-claim screen: the submission panel has already
  // been made visible by the original AutoApply inspect/submit workflow.
  await page.locator("#submission").evaluate((section)=>{section.hidden=false;});
  const button=page.locator("#finishOneJob");
  await button.evaluate((element)=>{
    element.setAttribute("disabled","");
    element.textContent="Attempt reserved — check confirmation";
  });
  await expect(button).toBeDisabled();
  await expect(button).toContainText("check confirmation");
  await page.mouse.move(70,100);
  const disabledBackground=await button.evaluate(element=>
    getComputedStyle(element).backgroundColor
  );
  const rect=await button.boundingBox();
  expect(rect).not.toBeNull();
  await page.mouse.move(rect!.x+rect!.width/2,rect!.y+rect!.height/2);
  const hoverBackground=await button.evaluate(element=>
    getComputedStyle(element).backgroundColor
  );
  expect(hoverBackground).toBe(disabledBackground);
  expect(hoverBackground).toBe("rgb(43, 55, 68)");
  await expect(page.locator("#finalClaimInfo")).toHaveAttribute("role","status");
  await expect(page.locator("#feedback")).toHaveAttribute("aria-live","polite");
  await expect(page.locator("#receipt")).toBeEnabled();
});

test("reduced-motion popup keeps genuine action labels and visible keyboard focus",async({page})=>{
  await page.emulateMedia({reducedMotion:"reduce"});
  await page.setContent(html);
  await page.addStyleTag({content:css});
  await page.locator("#verifyReview").focus();
  const button=page.locator("#verifyReview");
  await expect(button).toBeFocused();
  const outline=await button.evaluate(element=>getComputedStyle(element).outlineStyle);
  expect(outline).not.toBe("none");
  const transition=await page.locator("#startAutoApply").evaluate(element=>
    getComputedStyle(element).transitionDuration
  );
  expect(["0s","0s, 0s"]).toContain(transition);
  await expect(page.locator("#startAutoApply")).toContainText("Start AutoApply");
});
