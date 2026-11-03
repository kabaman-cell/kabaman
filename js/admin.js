(function () {
  if (!window.KABAMAN || !window.KABAMAN_SITE) return;

  var form = document.getElementById("site-form");
  var sloganInput = document.getElementById("edit-slogan");
  var welcomeInput = document.getElementById("edit-welcome");
  var nameInputs = [
    document.getElementById("edit-service-0"),
    document.getElementById("edit-service-1"),
    document.getElementById("edit-service-2"),
  ];
  var siteNote = document.getElementById("site-note");
  var list = document.getElementById("order-list");

  function fillForm(site) {
    sloganInput.value = site.slogan;
    welcomeInput.value = site.welcome;
    site.services.forEach(function (item, index) {
      if (nameInputs[index]) nameInputs[index].value = item.name;
    });
  }

  function orders() {
    return window.KABAMAN.readOrders();
  }

  function field(label, value) {
    var wrap = document.createElement("p");
    var strong = document.createElement("strong");
    strong.textContent = label + ": ";
    wrap.append(strong, document.createTextNode(value || "—"));
    return wrap;
  }

  function paintOrders() {
    list.replaceChildren();
    var rows = orders();
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
      var action = goods.action || (order.services[0] && order.services[0].action) || "";
      [
        ["Service", action && action !== service ? service + " — " + action : service],
        ["Name", contact.name],
        ["Ask for sample", goods.sample || ""],
        ["Wilaya", goods.wilaya || contact.wilaya],
        ["Phone", contact.phone],
        ["Email", contact.email],
        ["Description", goods.description],
        ["Product link", goods.links && goods.links[0] ? goods.links[0].url : ""],
        ["ID file", contact.idFileName],
        ["Status", order.status],
        ["MOQ", goods.moq ? String(goods.moq) : ""],
        ["Target unit price", goods.targetPrice || ""],
        ["Currency", goods.currency || ""],
        ["Country", goods.country || contact.country || ""],
        ["Shipment information", goods.shipment || ""],
        ["Weight", goods.weight ? goods.weight + " kg" : ""],
        ["Service price", goods.servicePrice || ""],
        ["Payment method", order.paymentMethod || ""],
      ].forEach(function (pair) {
        card.appendChild(field(pair[0], pair[1]));
      });

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
      card.append(replyLabel, reply, saveReply);
      list.appendChild(card);
    });
  }

  window.KABAMAN_SITE.whenReady(function (site) {
    fillForm(site);
    paintOrders();
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var site = window.KABAMAN_SITE.get();
    window.KABAMAN_SITE.save({
      slogan: sloganInput.value.trim(),
      welcome: welcomeInput.value.trim(),
      services: site.services.map(function (item, index) {
        return { name: nameInputs[index].value.trim() || item.name };
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
