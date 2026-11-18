// Sort the predictions table in the browser (college and NFL pages). "Kickoff" is the server's
// order with the day headings; any other sort hides the headings and shows the day in the kickoff cell.
// The choice is remembered in this browser.
(function () {
  var table = document.getElementById("predictions");
  var select = document.getElementById("sort-select");
  var note = document.getElementById("sort-note");
  if (!table || !select) return;
  var body = table.tBodies[0];
  var original = Array.prototype.slice.call(body.rows);   // game rows and day headings, server order

  // Number from a data- attribute; blank means "no value" and sorts last
  function num(row, key) {
    var v = parseFloat(row.dataset[key]);
    return isNaN(v) ? null : v;
  }
  function ascending(a, b) { return (a === null) - (b === null) || (a === null ? 0 : a - b); }
  function descending(a, b) { return (a === null) - (b === null) || (a === null ? 0 : b - a); }

  var compare = {
    // Play, then Caution, then Pass, then no line; inside a tier, the bigger gap first
    spread: function (a, b) {
      return ascending(num(a, "tier"), num(b, "tier")) || descending(num(a, "gap"), num(b, "gap"));
    },
    total: function (a, b) { return descending(num(a, "tgap"), num(b, "tgap")); },
    away: function (a, b) { return a.dataset.away.localeCompare(b.dataset.away); },
    home: function (a, b) { return a.dataset.home.localeCompare(b.dataset.home); }
  };

  function apply(key) {
    if (!compare[key]) key = "kickoff";
    var rows = original;
    if (key !== "kickoff") {
      rows = original.filter(function (r) { return r.classList.contains("game"); });
      rows.sort(function (a, b) { return compare[key](a, b) || num(a, "order") - num(b, "order"); });
    }
    rows.forEach(function (r) { body.appendChild(r); });
    table.classList.toggle("sorted", key !== "kickoff");
    if (note) note.hidden = key !== "spread";
    select.value = key;
    try { localStorage.setItem("predictionsSort", key); } catch (e) {}
  }

  var saved = "kickoff";
  try { saved = localStorage.getItem("predictionsSort") || "kickoff"; } catch (e) {}
  apply(saved);
  select.addEventListener("change", function () { apply(select.value); });
})();
