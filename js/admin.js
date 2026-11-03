(function () {
  if (!window.KABAMAN || !window.KABAMAN_SITE) return;

  var form = document.getElementById("site-form");
  var sloganInput = document.getElementById("edit-slogan");
  var welcomeInput = document.getElementById("edit-welcome");
  var lineInput = document.getElementById("edit-line");
  var importRate = document.getElementById("edit-import-rate");
  var importMax = document.getElementById("edit-import-max");
  var inspectionUsd = document.getElementById("edit-inspection-usd");
  var backgroundInput = document.getElementById("edit-bg");
  var textInput = document.getElementById("edit-text");
  var accentInput = document.getElementById("edit-accent");
  var buttonBgInput = document.getElementById("edit-btn-bg");
  var buttonTextInput = document.getElementById("edit-btn-text");
  var cornersInput = document.getElementById("edit-corners");
  var shimmerInput = document.getElementById("edit-shimmer");
  var logoInput = document.getElementById("edit-logo");
  var logoPreview = document.getElementById("logo-preview");
  var siteNote = document.getElementById("site-note");
  var draft = [];
  var logoValue = "";
  var FORM_TYPES = ["sourcing", "importation", "inspection", "products", "auction"];
  var list = document.getElementById("order-list");
  var filters = document.getElementById("order-filters");
  var openRef = "";
  var activeFilter = "All";
  var tones = {
    "Verified": "status-verified",
    "Not verified": "status-not-verified",
  };

  function showLogo() {
    if (!logoPreview) return;
    logoPreview.src = logoValue || "assets/logo.jpg?v=circle";
  }

  function readFile(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () { resolve(String(reader.result || "")); };
      reader.onerror = function () { reject(reader.error); };
      reader.readAsDataURL(file);
    });
  }

  function compressLogo(file) {
    return readFile(file).then(function (dataUrl) {
      return new Promise(function (resolve) {
        var img = new Image();
        img.onload = function () {
          var max = 640;
          var width = img.width || max;
          var height = img.height || max;
          var scale = Math.min(1, max / Math.max(width, height));
          width = Math.max(1, Math.round(width * scale));
          height = Math.max(1, Math.round(height * scale));
          var canvas = document.createElement("canvas");
          canvas.width = width;
          canvas.height = height;
          var ctx = canvas.getContext("2d");
          ctx.clearRect(0, 0, width, height);
          ctx.drawImage(img, 0, 0, width, height);
          var png = canvas.toDataURL("image/png");
          if (png.indexOf("data:image/") === 0 && png.length <= 280000) {
            resolve(png);
            return;
          }
          ctx.fillStyle = "#070707";
          ctx.fillRect(0, 0, width, height);
          ctx.drawImage(img, 0, 0, width, height);
          var quality = 0.82;
          var out = canvas.toDataURL("image/jpeg", quality);
          while (out.length > 280000 && quality > 0.45) {
            quality -= 0.1;
            out = canvas.toDataURL("image/jpeg", quality);
          }
          resolve(out.indexOf("data:image/") === 0 ? out : "");
        };
        img.onerror = function () { resolve(""); };
        img.src = dataUrl;
      });
    }).catch(function () { return ""; });
  }

  function moneyLine(value, suffix) {
    var amount = Number(value);
    if (!Number.isFinite(amount)) return "";
    return amount.toFixed(2).replace(".", ",") + suffix;
  }

  function preset(form) {
    var rate = moneyLine(importRate.value, " USD / kg") || "24,99 USD / kg";
    var inspection = moneyLine(inspectionUsd.value, " USD") || "99,99 USD";
    var map = {
      sourcing: { name: "Sourcing", line: "Trouvez les meilleurs fournisseurs", price: "19,99 USD" },
      importation: { name: "Importation", line: "Service clé en main", price: rate },
      inspection: { name: "Inspection", line: "Inspection des échantillons", price: inspection },
      products: { name: "Products", line: "Available goods", price: "On request" },
      auction: { name: "Auction", line: "Unfinished imports and unsold goods", price: "Place a bid" },
    };
    var item = map[form] || map.sourcing;
    return { name: item.name, note: "", line: item.line, price: item.price, action: "", form: form };
  }

  function knownForm(value) {
    return FORM_TYPES.indexOf(value) >= 0 ? value : "sourcing";
  }

  function readDraft() {
    var cards = document.querySelectorAll("#service-editors [data-service-index]");
    if (!cards.length) return;
    var next = [];
    cards.forEach(function (card, index) {
      var prev = draft[index] || {};
      var name = card.querySelector(".edit-name").value.trim();
      next.push({
        name: name || prev.name || "Service",
        note: prev.note || "",
        line: card.querySelector(".edit-line").value.trim(),
        price: card.querySelector(".edit-price").value.trim(),
        action: prev.action || "",
        form: knownForm(card.querySelector(".edit-form").value),
      });
    });
    draft = next;
  }

  function labeledInput(labelText, className, value, max, required) {
    var label = document.createElement("label");
    label.appendChild(document.createTextNode(labelText));
    var input = document.createElement("input");
    input.type = "text";
    input.className = className;
    input.maxLength = max;
    input.value = value || "";
    input.required = !!required;
    label.appendChild(input);
    return label;
  }

  function toolButton(text, disabled, onClick) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = text === "Remove" ? "btn-quiet danger" : "btn-quiet";
    button.textContent = text;
    button.disabled = !!disabled;
    button.addEventListener("click", onClick);
    return button;
  }

  function renderEditors() {
    var host = document.getElementById("service-editors");
    if (!host) return;
    host.replaceChildren();
    draft.forEach(function (item, index) {
      var box = document.createElement("fieldset");
      box.className = "admin-service";
      box.setAttribute("data-service-index", String(index));
      var legend = document.createElement("legend");
      legend.textContent = (item.name || "Button") + " — " + item.form;
      box.appendChild(legend);
      var nameField = labeledInput("Name", "edit-name", item.name, 60, true);
      nameField.querySelector("input").addEventListener("input", function (event) {
        legend.textContent = (event.target.value.trim() || "Button") + " — " + (box.querySelector(".edit-form").value || item.form);
      });
      box.appendChild(nameField);
      box.appendChild(labeledInput("Subtitle", "edit-line", item.line, 80, false));
      box.appendChild(labeledInput("Price line", "edit-price", item.price, 80, false));
      var formLabel = document.createElement("label");
      formLabel.appendChild(document.createTextNode("Form"));
      var select = document.createElement("select");
      select.className = "edit-form";
      [
        ["sourcing", "Sourcing"],
        ["importation", "Importation"],
        ["inspection", "Inspection"],
        ["products", "Products"],
        ["auction", "Auction"],
      ].forEach(function (pair) {
        var option = document.createElement("option");
        option.value = pair[0];
        option.textContent = pair[1];
        if (pair[0] === item.form) option.selected = true;
        select.appendChild(option);
      });
      select.addEventListener("change", function () {
        readDraft();
        renderEditors();
      });
      formLabel.appendChild(select);
      box.appendChild(formLabel);
      var tools = document.createElement("div");
      tools.className = "admin-service-tools";
      tools.appendChild(toolButton("Move up", index === 0, function () {
        readDraft();
        if (index === 0) return;
        var swap = draft[index - 1];
        draft[index - 1] = draft[index];
        draft[index] = swap;
        renderEditors();
      }));
      tools.appendChild(toolButton("Move down", index === draft.length - 1, function () {
        readDraft();
        if (index === draft.length - 1) return;
        var swap = draft[index + 1];
        draft[index + 1] = draft[index];
        draft[index] = swap;
        renderEditors();
      }));
      tools.appendChild(toolButton("Remove", draft.length <= 1, function () {
        readDraft();
        if (draft.length <= 1) return;
        draft.splice(index, 1);
        renderEditors();
      }));
      box.appendChild(tools);
      host.appendChild(box);
    });
  }

  function paintLinkedPrices(formName, text) {
    if (!text) return;
    document.querySelectorAll("#service-editors [data-service-index]").forEach(function (card) {
      if (card.querySelector(".edit-form").value !== formName) return;
      var price = card.querySelector(".edit-price");
      if (price) price.value = text;
    });
  }

  function fillForm(site) {
    var prices = site.prices || {};
    var theme = site.theme || {};
    sloganInput.value = site.slogan;
    welcomeInput.value = site.welcome;
    lineInput.value = site.line || "";
    importRate.value = prices.importPerKg || 24.99;
    importMax.value = prices.importMaxKg || 100;
    inspectionUsd.value = prices.inspectionUsd || 99.99;
    backgroundInput.value = theme.background || "#070707";
    textInput.value = theme.text || "#f6efd9";
    accentInput.value = theme.accent || "#d4af37";
    buttonBgInput.value = theme.buttonBackground || "#0b0b0b";
    buttonTextInput.value = theme.buttonText || "#d4af37";
    cornersInput.value = theme.buttonCorners === "rounded" ? "rounded" : "square";
    shimmerInput.checked = theme.shimmer !== false;
    logoValue = theme.logo || "";
    if (logoInput) logoInput.value = "";
    showLogo();
    draft = (site.services || []).map(function (item) {
      return {
        name: item.name,
        note: item.note || "",
        line: item.line || "",
        price: item.price || "",
        action: item.action || "",
        form: knownForm(item.form),
      };
    });
    renderEditors();
  }

  function serviceKind(order) {
    var goods = (order && order.goods) || {};
    var serviceId = order && order.services && order.services[0] && order.services[0].id;
    var serviceName = goods.service || (order && order.services && order.services[0] && order.services[0].name) || "";
    var byId = {
      inspection: "inspection",
      products: "products",
      auction: "auction",
      sourcing: "sourcing",
      importation: "import",
      import: "import",
    };
    if (byId[serviceId]) return byId[serviceId];
    if (serviceName === "Inspection") return "inspection";
    if (serviceName === "Products") return "products";
    if (serviceName === "Auction") return "auction";
    if (serviceName === "Sourcing") return "sourcing";
    return "import";
  }

  function field(label, value) {
    if (!value) return null;
    var wrap = document.createElement("p");
    var strong = document.createElement("strong");
    strong.textContent = label + ": ";
    wrap.append(strong, document.createTextNode(String(value)));
    return wrap;
  }

  function idView(order) {
    var contact = order.contact || {};
    var image = contact.idImage || "";
    if (!image) {
      var note = contact.idFileName ? contact.idFileName + " — No picture saved" : "";
      return field("ID", note);
    }
    var link = document.createElement("a");
    link.href = image;
    link.target = "_blank";
    link.rel = "noopener";
    link.className = "admin-id-link";
    if (image.indexOf("data:application/pdf") === 0) {
      link.textContent = "Open ID (" + (contact.idFileName || "PDF") + ")";
      return link;
    }
    var img = document.createElement("img");
    img.className = "admin-id";
    img.src = image;
    img.alt = "ID document for " + order.ref;
    link.appendChild(img);
    return link;
  }

  function paintOrders() {
    var rows = window.KABAMAN.readOrders().slice().reverse();
    var statuses = window.KABAMAN.orderStatuses;
    filters.replaceChildren();
    var counts = { All: rows.length };
    statuses.forEach(function (label) { counts[label] = 0; });
    rows.forEach(function (order) {
      counts[window.KABAMAN.orderStatus(order)] += 1;
    });
    ["All"].concat(statuses).forEach(function (label) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = label + " (" + counts[label] + ")";
      if (label === activeFilter) button.className = "is-active";
      button.addEventListener("click", function () {
        activeFilter = label;
        paintOrders();
      });
      filters.appendChild(button);
    });

    list.replaceChildren();
    if (!rows.length) {
      var empty = document.createElement("p");
      empty.textContent = "No orders yet.";
      list.appendChild(empty);
      return;
    }

    var groups = activeFilter === "All" ? statuses : [activeFilter];
    var shown = 0;
    groups.forEach(function (label) {
      var groupRows = rows.filter(function (order) {
        return window.KABAMAN.orderStatus(order) === label;
      });
      if (!groupRows.length) return;
      shown += groupRows.length;
      var section = document.createElement("section");
      section.className = "order-group";
      var heading = document.createElement("h3");
      heading.textContent = label;
      section.appendChild(heading);
      section.appendChild(orderTable(groupRows));
      list.appendChild(section);
    });
    if (!shown) {
      var none = document.createElement("p");
      none.textContent = "No orders in " + activeFilter + ".";
      list.appendChild(none);
    }
  }

  function orderTable(rows) {
    var wrap = document.createElement("div");
    wrap.className = "admin-table-wrap";
    var table = document.createElement("table");
    table.className = "admin-table";
    var head = document.createElement("thead");
    var headRow = document.createElement("tr");
    ["Reference", "Customer", "Service", "Product link", "Status", "Actions"].forEach(function (name) {
      var th = document.createElement("th");
      th.textContent = name;
      headRow.appendChild(th);
    });
    head.appendChild(headRow);
    var body = document.createElement("tbody");
    rows.forEach(function (order) {
      body.appendChild(orderRow(order));
      if (openRef === order.ref) body.appendChild(detailRow(order));
    });
    table.append(head, body);
    wrap.appendChild(table);
    return wrap;
  }

  function orderRow(order) {
    var goods = order.goods || {};
    var contact = order.contact || {};
    var status = window.KABAMAN.orderStatus(order);
    var tr = document.createElement("tr");

    var refCell = document.createElement("td");
    var ref = document.createElement("strong");
    ref.textContent = order.ref;
    refCell.appendChild(ref);
    if (order.placedAt) {
      var when = document.createElement("div");
      when.className = "admin-when";
      var date = new Date(order.placedAt);
      when.textContent = isNaN(date.getTime()) ? "" : date.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + ", " + date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
      if (when.textContent) refCell.appendChild(when);
    }
    tr.appendChild(refCell);

    var customer = document.createElement("td");
    var customerBox = document.createElement("div");
    customerBox.className = "admin-customer";
    var name = document.createElement("strong");
    name.textContent = contact.name || goods.supplierCountry || contact.supplierCountry || "No name";
    customerBox.appendChild(name);
    var contactLines = [];
    if (contact.phone) contactLines.push(contact.phone);
    else if (goods.supplierPhone || contact.supplierPhone) contactLines.push(goods.supplierPhone || contact.supplierPhone);
    if (contact.email) contactLines.push(contact.email);
    contactLines.forEach(function (value) {
      var line = document.createElement("span");
      line.textContent = value;
      customerBox.appendChild(line);
    });
    customer.appendChild(customerBox);
    tr.appendChild(customer);

    var kind = serviceKind(order);
    var service = goods.service || (order.services[0] && order.services[0].name) || "";
    var serviceCell = document.createElement("td");
    serviceCell.textContent = service;
    if (goods.servicePrice) {
      var price = document.createElement("div");
      price.className = "admin-muted";
      price.textContent = goods.servicePrice;
      serviceCell.appendChild(price);
    }
    if ((kind === "products" && goods.quantity >= 1) || goods.quantity >= 250) {
      var pieces = document.createElement("div");
      pieces.className = "admin-muted";
      pieces.textContent = kind === "products" ? String(goods.quantity) : goods.quantity + " pieces";
      serviceCell.appendChild(pieces);
    } else if (goods.weight) {
      var kilos = document.createElement("div");
      kilos.className = "admin-muted";
      kilos.textContent = goods.weight + " kg";
      serviceCell.appendChild(kilos);
    }
    tr.appendChild(serviceCell);

    var linkCell = document.createElement("td");
    var urls = window.KABAMAN.productUrls(order);
    if (!urls.length) {
      linkCell.textContent = kind === "products" && goods.productName
        ? goods.productName
        : kind === "auction" && goods.description
          ? goods.description
          : "—";
    } else {
      urls.forEach(function (item, index) {
        if (index) linkCell.appendChild(document.createElement("br"));
        var anchor = document.createElement("a");
        anchor.className = "admin-link";
        anchor.href = item.href;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        anchor.textContent = item.href;
        anchor.title = item.href;
        linkCell.appendChild(anchor);
      });
    }
    tr.appendChild(linkCell);

    var statusCell = document.createElement("td");
    var pill = document.createElement("span");
    pill.className = "status-pill " + (tones[status] || "status-new");
    pill.textContent = status;
    var select = document.createElement("select");
    select.className = "status-select";
    select.setAttribute("aria-label", "Status for " + order.ref);
    window.KABAMAN.orderStatuses.forEach(function (label) {
      var option = document.createElement("option");
      option.value = label;
      option.textContent = label;
      if (label === status) option.selected = true;
      select.appendChild(option);
    });
    select.addEventListener("change", function () {
      window.KABAMAN.updateOrder(order.ref, { status: select.value });
      paintOrders();
    });
    statusCell.append(pill, document.createElement("br"), select);
    tr.appendChild(statusCell);

    var actions = document.createElement("td");
    var actionBox = document.createElement("div");
    actionBox.className = "admin-actions-cell";
    var details = document.createElement("button");
    details.type = "button";
    details.className = "btn-quiet";
    details.textContent = openRef === order.ref ? "Hide" : "Details";
    details.addEventListener("click", function () {
      openRef = openRef === order.ref ? "" : order.ref;
      paintOrders();
    });
    actionBox.appendChild(details);
    if (!window.KABAMAN.identityVerified(order)) {
      var verify = document.createElement("button");
      verify.type = "button";
      verify.className = "btn btn-gold";
      verify.textContent = "Verify ID";
      verify.addEventListener("click", function () {
        window.KABAMAN.updateOrder(order.ref, { status: "Verified" });
        paintOrders();
      });
      actionBox.appendChild(verify);
    }
    var remove = document.createElement("button");
    remove.type = "button";
    remove.className = "btn-quiet danger";
    remove.textContent = "Delete";
    remove.addEventListener("click", function () {
      if (!window.confirm("Delete " + order.ref + "?")) return;
      window.KABAMAN.deleteOrder(order.ref);
      if (openRef === order.ref) openRef = "";
      paintOrders();
    });
    actionBox.appendChild(remove);
    actions.appendChild(actionBox);
    tr.appendChild(actions);
    return tr;
  }

  function detailRow(order) {
    var goods = order.goods || {};
    var contact = order.contact || {};
    var tr = document.createElement("tr");
    tr.className = "admin-details";
    var td = document.createElement("td");
    td.colSpan = 6;
    var kind = serviceKind(order);
    var inspection = kind === "inspection";
    var products = kind === "products";
    var auction = kind === "auction";
    var grid = document.createElement("div");
    grid.className = "admin-detail-grid";
    var pairs = [
      ["Name", (products || auction) ? contact.name : ""],
      ["Phone number", contact.phone],
      ["Product name", goods.productName],
      ["Product specification", auction ? "" : (goods.specification || goods.description)],
      ["Description of the goods", auction ? goods.description : ""],
      ["Quantity", products && goods.quantity >= 1 ? String(goods.quantity) : (goods.quantity >= 250 ? goods.quantity + " pieces" : "")],
      ["Bid", auction && Number(goods.bid) > 0 ? moneyLine(goods.bid, " USD") : ""],
      ["Wilaya", goods.wilaya || contact.wilaya],
      ["Country", inspection ? "" : (goods.country || contact.country)],
      ["Address", inspection ? "" : (goods.address || contact.address)],
      ["Supplier country", goods.supplierCountry || (inspection ? (goods.country || contact.country) : "")],
      ["Supplier address", goods.supplierAddress || (inspection ? (goods.address || contact.address) : "")],
      ["Supplier phone", goods.supplierPhone || contact.supplierPhone || (inspection ? contact.phone : "")],
      ["Checklist to inspect", goods.checklist],
      ["Ask for sample", goods.sample],
      ["Shipment information", goods.shipment],
      ["Weight", goods.weight ? goods.weight + " kg" : ""],
      ["Payment method", order.paymentMethod],
      ["Email", contact.email],
    ];
    pairs.forEach(function (pair) {
      var row = field(pair[0], pair[1]);
      if (row) grid.appendChild(row);
    });
    var picture = idView(order);
    if (picture) grid.appendChild(picture);
    td.appendChild(grid);

    var replyLabel = document.createElement("label");
    replyLabel.textContent = "Reply";
    var reply = document.createElement("textarea");
    reply.maxLength = 500;
    reply.rows = 3;
    reply.value = order.reply || "";
    var saveReply = document.createElement("button");
    saveReply.type = "button";
    saveReply.className = "btn btn-gold";
    saveReply.textContent = "Save reply";
    saveReply.addEventListener("click", function () {
      window.KABAMAN.updateOrder(order.ref, { reply: reply.value.trim() });
      openRef = order.ref;
      paintOrders();
    });
    td.append(replyLabel, reply, saveReply);
    tr.appendChild(td);
    return tr;
  }

  window.KABAMAN_SITE.whenReady(function (site) {
    fillForm(site);
    paintOrders();
  });

  importRate.addEventListener("input", function () {
    if (importRate.value) paintLinkedPrices("importation", moneyLine(importRate.value, " USD / kg"));
  });
  inspectionUsd.addEventListener("input", function () {
    if (inspectionUsd.value) paintLinkedPrices("inspection", moneyLine(inspectionUsd.value, " USD"));
  });

  if (logoInput) {
    logoInput.addEventListener("change", function () {
      var file = logoInput.files && logoInput.files[0];
      if (!file) return;
      compressLogo(file).then(function (dataUrl) {
        if (!dataUrl) {
          siteNote.textContent = "That image could not be read. Try a different file.";
          return;
        }
        logoValue = dataUrl;
        showLogo();
        siteNote.textContent = "Logo ready. Save to use it on the customer page.";
      });
    });
  }

  document.getElementById("logo-clear").addEventListener("click", function () {
    logoValue = "";
    if (logoInput) logoInput.value = "";
    showLogo();
  });

  document.getElementById("add-service").addEventListener("click", function () {
    readDraft();
    var formType = knownForm(document.getElementById("new-service-form").value);
    draft.push(preset(formType));
    renderEditors();
    siteNote.textContent = "Button added. Save to show it on the customer page.";
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    readDraft();
    if (draft.length < 1) {
      siteNote.textContent = "Keep at least one button.";
      return;
    }
    var saved = window.KABAMAN_SITE.save({
      slogan: sloganInput.value.trim(),
      welcome: welcomeInput.value.trim(),
      line: lineInput.value.trim(),
      prices: {
        importPerKg: Number(importRate.value),
        importMaxKg: Number(importMax.value),
        inspectionUsd: Number(inspectionUsd.value),
      },
      theme: {
        background: backgroundInput.value,
        text: textInput.value,
        accent: accentInput.value,
        buttonBackground: buttonBgInput.value,
        buttonText: buttonTextInput.value,
        buttonCorners: cornersInput.value === "rounded" ? "rounded" : "square",
        shimmer: shimmerInput.checked,
        logo: logoValue,
      },
      services: draft.map(function (item) {
        return {
          name: item.name,
          note: item.note,
          line: item.line,
          price: item.price,
          action: item.action,
          form: item.form,
        };
      }),
    });
    if (!saved) {
      siteNote.textContent = "This browser blocked saving. Try a smaller logo.";
      return;
    }
    var wantedLogo = logoValue;
    fillForm(saved);
    if (wantedLogo && !(saved.theme && saved.theme.logo)) {
      siteNote.textContent = "Saved, but the logo was too large to store. Other changes were kept.";
      return;
    }
    siteNote.textContent = "Saved on this browser. Reload the customer page to see it.";
  });

  document.getElementById("site-reset").addEventListener("click", function () {
    window.KABAMAN_SITE.reset();
    fillForm(window.KABAMAN_SITE.get());
    siteNote.textContent = "Restored the site.json defaults on this browser.";
  });
})();
