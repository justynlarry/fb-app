// The "Bet" form on the predictions pages.  A row's Bet button opens the dialog prefilled with
// that game's line, our side and the best price we saw; the user edits and saves to /api/bets.
// Lines are typed for the side bet on (+3.5); spreads are saved as the HOME team's number.
(function () {
  var dialog = document.getElementById("bet-dialog");
  if (!dialog || typeof dialog.showModal !== "function") return;
  function el(id) { return document.getElementById(id); }
  var form = el("bet-form"), sideA = el("bet-side-a"), sideB = el("bet-side-b");
  var line = el("bet-line"), price = el("bet-price"), book = el("bet-book"), stake = el("bet-stake");
  var message = el("bet-message");
  var game = null, button = null;     // the row's data and its button

  function num(v) { var n = parseFloat(String(v).replace("−", "-")); return isNaN(n) ? null : n; }
  function signed(n) { return n === null ? "" : (n > 0 ? "+" + n : String(n)); }
  function betType() { return form.querySelector('input[name="bet_type"]:checked').value; }
  function side() { var s = form.querySelector('input[name="side"]:checked'); return s ? s.value : null; }
  function show(text, isError) { message.textContent = text; message.classList.toggle("error", !!isError); }
  function remembered(key) { try { return localStorage.getItem(key) || ""; } catch (e) { return ""; } }
  function remember(key, value) { try { localStorage.setItem(key, value); } catch (e) {} }

  // Only books the user can bet at are prefilled (Bovada and the rest are reference lines only)
  var BETTABLE = ["MyBookie", "DraftKings", "FanDuel", "BetMGM", "Caesars", "Fanatics"];
  function bookOrLast(name) { return BETTABLE.indexOf(name) >= 0 ? name : remembered("betBook"); }

  function chooseSide(value) { (sideA.value === value ? sideA : sideB).checked = true; }

  // Labels, side choices and prefilled numbers for the chosen bet type
  function setType(t) {
    form.querySelector('input[name="bet_type"][value="' + t + '"]').checked = true;
    var isTotal = t === "total";
    sideA.value = isTotal ? "over" : "away";
    sideB.value = isTotal ? "under" : "home";
    el("bet-side-a-name").textContent = isTotal ? "Over" : game.away;
    el("bet-side-b-name").textContent = isTotal ? "Under" : game.home;
    el("bet-line-field").hidden = t === "moneyline";
    el("bet-line-label").textContent = isTotal ? "Total" : "Line (your team's number)";

    if (t === "total") {
      chooseSide(game.totalSide || "over");
      line.value = game.total;
      price.value = game.totalPrice ? signed(num(game.totalPrice)) : "-110";
      book.value = bookOrLast(game.totalBook);
    } else {
      chooseSide(game.side || "away");
      var home = num(game.spread);
      line.value = t === "spread" && home !== null ? signed(side() === "home" ? home : -home) : "";
      price.value = t === "spread" ? (game.price ? signed(num(game.price)) : "-110") : "";
      book.value = t === "spread" ? bookOrLast(game.book) : remembered("betBook");
    }
  }

  function open(btn) {
    button = btn;
    game = btn.dataset;
    el("bet-game").textContent = game.away + " at " + game.home;
    setType("spread");
    stake.value = remembered("betStake");
    el("bet-note").value = "";
    show("");
    dialog.showModal();
  }

  // Any Bet button (rows can be re-sorted, so listen on the document)
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".bet-link");
    if (btn) open(btn);
  });
  form.querySelectorAll('input[name="bet_type"]').forEach(function (r) {
    r.addEventListener("change", function () { setType(r.value); });
  });
  // Switching sides of a spread flips the number: Michigan +3.5 is Ohio State -3.5
  [sideA, sideB].forEach(function (r) {
    r.addEventListener("change", function () {
      if (betType() === "spread" && num(line.value) !== null) line.value = signed(-num(line.value));
    });
  });
  el("bet-cancel").addEventListener("click", function () { dialog.close(); });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var t = betType(), s = side(), l = num(line.value), p = num(price.value), amount = num(stake.value);
    if (!s) return show("Pick a side.", true);
    if (t !== "moneyline" && l === null) return show(t === "total" ? "Enter the total." : "Enter the line, like +3.5.", true);
    if (p === null || Math.abs(p) < 100 || p !== Math.round(p)) return show("Price must be American odds, like -110 or +150.", true);
    if (!book.value.trim()) return show("Which book?", true);
    if (amount === null || amount <= 0) return show("Enter the stake in dollars.", true);

    // Spreads are stored as the home team's number
    var saved = t === "moneyline" ? null : (t === "spread" && s === "away" ? -l : l);
    show("Saving…");
    fetch("/api/bets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_id: parseInt(game.game, 10), bet_type: t, side: s, line: saved,
                             price: p, book: book.value.trim(), stake: amount.toFixed(2),
                             note: el("bet-note").value.trim() })
    }).then(function (r) {
      return r.json().then(function (body) { return { ok: r.ok, body: body }; });
    }).then(function (res) {
      if (!res.ok) {
        var detail = res.body && res.body.detail;
        return show(typeof detail === "string" ? detail : "Couldn't save that bet. Check the numbers.", true);
      }
      remember("betBook", book.value.trim());
      remember("betStake", amount.toFixed(2));
      button.textContent = "Bet ✓";
      button.classList.add("bet-saved");
      message.innerHTML = 'Saved. <a href="/bets">My bets</a>';
      setTimeout(function () { dialog.close(); }, 1500);
    }).catch(function () { show("Couldn't reach the server.", true); });
  });
})();
