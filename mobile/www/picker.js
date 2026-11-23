// College picker for the KalviOne app (D33).
// First launch: ask for the college code, check it exists, remember it, open it.
// Later launches: open the remembered college straight away. "?change=1" (the
// "Switch college" link on every KalviOne page inside the app) shows the picker again.
(function () {
  const KEY = "kalvione.college";
  const $ = (id) => document.getElementById(id);
  const params = new URLSearchParams(location.search);

  function saved() {
    try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { return null; }
  }
  function remember(college) {
    try { localStorage.setItem(KEY, JSON.stringify(college)); } catch (e) { /* still opens */ }
  }
  function open(url) { location.replace(url + "/?source=app"); }

  function showPicker(message) {
    $("confirm").hidden = true;
    $("pick").hidden = false;
    $("error").hidden = !message;
    $("error").textContent = message || "";
    $("find").disabled = false;
    $("code").focus();
  }

  function showConfirm(college) {
    $("pick").hidden = true;
    $("confirm").hidden = false;
    $("college-name").textContent = college.name;
    $("college-url").textContent = college.url.replace("https://", "");
  }

  async function lookUp(url) {
    // Each college serves its manifest publicly; its name confirms the code is right.
    const response = await fetch(url + "/manifest.webmanifest", { cache: "no-store" });
    if (response.status === 404) return null;
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    return { url, name: data.name || url };
  }

  $("pick").addEventListener("submit", async (event) => {
    event.preventDefault();
    const url = KalviAddress.collegeUrl($("code").value);
    if (!url) return showPicker("Use only letters, numbers and hyphens in the college code.");
    $("find").disabled = true;
    try {
      const college = await lookUp(url);
      if (!college) return showPicker("We couldn't find a college with that code. Check it with your college office.");
      showConfirm(college);
      $("open").onclick = () => { remember(college); open(college.url); };
    } catch (e) {
      showPicker("We couldn't reach KalviOne. Check your mobile data or Wi-Fi and try again.");
    }
  });
  $("back").addEventListener("click", () => showPicker());

  const college = saved();
  if (college && college.url && !params.has("change")) {
    open(college.url);
  } else {
    if (college) $("code").value = college.url.replace("https://", "").split(".")[0];
    showPicker();
  }
})();
