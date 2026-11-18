import test from "node:test";
import assert from "node:assert/strict";
import { uniqueApprovedOption } from "../adapters/approved-option.mjs";

test("V4 exact matching never guesses a yes/no option", () => {
  const options = [{ value:"yes", label:"Yes" }, { value:"no", label:"No" }];
  assert.deepEqual(uniqueApprovedOption("yes", options), { index:0, value:"yes", label:"Yes" });
  for (const value of ["y", "yes ", "YES", "", null, "yes and no"]) {
    assert.equal(uniqueApprovedOption(value, options), null);
  }
});
test("V4 rejects duplicate option identities and disabled choices", () => {
  assert.equal(uniqueApprovedOption("a", [{ value:"a", label:"One" }, { value:"a", label:"Two" }]), null);
  assert.equal(uniqueApprovedOption("a", [{ value:"a", label:"One", disabled:true }]), null);
  assert.equal(uniqueApprovedOption("a", [{ value:"a", label:"One" }, { value:"b", label:"Two", disabled:true }]).value, "a");
});
