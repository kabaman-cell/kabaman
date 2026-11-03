(function () {
  var CART_KEY = "kabaman.cart";
  var ORDERS_KEY = "kabaman.orders";

  var SERVICES = [
    {
      id: "full-importation",
      name: "Full Importation",
      summary: "Source · Import · Deliver",
    },
    {
      id: "sourcing",
      name: "Sourcing",
      summary: "Trusted suppliers matched to your brief",
    },
    {
      id: "quality-check",
      name: "Quality Check",
      summary: "Inspection before anything ships",
    },
    {
      id: "custom-packaging",
      name: "Custom Packaging",
      summary: "Brand-ready packing for retail or gifting",
    },
    {
      id: "door-to-door",
      name: "Door to Door Delivery",
      summary: "From our supplier to your door",
    },
  ];

  var DETAIL_LIMITS = {
    goods: 500,
    goodsQty: 80,
    destination: 160,
    notes: 500,
  };

  function findService(id) {
    for (var i = 0; i < SERVICES.length; i += 1) {
      if (SERVICES[i].id === id) return SERVICES[i];
    }
    return null;
  }

  function emptyDetails() {
    return { goods: "", goodsQty: "", destination: "", notes: "", links: [] };
  }

  function labelFromListingPath(url) {
    var parts = url.pathname.split("/").filter(Boolean);
    var slug = parts.length ? parts[parts.length - 1] : "";
    slug = slug.replace(/\.html?$/i, "");
    try {
      slug = decodeURIComponent(slug);
    } catch (err) {
      /* keep the raw slug */
    }
    var label = slug.replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
    label = label.replace(/\s+\d{6,}$/g, "").trim();
    if (!label || /^offer$/i.test(label) || /^\d+$/.test(label)) label = "Product link";
    label = label.replace(/\b([a-z])/g, function (letter) {
      return letter.toUpperCase();
    });
    return label.slice(0, 120);
  }

  function parseListingUrl(value) {
    if (typeof value !== "string") return null;
    var parsed;
    try {
      parsed = new URL(value.trim());
    } catch (err) {
      return null;
    }
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    if (!parsed.hostname) return null;
    return { url: parsed.href, label: labelFromListingPath(parsed) };
  }

  function normalizeLinks(list) {
    if (!Array.isArray(list)) return [];
    var out = [];
    var seen = {};
    list.slice(0, 8).forEach(function (item) {
      if (!item) return;
      var parsed = parseListingUrl(item.url);
      if (!parsed || seen[parsed.url]) return;
      seen[parsed.url] = true;
      var goodsQty = Number.parseInt(item.qty, 10);
      var qty = Number.isFinite(goodsQty) && goodsQty >= 1 ? Math.min(9999, goodsQty) : 1;
      var label = typeof item.label === "string" && item.label.trim() ? item.label.trim().slice(0, 120) : parsed.label;
      out.push({
        url: parsed.url,
        label: label,
        qty: qty,
        note: typeof item.note === "string" ? item.note.slice(0, 200) : "",
      });
    });
    return out;
  }

  function emptyCart() {
    return { items: [], details: emptyDetails() };
  }

  function readJson(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      if (!raw) return fallback;
      return JSON.parse(raw);
    } catch (err) {
      return fallback;
    }
  }

  function writeJson(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (err) {
      return false;
    }
  }

  function clampQty(value) {
    var n = Number.parseInt(value, 10);
    if (!Number.isFinite(n) || n < 1) return 0;
    return Math.min(99, n);
  }

  function normalizeCart(data) {
    var source = data && typeof data === "object" ? data : {};
    var details = emptyDetails();
    var incoming = source.details && typeof source.details === "object" ? source.details : {};
    Object.keys(DETAIL_LIMITS).forEach(function (key) {
      var value = incoming[key];
      if (typeof value === "string") details[key] = value.slice(0, DETAIL_LIMITS[key]);
    });
    details.links = normalizeLinks(incoming.links);

    var items = [];
    var seen = {};
    var list = Array.isArray(source.items) ? source.items : [];
    list.forEach(function (item) {
      if (!item || seen[item.id]) return;
      var service = findService(item.id);
      var qty = clampQty(item.qty);
      if (!service || !qty) return;
      seen[item.id] = true;
      items.push({ id: service.id, qty: qty });
    });

    return { items: items, details: details };
  }

  function readCart() {
    return normalizeCart(readJson(CART_KEY, null));
  }

  function cartUnits(cart) {
    return (cart.items || []).reduce(function (sum, item) {
      return sum + item.qty;
    }, 0);
  }

  function shipmentLabel(qty) {
    return qty === 1 ? "1 shipment" : String(qty) + " shipments";
  }

  function paintCartCount() {
    var units = cartUnits(readCart());
    document.querySelectorAll("[data-cart-count]").forEach(function (el) {
      el.textContent = String(units);
    });
    var label = "Your order, " + shipmentLabel(units);
    document.querySelectorAll(".cart-link").forEach(function (el) {
      el.setAttribute("aria-label", label);
    });
  }

  function writeCart(cart) {
    var ok = writeJson(CART_KEY, normalizeCart(cart));
    paintCartCount();
    return ok;
  }

  function clearCart() {
    return writeCart(emptyCart());
  }

  function readOrders() {
    var data = readJson(ORDERS_KEY, []);
    if (!Array.isArray(data)) return [];
    return data.filter(function (order) {
      return order && typeof order.ref === "string" && Array.isArray(order.services);
    });
  }

  function nextRef(orders) {
    var used = {};
    (orders || readOrders()).forEach(function (order) {
      used[order.ref] = true;
    });
    var ref = "";
    var guard = 0;
    do {
      ref = "KBM-" + String(Math.floor(1000 + Math.random() * 9000));
      guard += 1;
    } while (used[ref] && guard < 40);
    if (used[ref]) ref = "KBM-" + String(Date.now()).slice(-4);
    return ref;
  }

  function saveOrder(order) {
    var orders = readOrders();
    var copy = {
      ref: order.ref || nextRef(orders),
      placedAt: order.placedAt,
      status: order.status || "",
      reviewWindow: order.reviewWindow || "",
      services: order.services,
      goods: order.goods,
      contact: order.contact,
      paymentMethod: order.paymentMethod || "",
    };
    orders.push(copy);
    return writeJson(ORDERS_KEY, orders.slice(-30)) ? copy : null;
  }

  function updateOrder(ref, patch) {
    var orders = readOrders();
    var found = null;
    orders.forEach(function (order, index) {
      if (order.ref !== ref) return;
      var next = {};
      Object.keys(order).forEach(function (key) { next[key] = order[key]; });
      Object.keys(patch || {}).forEach(function (key) { next[key] = patch[key]; });
      if (patch && patch.goods && order.goods) {
        next.goods = Object.assign({}, order.goods, patch.goods);
      }
      orders[index] = next;
      found = next;
    });
    if (!found) return null;
    return writeJson(ORDERS_KEY, orders) ? found : null;
  }

  window.KABAMAN = {
    findService: findService,
    parseListingUrl: parseListingUrl,
    readCart: readCart,
    writeCart: writeCart,
    clearCart: clearCart,
    readOrders: readOrders,
    saveOrder: saveOrder,
    updateOrder: updateOrder,
    nextRef: nextRef,
    cartUnits: cartUnits,
    shipmentLabel: shipmentLabel,
    paintCartCount: paintCartCount,
  };
})();
