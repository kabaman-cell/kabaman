(function () {
  if (!window.KABAMAN || !window.KABAMAN_SITE) return;

  var form = document.getElementById("site-form");
  var sloganInput = document.getElementById("edit-slogan");
  var welcomeInput = document.getElementById("edit-welcome");
  var lineInput = document.getElementById("edit-line");
  var nameInputs = [
    document.getElementById("edit-service-0"),
    document.getElementById("edit-service-1"),
    document.getElementById("edit-service-2"),
  ];
  var lineInputs = [
    document.getElementById("edit-line-0"),
    document.getElementById("edit-line-1"),
    document.getElementById("edit-line-2"),
  ];
  var priceInputs = [
    document.getElementById("edit-price-0"),
    document.getElementById("edit-price-1"),
    document.getElementById("edit-price-2"),
  ];
  var importRate = document.getElementById("edit-import-rate");
  var importMax = document.getElementById("edit-import-max");
  var inspectionUsd = document.getElementById("edit-inspection-usd");
  var siteNote = document.getElementById("site-note");
  var list = document.getElementById("order-list");

  function fillForm(site) {
    var prices = site.prices || {};
    sloganInput.value = site.slogan;
    welcomeInput.value = site.welcome;
    lineInput.value = site.line || "";
    importRate.value = prices.importPerKg || 25;
    importMax.value = prices.importMaxKg || 100;
    inspectionUsd.value = prices.inspectionUsd || 100;
    site.services.forEach(function (item, index) {
      if (nameInputs[index]) nameInputs[index].value = item.name;
      if (lineInputs[index]) lineInputs[index].value = item.line || "";
      if (priceInputs[index]) priceInputs[index].value = item.price || "";
    });
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
    list.replaceChildren();
    var rows = window.KABAMAN.readOrders();
    if (!rows.length) {
      var empty = document.createElement("p");
      empty.textContent = "No orders yet.";
      list.appendChild(empty);
      return;
    }
    rows.slice().reverse().forEach(function (order) {
      var card = document.createElement("article");
      card.className = "admin-order";
      var title = document.createElement("h3");
      title.textContent = order.ref;
      card.appendChild(title);
      var goods = order.goods || {};
      var contact = order.contact || {};
      var service = goods.service || (order.services[0] && order.services[0].name) || "";
      var link = goods.links && goods.links[0] ? goods.links[0].url : "";
      [
        ["Service", service],
        ["Name", contact.name],
        ["Ask for sample", goods.sample],
        ["Description", goods.description],
        ["Product link", link],
        ["Wilaya", goods.wilaya || contact.wilaya],
        ["Phone", contact.phone],
        ["Email", contact.email],
        ["Country", goods.country || contact.country],
        ["Address", goods.address || contact.address],
        ["Shipment information", goods.shipment],
        ["Weight", goods.weight ? goods.weight + " kg" : ""],
        ["Service price", goods.servicePrice],
        ["Payment method", order.paymentMethod],
        ["Status", order.status],
      ].forEach(function (pair) {
        var row = field(pair[0], pair[1]);
        if (row) card.appendChild(row);
      });

      var picture = idView(order);
      if (picture) card.appendChild(picture);

      var confirm = document.createElement("button");
      confirm.type = "button";
      confirm.className = "btn btn-gold";
      if (order.status === "ID confirmed") {
        confirm.textContent = "ID confirmed";
        confirm.disabled = true;
      } else {
        confirm.textContent = "Confirm ID";
        confirm.addEventListener("click", function () {
          window.KABAMAN.updateOrder(order.ref, { status: "ID confirmed" });
          paintOrders();
        });
      }
      card.appendChild(confirm);

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
        paintOrders();
      });
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn btn-gold";
      remove.textContent = "Delete order";
      remove.addEventListener("click", function () {
        window.KABAMAN.deleteOrder(order.ref);
        paintOrders();
      });
      card.append(replyLabel, reply, saveReply, remove);
      list.appendChild(card);
    });
  }

  window.KABAMAN_SITE.whenReady(function (site) {
    fillForm(site);
    paintOrders();
  });

  importRate.addEventListener("input", function () {
    if (importRate.value) priceInputs[0].value = importRate.value + " USD / kg";
  });
  inspectionUsd.addEventListener("input", function () {
    if (inspectionUsd.value) priceInputs[2].value = inspectionUsd.value + " USD";
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var site = window.KABAMAN_SITE.get();
    window.KABAMAN_SITE.save({
      slogan: sloganInput.value.trim(),
      welcome: welcomeInput.value.trim(),
      line: lineInput.value.trim(),
      prices: {
        importPerKg: Number(importRate.value),
        importMaxKg: Number(importMax.value),
        inspectionUsd: Number(inspectionUsd.value),
      },
      services: site.services.map(function (item, index) {
        return {
          name: nameInputs[index].value.trim() || item.name,
          note: item.note,
          line: lineInputs[index].value.trim(),
          price: priceInputs[index].value.trim(),
          action: item.action,
        };
      }),
    });
    siteNote.textContent = "Saved on this browser. Reload the customer page to see it.";
  });

  document.getElementById("site-reset").addEventListener("click", function () {
    window.KABAMAN_SITE.reset();
    fillForm(window.KABAMAN_SITE.get());
    siteNote.textContent = "Restored the site.json defaults on this browser.";
  });
})();
