(function () {
  "use strict";

  var KEY = "kabaman.whatsapp.manual-orders.v1";
  var STATUSES = ["Nouveau", "Confirmée", "En préparation", "Expédiée", "Livrée", "Annulée"];
  var form = document.getElementById("manual-order-form");
  var list = document.getElementById("orders-list");
  var empty = document.getElementById("empty-orders");
  var errorNote = document.getElementById("storage-error");
  var formNote = document.getElementById("form-note");
  var search = document.getElementById("order-search");
  var filter = document.getElementById("order-filter");

  function readOrders() {
    try {
      var value = JSON.parse(window.localStorage.getItem(KEY) || "[]");
      return Array.isArray(value) ? value.filter(function (item) {
        return item && typeof item.id === "string" && typeof item.ref === "string";
      }) : [];
    } catch (error) {
      errorNote.hidden = false;
      return [];
    }
  }

  function writeOrders(orders) {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(orders));
      errorNote.hidden = true;
      return true;
    } catch (error) {
      errorNote.hidden = false;
      return false;
    }
  }

  function makeId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
    return String(Date.now()) + "-" + String(Math.random()).slice(2);
  }

  function makeRef() {
    var date = new Date();
    var stamp = date.getFullYear() + String(date.getMonth() + 1).padStart(2, "0") + String(date.getDate()).padStart(2, "0");
    return "KBW-" + stamp + "-" + String(Math.floor(1000 + Math.random() * 9000));
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function formatDate(value) {
    var date = new Date(value);
    if (isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" }).format(date);
  }

  function formatTotal(value) {
    if (value === "" || value === null || value === undefined || !isFinite(Number(value))) return "À définir";
    return new Intl.NumberFormat("fr-DZ", { maximumFractionDigits: 2 }).format(Number(value)) + " DZD";
  }

  function detail(label, value) {
    var box = el("div", "wa-order-detail");
    box.append(el("span", "", label), el("strong", "", value || "—"));
    return box;
  }

  function phoneDigits(value) {
    var digits = String(value || "").replace(/\D/g, "");
    if (digits.indexOf("00") === 0) digits = digits.slice(2);
    return digits;
  }

  function whatsappUrl(order) {
    var digits = phoneDigits(order.phone);
    if (digits.length < 8) return "";
    var message = "Bonjour " + order.customerName + ", je vous contacte au sujet de votre commande " + order.ref + " concernant " + order.item + ".";
    return "https://wa.me/" + digits + "?text=" + encodeURIComponent(message);
  }

  function renderCard(order) {
    var card = el("article", "wa-order-card");
    var top = el("div", "wa-order-top");
    var identity = el("div", "");
    identity.append(
      el("h3", "wa-order-title", order.customerName || "Client"),
      el("p", "wa-order-meta", order.ref + " · " + formatDate(order.createdAt))
    );
    top.append(identity, el("span", "wa-source-badge", "WhatsApp"));
    card.appendChild(top);

    var details = el("div", "wa-order-details");
    details.append(
      detail("Téléphone", order.phone),
      detail("Produit / service", order.item),
      detail("Quantité", order.quantity),
      detail("Total convenu", formatTotal(order.total)),
      detail("Wilaya / ville", order.location),
      detail("État", order.status)
    );
    card.appendChild(details);

    if (order.note) card.appendChild(el("p", "wa-order-note", order.note));

    var actions = el("div", "wa-order-actions");
    var select = el("select", "");
    select.setAttribute("aria-label", "État de la commande " + order.ref);
    STATUSES.forEach(function (status) {
      var option = el("option", "", status);
      option.value = status;
      option.selected = status === order.status;
      select.appendChild(option);
    });
    select.addEventListener("change", function () {
      var orders = readOrders();
      var target = orders.find(function (item) { return item.id === order.id; });
      if (!target) return;
      target.status = select.value;
      if (writeOrders(orders)) render();
    });
    actions.appendChild(select);

    var wa = whatsappUrl(order);
    if (wa) {
      var openChat = el("a", "", "Ouvrir la conversation WhatsApp");
      openChat.href = wa;
      openChat.target = "_blank";
      openChat.rel = "noopener noreferrer";
      actions.appendChild(openChat);
    }

    var remove = el("button", "btn btn-quiet wa-delete", "Supprimer");
    remove.type = "button";
    remove.addEventListener("click", function () {
      if (!window.confirm("Supprimer la commande " + order.ref + " de ce navigateur ?")) return;
      var remaining = readOrders().filter(function (item) { return item.id !== order.id; });
      if (writeOrders(remaining)) render();
    });
    actions.appendChild(remove);
    card.appendChild(actions);
    return card;
  }

  function renderMetrics(orders) {
    var active = orders.filter(function (order) { return order.status !== "Livrée" && order.status !== "Annulée"; });
    var progress = orders.filter(function (order) {
      return ["Confirmée", "En préparation", "Expédiée"].indexOf(order.status) !== -1;
    });
    document.getElementById("metric-total").textContent = String(orders.length);
    document.getElementById("metric-new").textContent = String(orders.filter(function (order) { return order.status === "Nouveau"; }).length);
    document.getElementById("metric-progress").textContent = String(progress.length);
    document.getElementById("metric-done").textContent = String(orders.filter(function (order) { return order.status === "Livrée"; }).length);
    document.getElementById("metric-total").setAttribute("aria-label", String(active.length) + " commandes actives sur " + String(orders.length));
  }

  function render() {
    var orders = readOrders().slice().sort(function (a, b) {
      return new Date(b.createdAt || 0).getTime() - new Date(a.createdAt || 0).getTime();
    });
    renderMetrics(orders);
    var query = search.value.trim().toLocaleLowerCase("fr");
    var status = filter.value;
    var visible = orders.filter(function (order) {
      var text = [order.ref, order.customerName, order.phone, order.location, order.item, order.note].join(" ").toLocaleLowerCase("fr");
      return (!query || text.indexOf(query) !== -1) && (!status || order.status === status);
    });
    list.replaceChildren();
    visible.forEach(function (order) { list.appendChild(renderCard(order)); });
    empty.hidden = visible.length > 0;
    if (orders.length && !visible.length) empty.textContent = "Aucune commande ne correspond à cette recherche.";
    else empty.textContent = "Aucune commande pour le moment. Ajoute la première commande reçue sur WhatsApp.";
  }

  function exportCsv() {
    var orders = readOrders();
    if (!orders.length) {
      formNote.textContent = "Aucune commande à exporter.";
      return;
    }
    var columns = ["Référence", "Date", "Client", "Téléphone WhatsApp", "Wilaya / ville", "Produit / service", "Quantité", "Total DZD", "État", "Résumé du message"];
    var rows = orders.map(function (order) {
      return [order.ref, formatDate(order.createdAt), order.customerName, order.phone, order.location, order.item, order.quantity, order.total, order.status, order.note];
    });
    function quote(value) {
      return '"' + String(value === undefined || value === null ? "" : value).replace(/"/g, '""') + '"';
    }
    var csv = "\uFEFF" + [columns].concat(rows).map(function (row) { return row.map(quote).join(";"); }).join("\r\n");
    var blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var anchor = el("a", "");
    anchor.href = url;
    anchor.download = "kabaman-commandes-whatsapp-" + new Date().toISOString().slice(0, 10) + ".csv";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    formNote.textContent = "Sauvegarde CSV téléchargée.";
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var data = new FormData(form);
    var phone = String(data.get("phone") || "").trim();
    if (phoneDigits(phone).length < 8) {
      formNote.textContent = "Vérifie le numéro WhatsApp et ajoute son indicatif pays.";
      form.elements.phone.focus();
      return;
    }
    var totalValue = String(data.get("total") || "").trim();
    var order = {
      id: makeId(),
      ref: makeRef(),
      createdAt: new Date().toISOString(),
      source: "WhatsApp Business",
      customerName: String(data.get("customerName") || "").trim(),
      phone: phone,
      location: String(data.get("location") || "").trim(),
      item: String(data.get("item") || "").trim(),
      quantity: String(data.get("quantity") || "").trim(),
      total: totalValue === "" ? "" : Number(totalValue),
      note: String(data.get("note") || "").trim(),
      status: "Nouveau"
    };
    var orders = readOrders();
    orders.push(order);
    if (!writeOrders(orders)) {
      formNote.textContent = "Échec de l’enregistrement. Libère de l’espace ou exporte tes données.";
      return;
    }
    form.reset();
    formNote.textContent = "Commande " + order.ref + " enregistrée dans ce navigateur.";
    render();
  });

  search.addEventListener("input", render);
  filter.addEventListener("change", render);
  document.getElementById("export-orders").addEventListener("click", exportCsv);
  render();
})();
