(function () {
  var KEY = "kabaman.site";
  var fallback = {
    slogan: "LA QUALITÉ PRIORITÉ",
    welcome: "KABAMAN brings what you want to your door.",
    line: "From the world to your hands",
    services: [
      { name: "Importation", note: "Up to 100 kg", action: "" },
      { name: "Sourcing", note: "", action: "" },
      { name: "Inspection", note: "", action: "" },
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

  function merge(base, saved) {
    var services = base.services.map(function (item, index) {
      var over = saved && saved.services && saved.services[index];
      var name = over && typeof over.name === "string" && over.name.trim() ? over.name.trim() : item.name;
      if (name === "Door to door service" || name === "Import Now" || name === "Source Now") name = item.name;
      return { name: name, note: item.note, action: item.action };
    });
    return {
      slogan: saved && typeof saved.slogan === "string" && saved.slogan.trim() ? saved.slogan.trim() : base.slogan,
      welcome: saved && typeof saved.welcome === "string" && saved.welcome.trim() ? saved.welcome.trim() : base.welcome,
      line: base.line,
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
        var line = button.querySelector(".choice-line");
        var price = button.querySelector(".choice-price");
        var image = button.querySelector("img");
        if (title) title.textContent = item.name;
        else if (image) image.alt = item.name;
        else button.textContent = item.name;
        var label = item.name;
        if (line && line.textContent) label += ". " + line.textContent;
        if (price && price.textContent) label += ". " + price.textContent;
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
    if (help && site.services[0]) help.textContent = site.services[0].name + " is up to 100 kg.";
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
