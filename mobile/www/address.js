// Turns what the user types into their college's KalviOne address (D33).
// Shared by the picker page and the Node tests, so it has no browser-only code.
(function (root) {
  const BASE_DOMAIN = "kalvione.in";
  const SLUG = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;

  // Returns "https://<code>.kalvione.in" or null when the input isn't a college address.
  function collegeUrl(input, baseDomain = BASE_DOMAIN) {
    let text = String(input || "").trim().toLowerCase();
    text = text.replace(/^https?:\/\//, "").replace(/\/.*$/, "").replace(/\.$/, "");
    if (!text) return null;
    let slug = text;
    const suffix = "." + baseDomain;
    if (text.endsWith(suffix)) slug = text.slice(0, -suffix.length);
    if (!SLUG.test(slug)) return null;
    return "https://" + slug + suffix;
  }

  const api = { BASE_DOMAIN, collegeUrl };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.KalviAddress = api;
})(this);
