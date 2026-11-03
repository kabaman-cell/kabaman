(function () {
  var KEY = "kabaman.site";
  var fallback = {
    slogan: "LA QUALITÉ PRIORITÉ",
    welcome: "KABAMAN.LOGISTIQUE",
    line: "From the world to your hands",
    prices: { importPerKg: 24.99, importMaxKg: 100, inspectionUsd: 99.99 },
    services: [
      { name: "Importation", note: "Up to 100 kg", line: "Service clé en main", price: "24,99 USD / kg", action: "" },
      { name: "Sourcing", note: "", line: "Trouvez les meilleurs fournisseurs", price: "19,99 USD", action: "" },
      { name: "Inspection", note: "", line: "Inspection des échantillons", price: "99,99 USD", action: "" },
    ],
  };
  var defaults = fallback;
  var current = fallback;
  var ready = false;
  var waiters = [];

  function readSaved() {
    try {
      var raw = localStorage.getItem(KEY);
      if (!raw) return null;
      var data = JSON.parse(raw);
      return data && typeof data === "object" ? data : null;
    } catch (err) {
      return null;
    }
  }

  function textOr(value, fallback) {
    return typeof value === "string" && value.trim() ? value.trim() : (fallback || "");
  }

  function numberOr(value, fallback) {
    var n = Number(value);
    return Number.isFinite(n) && n > 0 ? n : fallback;
  }

  function oldOfficialPrices(saved) {
    if (!saved) return false;
    var prices = saved.prices || {};
    var services = saved.services || [];
    var importPrice = services[0] && services[0].price;
    var sourcingPrice = services[1] && services[1].price;
    var inspectionPrice = services[2] && services[2].price;
    return Number(prices.importPerKg) === 25 &&
      Number(prices.inspectionUsd) === 100 &&
      (!importPrice || importPrice === "25 USD / kg") &&
      (!sourcingPrice || sourcingPrice === "Free") &&
      (!inspectionPrice || inspectionPrice === "100 USD");
  }

  function merge(base, saved) {
    if (oldOfficialPrices(saved)) {
      saved = Object.assign({}, saved, {
        prices: {},
        services: (saved.services || []).map(function (item) {
          var copy = Object.assign({}, item);
          delete copy.price;
          return copy;
        }),
      });
    }
    var basePrices = base.prices || fallback.prices;
    var savedPrices = saved && saved.prices ? saved.prices : {};
    var services = base.services.map(function (item, index) {
      var over = saved && saved.services && saved.services[index] ? saved.services[index] : {};
      var name = textOr(over.name, item.name);
      if (name === "Door to door service" || name === "Import Now" || name === "Source Now") name = item.name;
      return {
        name: name,
        note: textOr(over.note, item.note),
        line: textOr(over.line, item.line),
        price: textOr(over.price, item.price),
        action: (function () {
          var action = textOr(over.action, item.action);
          if (action === "Import Now" || action === "Source Now") return item.action || "";
          return action;
        })(),
      };
    });
    return {
      slogan: textOr(saved && saved.slogan, base.slogan),
      welcome: (function () {
        var welcome = textOr(saved && saved.welcome, base.welcome);
        if (welcome === "KABAMAN brings what you want to your door.") return base.welcome;
        return welcome;
      })(),
      line: textOr(saved && saved.line, base.line),
      prices: {
        importPerKg: numberOr(savedPrices.importPerKg, basePrices.importPerKg),
        importMaxKg: numberOr(savedPrices.importMaxKg, basePrices.importMaxKg),
        inspectionUsd: numberOr(savedPrices.inspectionUsd, basePrices.inspectionUsd),
      },
      services: services,
    };
  }

  function choiceLabel(item) {
    if (item.action && item.action !== item.name) return item.name + " — " + item.action;
    return item.name;
  }

  function apply(site) {
    current = site;
    var slogan = document.getElementById("brand-slogan");
    var welcome = document.getElementById("brand-welcome");
    var line = document.getElementById("brand-line");
    var footerSlogan = document.getElementById("footer-slogan");
    if (slogan) slogan.textContent = site.slogan;
    if (footerSlogan) footerSlogan.textContent = site.slogan;
    if (welcome) welcome.textContent = site.welcome;
    if (line) line.textContent = site.line;
    site.services.forEach(function (item, index) {
      var nameEl = document.getElementById("service-name-" + index);
      var noteEl = document.getElementById("service-note-" + index);
      var actionEl = document.getElementById("service-action-" + index);
      if (nameEl) nameEl.textContent = item.name;
      if (noteEl) noteEl.textContent = item.note || "";
      if (actionEl) actionEl.textContent = item.action || "";
      var button = document.querySelector('[data-pick-service="' + index + '"]');
      if (button) {
        var title = button.querySelector(".choice-title");
        var choiceLine = button.querySelector(".choice-line");
        var choicePrice = button.querySelector(".choice-price");
        var image = button.querySelector("img");
        if (title) title.textContent = item.name;
        else if (image) image.alt = item.name;
        else button.textContent = item.name;
        if (choiceLine) choiceLine.textContent = item.line || "";
        if (choicePrice) choicePrice.textContent = item.price || "";
        var label = item.name;
        if (item.line) label += ". " + item.line;
        if (item.price) label += ". " + item.price;
        button.setAttribute("aria-label", label);
      }
    });
    var select = document.getElementById("order-service");
    if (select) {
      var previous = select.value;
      select.replaceChildren();
      site.services.forEach(function (item, index) {
        var option = document.createElement("option");
        option.value = item.name;
        option.textContent = choiceLabel(item);
        if (index === 0 || item.name === previous) option.selected = true;
        select.appendChild(option);
      });
      if (![].some.call(select.options, function (option) { return option.selected; }) && select.options[0]) {
        select.options[0].selected = true;
      }
    }
    var help = document.getElementById("service-help");
    var maxKg = site.prices && site.prices.importMaxKg ? site.prices.importMaxKg : 100;
    if (help && site.services[0]) help.textContent = site.services[0].name + " is up to " + maxKg + " kg.";
    var pressed = document.querySelector('[data-pick-service][aria-pressed="true"]');
    var title = document.getElementById("service-detail-title");
    if (pressed && title && select) {
      var picked = Number(pressed.getAttribute("data-pick-service"));
      if (select.options[picked]) {
        select.selectedIndex = picked;
        title.textContent = select.options[picked].textContent;
      }
    }
  }

  function finish(site) {
    apply(site);
    ready = true;
    waiters.splice(0).forEach(function (fn) { fn(current); });
  }

  function load() {
    return fetch("site.json")
      .then(function (response) { return response.ok ? response.json() : fallback; })
      .catch(function () { return fallback; })
      .then(function (data) {
        defaults = data && data.slogan ? data : fallback;
        finish(merge(defaults, readSaved()));
        return current;
      });
  }

  function save(next) {
    localStorage.setItem(KEY, JSON.stringify(merge(defaults, next)));
    finish(merge(defaults, readSaved()));
    return current;
  }

  function reset() {
    localStorage.removeItem(KEY);
    finish(merge(defaults, null));
    return current;
  }

  window.KABAMAN_SITE = {
    key: KEY,
    get: function () { return current; },
    whenReady: function (fn) {
      if (ready) fn(current);
      else waiters.push(fn);
    },
    load: load,
    save: save,
    reset: reset,
  };

  load();
})();
