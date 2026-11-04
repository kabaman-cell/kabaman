(function () {
  var KEY = "kabaman.site";
  var FORMS = ["sourcing", "importation", "inspection", "products", "auction"];
  var NAME_FORM = {
    importation: "importation",
    sourcing: "sourcing",
    inspection: "inspection",
    products: "products",
    auction: "auction",
    auctions: "auction",
    "door to door service": "importation",
    "import now": "importation",
    "source now": "sourcing",
  };
  var LEGACY_INDEX_FORM = ["importation", "sourcing", "inspection", "products", "auction"];
  var fallback = {
    slogan: "LA QUALITÉ PRIORITÉ",
    welcome: "KABAMAN.LOGISTIQUE",
    line: "From the world to your hands",
    prices: { importPerKg: 24.99, importMaxKg: 100, inspectionUsd: 99.99 },
    theme: {
      background: "#070707",
      text: "#f6efd9",
      accent: "#d4af37",
      buttonBackground: "#0b0b0b",
      buttonText: "#d4af37",
      buttonCorners: "square",
      shimmer: true,
      logo: "",
    },
    services: [
      { name: "Sourcing", note: "", line: "Trouvez les meilleurs fournisseurs", price: "19,99 USD", action: "", form: "sourcing" },
      { name: "Importation", note: "Up to 100 kg", line: "Service clé en main", price: "24,99 USD / kg", action: "", form: "importation" },
      { name: "Inspection", note: "", line: "Inspection des échantillons", price: "99,99 USD", action: "", form: "inspection" },
      { name: "Auctions", note: "", line: "Unfinished imports and unsold goods", price: "Place a bid", action: "", form: "auction" },
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

  function textOr(value, fallbackText) {
    return typeof value === "string" && value.trim() ? value.trim() : (fallbackText || "");
  }

  function textKeep(value, fallbackText) {
    if (typeof value === "string") return value.trim();
    return fallbackText || "";
  }

  function numberOr(value, fallbackNumber) {
    var n = Number(value);
    return Number.isFinite(n) && n > 0 ? n : fallbackNumber;
  }

  function hexToRgb(hex) {
    var text = String(hex || "").replace("#", "").trim();
    if (text.length === 3) text = text[0] + text[0] + text[1] + text[1] + text[2] + text[2];
    if (!/^[0-9a-fA-F]{6}$/.test(text)) return null;
    var n = parseInt(text, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  function rgbToHex(rgb) {
    return "#" + rgb.map(function (channel) {
      var value = Math.max(0, Math.min(255, Math.round(channel)));
      return (value < 16 ? "0" : "") + value.toString(16);
    }).join("");
  }

  function colorOr(value, fallbackColor) {
    var rgb = hexToRgb(value);
    return rgb ? rgbToHex(rgb) : fallbackColor;
  }

  function mix(from, to, amount) {
    var left = hexToRgb(from);
    var right = hexToRgb(to);
    if (!left || !right) return from;
    return rgbToHex(left.map(function (channel, index) {
      return channel + (right[index] - channel) * amount;
    }));
  }

  function hexToRgba(hex, alpha) {
    var rgb = hexToRgb(hex);
    if (!rgb) return "rgba(212, 175, 55, " + alpha + ")";
    return "rgba(" + rgb[0] + ", " + rgb[1] + ", " + rgb[2] + ", " + alpha + ")";
  }

  function logoOr(value) {
    if (typeof value !== "string") return "";
    var text = value.trim();
    if (!text) return "";
    if (text.indexOf("data:image/") !== 0) return "";
    if (text.length > 700000) return "";
    return text;
  }

  function knownForm(value) {
    var key = String(value || "").trim().toLowerCase();
    if (key === "import") return "importation";
    return FORMS.indexOf(key) >= 0 ? key : "";
  }

  function formFromItem(item, index, allowIndexFallback) {
    var explicit = knownForm(item && item.form);
    if (explicit) return explicit;
    var name = String(item && item.name || "").trim().toLowerCase();
    if (NAME_FORM[name]) return NAME_FORM[name];
    if (allowIndexFallback && index >= 0 && index < LEGACY_INDEX_FORM.length) return LEGACY_INDEX_FORM[index];
    return "importation";
  }

  function findBase(list, form) {
    for (var i = 0; i < list.length; i += 1) {
      if (formFromItem(list[i], i, false) === form) return list[i];
    }
    return null;
  }

  function normalizeService(item, index, baseList) {
    var source = item && typeof item === "object" ? item : {};
    var form = formFromItem(source, index, true);
    var base = findBase(baseList, form) || { name: "Service", note: "", line: "", price: "", action: "", form: form };
    var name = textOr(source.name, base.name || "Service");
    if (name === "Door to door service" || name === "Import Now" || name === "Source Now") name = base.name || name;
    var action = textKeep(source.action, base.action || "");
    if (action === "Import Now" || action === "Source Now") action = base.action || "";
    return {
      name: name,
      note: textKeep(source.note, base.note || ""),
      line: textKeep(source.line, base.line || ""),
      price: textKeep(source.price, base.price || ""),
      action: action,
      form: form,
    };
  }

  function oldOfficialPrices(saved) {
    if (!saved) return false;
    var prices = saved.prices || {};
    var services = saved.services || [];
    function priceOf(name, index) {
      for (var i = 0; i < services.length; i += 1) {
        if (services[i] && services[i].name === name) return services[i].price;
      }
      return services[index] && services[index].price;
    }
    var importPrice = priceOf("Importation", 0);
    var sourcingPrice = priceOf("Sourcing", 1);
    var inspectionPrice = priceOf("Inspection", 2);
    return Number(prices.importPerKg) === 25 &&
      Number(prices.inspectionUsd) === 100 &&
      (!importPrice || importPrice === "25 USD / kg") &&
      (!sourcingPrice || sourcingPrice === "Free") &&
      (!inspectionPrice || inspectionPrice === "100 USD");
  }

  var PREVIOUS_OFFICIAL_FIVE = [
    ["sourcing", "sourcing"],
    ["importation", "importation"],
    ["inspection", "inspection"],
    ["products", "products"],
    ["auction", "auction"],
  ];

  function isProductsService(item) {
    var name = String(item && item.name || "").trim().toLowerCase();
    var form = String(item && item.form || "").trim().toLowerCase();
    if (name === "product") name = "products";
    if (form === "product") form = "products";
    return name === "products" || form === "products";
  }

  function dropProducts(list) {
    return (list || []).filter(function (item) { return !isProductsService(item); });
  }

  function isPreviousOfficialFive(list) {
    if (!list || list.length !== PREVIOUS_OFFICIAL_FIVE.length) return false;
    for (var i = 0; i < PREVIOUS_OFFICIAL_FIVE.length; i += 1) {
      var item = list[i];
      var name = String(item && item.name || "").trim().toLowerCase();
      var form = knownForm(item && item.form) || NAME_FORM[name] || "";
      if (name !== PREVIOUS_OFFICIAL_FIVE[i][0] || form !== PREVIOUS_OFFICIAL_FIVE[i][1]) return false;
    }
    return true;
  }

  function landingQuad(services) {
    var order = ["sourcing", "importation", "inspection", "auction"];
    if (!services || services.length < order.length) return false;
    for (var i = 0; i < order.length; i += 1) {
      if (!services[i] || services[i].form !== order[i]) return false;
    }
    return true;
  }

  function servicesFrom(base, saved) {
    var savedList = saved && Array.isArray(saved.services) ? saved.services : null;
    if (savedList && isPreviousOfficialFive(savedList)) {
      return base.services.map(function (item, index) {
        return normalizeService(item, index, base.services);
      });
    }
    if (savedList) savedList = dropProducts(savedList);
    var source = savedList && savedList.length ? savedList : base.services;
    var legacy = !savedList || !savedList.length || savedList.every(function (item) {
      return !item || !knownForm(item.form);
    });
    var services = source.map(function (item, index) {
      return normalizeService(item, index, base.services);
    }).filter(function (item) { return item && item.name && item.form; });
    if (legacy) {
      var present = {};
      services.forEach(function (item) { present[item.form] = true; });
      base.services.forEach(function (item, index) {
        var form = formFromItem(item, index, false);
        if (present[form]) return;
        services.push(normalizeService(item, index, base.services));
        present[form] = true;
      });
    }
    services = dropProducts(services);
    if (!services.length) {
      services = base.services.map(function (item, index) {
        return normalizeService(item, index, base.services);
      });
    }
    return services;
  }

  function themeFrom(base, saved) {
    var baseTheme = base.theme || fallback.theme;
    var savedTheme = saved && saved.theme && typeof saved.theme === "object" ? saved.theme : {};
    var corners = savedTheme.buttonCorners;
    if (corners !== "rounded" && corners !== "square") corners = baseTheme.buttonCorners === "rounded" ? "rounded" : "square";
    return {
      background: colorOr(savedTheme.background, baseTheme.background || "#070707"),
      text: colorOr(savedTheme.text, baseTheme.text || "#f6efd9"),
      accent: colorOr(savedTheme.accent, baseTheme.accent || "#d4af37"),
      buttonBackground: colorOr(savedTheme.buttonBackground, baseTheme.buttonBackground || "#0b0b0b"),
      buttonText: colorOr(savedTheme.buttonText, baseTheme.buttonText || "#d4af37"),
      buttonCorners: corners,
      shimmer: typeof savedTheme.shimmer === "boolean" ? savedTheme.shimmer : baseTheme.shimmer !== false,
      logo: logoOr(savedTheme.logo),
    };
  }

  function merge(base, saved) {
    var source = saved;
    if (oldOfficialPrices(source)) {
      source = Object.assign({}, source, {
        prices: {},
        services: (source.services || []).map(function (item) {
          var copy = Object.assign({}, item);
          if (copy.price === "25 USD / kg" || copy.price === "Free" || copy.price === "100 USD") delete copy.price;
          return copy;
        }),
      });
    }
    var basePrices = base.prices || fallback.prices;
    var savedPrices = source && source.prices ? source.prices : {};
    return {
      slogan: textOr(source && source.slogan, base.slogan),
      welcome: (function () {
        var welcome = textOr(source && source.welcome, base.welcome);
        if (welcome === "KABAMAN brings what you want to your door.") return base.welcome;
        return welcome;
      })(),
      line: textOr(source && source.line, base.line),
      prices: {
        importPerKg: numberOr(savedPrices.importPerKg, basePrices.importPerKg),
        importMaxKg: numberOr(savedPrices.importMaxKg, basePrices.importMaxKg),
        inspectionUsd: numberOr(savedPrices.inspectionUsd, basePrices.inspectionUsd),
      },
      theme: themeFrom(base, source),
      services: servicesFrom(base, source),
    };
  }

  function choiceLabel(item) {
    if (item.action && item.action !== item.name) return item.name + " — " + item.action;
    return item.name;
  }

  function renderChoices(site) {
    var grid = document.getElementById("service-choices");
    if (!grid) return -1;
    var pressed = grid.querySelector('[aria-pressed="true"]');
    var pressedIndex = pressed ? Number(pressed.getAttribute("data-pick-service")) : -1;
    grid.classList.toggle("landing-quad", landingQuad(site.services));
    grid.replaceChildren();
    site.services.forEach(function (item, index) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "choice-btn";
      button.setAttribute("data-pick-service", String(index));
      button.setAttribute("data-form", item.form);
      var label = item.name;
      if (item.line) label += ". " + item.line;
      if (item.price) label += ". " + item.price;
      button.setAttribute("aria-label", label);
      button.setAttribute("aria-pressed", index === pressedIndex ? "true" : "false");
      var mark = document.createElement("span");
      mark.className = "choice-mark";
      mark.setAttribute("aria-hidden", "true");
      var title = document.createElement("span");
      title.className = "choice-title";
      title.textContent = item.name;
      var line = document.createElement("span");
      line.className = "choice-line";
      line.textContent = item.line || "";
      var price = document.createElement("span");
      price.className = "choice-price";
      price.textContent = item.price || "";
      button.append(mark, title, line, price);
      grid.appendChild(button);
    });
    if (pressedIndex >= site.services.length) pressedIndex = -1;
    return pressedIndex;
  }

  function applyLogo(theme) {
    var src = theme.logo || "assets/logo.jpg?v=circle";
    document.querySelectorAll(".logo-full, .brand-mark img").forEach(function (img) {
      if (img.getAttribute("src") !== src) img.setAttribute("src", src);
    });
    var icon = document.querySelector('link[rel="icon"]');
    if (icon) icon.href = src;
  }

  function applyTheme(site) {
    if (!document.body || !document.body.classList.contains("customer")) return;
    var theme = site.theme || fallback.theme;
    var root = document.documentElement;
    var background = theme.background;
    var accent = theme.accent;
    var buttonBackground = theme.buttonBackground;
    var classicPage = background === "#070707" && accent === "#d4af37";
    var classicButton = buttonBackground === "#0b0b0b";
    root.style.setProperty("--page-bg", background);
    root.style.setProperty("--page-glow", classicPage ? "#2a220c" : mix(background, accent, 0.22));
    root.style.setProperty("--text", theme.text);
    root.style.setProperty("--cream", theme.text);
    root.style.setProperty("--gold", accent);
    root.style.setProperty("--gold-soft", accent === "#d4af37" ? "#f0d78c" : mix(accent, "#ffffff", 0.62));
    root.style.setProperty("--line", hexToRgba(accent, 0.35));
    root.style.setProperty("--black", background);
    root.style.setProperty("--btn-bg", buttonBackground);
    root.style.setProperty("--btn-bg-top", classicButton ? "#1a160c" : mix(buttonBackground, accent, 0.18));
    root.style.setProperty("--btn-bg-selected", classicButton ? "#14110a" : mix(buttonBackground, "#000000", 0.2));
    root.style.setProperty("--btn-bg-selected-top", classicButton ? "#3a2e10" : mix(buttonBackground, accent, 0.4));
    root.style.setProperty("--btn-text", theme.buttonText);
    root.style.setProperty("--btn-radius", theme.buttonCorners === "rounded" ? "20px" : "0px");
    root.classList.toggle("no-shimmer", theme.shimmer === false);
    applyLogo(theme);
  }

  function apply(site) {
    current = site;
    applyTheme(site);
    var slogan = document.getElementById("brand-slogan");
    var welcome = document.getElementById("brand-welcome");
    var line = document.getElementById("brand-line");
    var footerSlogan = document.getElementById("footer-slogan");
    if (slogan) slogan.textContent = site.slogan;
    if (footerSlogan) footerSlogan.textContent = site.slogan;
    if (welcome) welcome.textContent = site.welcome;
    if (line) line.textContent = site.line;
    var pressedIndex = renderChoices(site);
    site.services.forEach(function (item, index) {
      var nameEl = document.getElementById("service-name-" + index);
      var noteEl = document.getElementById("service-note-" + index);
      var actionEl = document.getElementById("service-action-" + index);
      if (nameEl) nameEl.textContent = item.name;
      if (noteEl) noteEl.textContent = item.note || "";
      if (actionEl) actionEl.textContent = item.action || "";
    });
    var select = document.getElementById("order-service");
    if (select) {
      select.replaceChildren();
      site.services.forEach(function (item, index) {
        var option = document.createElement("option");
        option.value = String(index);
        option.textContent = choiceLabel(item);
        option.setAttribute("data-form", item.form);
        select.appendChild(option);
      });
      if (pressedIndex >= 0 && select.options[pressedIndex]) select.selectedIndex = pressedIndex;
      else if (select.options[0]) select.selectedIndex = 0;
    }
    var help = document.getElementById("service-help");
    var maxKg = site.prices && site.prices.importMaxKg ? site.prices.importMaxKg : 100;
    var importation = site.services.filter(function (item) { return item.form === "importation"; })[0];
    if (help && importation) help.textContent = importation.name + " is up to " + maxKg + " kg.";
    var title = document.getElementById("service-detail-title");
    if (pressedIndex >= 0 && title && select && select.options[pressedIndex]) {
      title.textContent = select.options[pressedIndex].textContent;
    }
  }

  function finish(site) {
    apply(site);
    ready = true;
    waiters.splice(0).forEach(function (fn) { fn(current); });
  }

  function migrateSavedSite(base) {
    var saved = readSaved();
    if (!saved || !Array.isArray(saved.services)) return saved;
    var services = saved.services;
    var changed = false;
    if (isPreviousOfficialFive(services)) {
      services = base.services.map(function (item) { return Object.assign({}, item); });
      changed = true;
    } else if (services.some(isProductsService)) {
      services = dropProducts(services);
      changed = true;
    }
    if (!changed) return saved;
    var next = Object.assign({}, saved, { services: services });
    try {
      localStorage.setItem(KEY, JSON.stringify(next));
    } catch (err) {
      /* keep the in-memory list even if this browser refuses the write */
    }
    return next;
  }

  function load() {
    return fetch("site.json")
      .then(function (response) { return response.ok ? response.json() : fallback; })
      .catch(function () { return fallback; })
      .then(function (data) {
        defaults = data && data.slogan ? data : fallback;
        var saved = migrateSavedSite(defaults);
        var remote = window.KABAMAN_API ? window.KABAMAN_API.site() : Promise.resolve(null);
        return remote.then(function (serverSite) {
          finish(merge(defaults, serverSite || saved));
          return current;
        });
      });
  }

  function remember(site) {
    try {
      localStorage.setItem(KEY, JSON.stringify(site));
    } catch (err) {
      if (site.theme) site = Object.assign({}, site, { theme: Object.assign({}, site.theme, { logo: "" }) });
      try { localStorage.setItem(KEY, JSON.stringify(site)); } catch (err2) { /* the server copy can still be saved */ }
    }
    finish(site);
    return current;
  }

  function save(next) {
    var merged = merge(defaults, next);
    if (window.KABAMAN_API && window.KABAMAN_API.usingServer()) {
      return window.KABAMAN_API.saveSite(merged).then(function (remote) {
        return remember(merge(defaults, remote || merged));
      });
    }
    return remember(merged);
  }

  function reset() {
    localStorage.removeItem(KEY);
    if (window.KABAMAN_API && window.KABAMAN_API.usingServer()) {
      return window.KABAMAN_API.resetSite().then(function (remote) {
        return remember(merge(defaults, remote));
      });
    }
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

  apply(current);
  load();
})();
