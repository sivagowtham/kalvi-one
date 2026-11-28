const test = require("node:test");
const assert = require("node:assert");
const { collegeUrl } = require("../www/address.js");

test("a college code becomes its address", () => {
  assert.strictEqual(collegeUrl("demo"), "https://demo.kalvione.in");
  assert.strictEqual(collegeUrl("  PieTech "), "https://pietech.kalvione.in");
  assert.strictEqual(collegeUrl("pcas-1"), "https://pcas-1.kalvione.in");
});

test("a full address is accepted", () => {
  assert.strictEqual(collegeUrl("demo.kalvione.in"), "https://demo.kalvione.in");
  assert.strictEqual(collegeUrl("https://demo.kalvione.in/login/"), "https://demo.kalvione.in");
});

test("anything that is not one college on KalviOne is refused", () => {
  for (const bad of ["", "   ", "a.b", "evil.com", "demo.kalvione.in.evil.com", "-demo", "demo-",
                     "de mo", "x".repeat(64), "kalvione.in", "a.demo.kalvione.in"]) {
    assert.strictEqual(collegeUrl(bad), null, bad);
  }
});
