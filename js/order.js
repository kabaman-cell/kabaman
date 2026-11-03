(function () {
  const PAGE_TITLE = document.title;
  const flashTimers = new WeakMap();

  const orderFlow = document.getElementById("order-flow");
  const catalog = document.getElementById("catalog");
  const yourOrder = document.getElementById("your-order");
  const checkout = document.getElementById("checkout");
  const confirmation = document.getElementById("confirmation");
  const cartLines = document.getElementById("cart-lines");
  const cartEmpty = document.getElementById("cart-empty");
  const detailsForm = document.getElementById("details-form");
  const checkoutForm = document.getElementById("checkout-form");
  const announce = document.getElementById("cart-announce");

  function scrollToId(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  }

  function closeMenu() {
    document.querySelector(".nav")?.classList.remove("open");
    document.querySelector(".nav-toggle")?.setAttribute("aria-expanded", "false");
  }

  function say(message) {
    if (!announce) return;
    announce.textContent = "";
    window.setTimeout(() => {
      announce.textContent = message;
    }, 30);
  }

  function setStatus(id, message, isError) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = message;
    el.classList.toggle("is-error", Boolean(isError));
  }

  function setStep(n) {
    document.querySelectorAll(".order-steps li").forEach((li) => {
      const step = Number(li.dataset.step);
      li.classList.toggle("is-current", step === n);
      li.classList.toggle("is-done", step < n);
      if (step === n) li.setAttribute("aria-current", "step");
      else li.removeAttribute("aria-current");
    });
  }

  function syncDock() {
    const dock = document.getElementById("order-dock");
    if (!dock) return;
    const units = window.KABAMAN.cartUnits(window.KABAMAN.readCart());
    const shopping = document.body.dataset.view === "shop";
    const show = shopping && units > 0;
    dock.hidden = !show;
    const count = dock.querySelector("[data-dock-count]");
    if (count) count.textContent = window.KABAMAN.shipmentLabel(units) + " in your order";
    const narrow = window.matchMedia("(max-width: 720px)").matches;
    document.body.classList.toggle("has-dock", show && narrow);
  }

  function fillDetails() {
    const details = window.KABAMAN.readCart().details;
    document.querySelectorAll("[data-detail]").forEach((input) => {
      input.value = details[input.dataset.detail] || "";
    });
  }

  function readDetailInputs() {
    const details = {};
    document.querySelectorAll("[data-detail]").forEach((input) => {
      details[input.dataset.detail] = input.value;
    });
    return details;
  }

  function saveDetailsFromInputs() {
    const cart = window.KABAMAN.readCart();
    const links = Array.isArray(cart.details.links) ? cart.details.links : [];
    cart.details = Object.assign({}, cart.details, readDetailInputs(), { links: links });
    return window.KABAMAN.writeCart(cart);
  }

  function renderCart() {
    const cart = window.KABAMAN.readCart();
    cartLines.replaceChildren();
    cartEmpty.hidden = cart.items.length > 0;

    cart.items.forEach((item) => {
      const service = window.KABAMAN.findService(item.id);
      if (!service) return;

      const row = document.createElement("article");
      row.className = "cart-line";
      row.dataset.id = service.id;

      const info = document.createElement("div");
      info.className = "line-info";
      const title = document.createElement("h3");
      title.textContent = service.name;
      const summary = document.createElement("p");
      summary.textContent = service.summary + " · Service";
      info.append(title, summary);

      const qtyWrap = document.createElement("div");
      qtyWrap.className = "qty-wrap";
      const qtyLabel = document.createElement("span");
      qtyLabel.className = "qty-label";
      qtyLabel.textContent = "Shipments";
      const qty = document.createElement("div");
      qty.className = "qty";

      const dec = document.createElement("button");
      dec.type = "button";
      dec.dataset.dec = "true";
      dec.textContent = "−";
      dec.setAttribute("aria-label", "Fewer shipments for " + service.name);

      const input = document.createElement("input");
      input.type = "number";
      input.min = "1";
      input.max = "99";
      input.inputMode = "numeric";
      input.value = String(item.qty);
      input.dataset.qtyInput = "true";
      input.setAttribute("aria-label", "Number of shipments for " + service.name);

      const inc = document.createElement("button");
      inc.type = "button";
      inc.dataset.inc = "true";
      inc.textContent = "+";
      inc.setAttribute("aria-label", "More shipments for " + service.name);

      qty.append(dec, input, inc);
      qtyWrap.append(qtyLabel, qty);

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "linkish";
      remove.dataset.remove = "true";
      remove.textContent = "Remove";
      remove.setAttribute("aria-label", "Remove " + service.name);

      row.append(info, qtyWrap, remove);
      cartLines.append(row);
    });

    if (document.body.dataset.view === "shop") {
      setStep(cart.items.length ? 2 : 1);
    }
    renderSourceLinks();
    syncDock();
  }

  function linkList(links) {
    const list = document.createElement("ul");
    list.className = "link-lines";
    links.forEach((link) => {
      const li = document.createElement("li");
      const title = document.createElement("strong");
      title.textContent = link.label;
      const anchor = document.createElement("a");
      anchor.href = link.url;
      anchor.textContent = link.url;
      anchor.rel = "noreferrer noopener";
      anchor.target = "_blank";
      const meta = document.createElement("span");
      meta.textContent = "Quantity " + link.qty + (link.note ? " · " + link.note : "");
      li.append(title, anchor, meta);
      list.append(li);
    });
    return list;
  }

  function renderSourceLinks() {
    const holder = document.getElementById("source-links");
    if (!holder) return;
    const links = window.KABAMAN.readCart().details.links || [];
    holder.replaceChildren();
    if (!links.length) {
      holder.hidden = true;
      return;
    }
    holder.hidden = false;
    const title = document.createElement("h3");
    title.textContent = "Listings to source";
    holder.append(title, linkList(links));
  }

  function commitQty(id, qty) {
    const cart = window.KABAMAN.readCart();
    const item = cart.items.find((entry) => entry.id === id);
    if (!item || item.qty === qty) return;
    item.qty = qty;
    window.KABAMAN.writeCart(cart);
    syncDock();
  }

  function removeItem(id) {
    const service = window.KABAMAN.findService(id);
    const cart = window.KABAMAN.readCart();
    cart.items = cart.items.filter((item) => item.id !== id);
    window.KABAMAN.writeCart(cart);
    renderCart();
    say((service ? service.name : "Service") + " removed from your order.");
  }

  function addService(id, button) {
    const service = window.KABAMAN.findService(id);
    if (!service) return;
    const cart = window.KABAMAN.readCart();
    const wasEmpty = cart.items.length === 0;
    const existing = cart.items.find((item) => item.id === id);
    if (existing && existing.qty >= 99) {
      say(service.name + " already covers 99 shipments on this order.");
      return;
    }
    if (existing) existing.qty += 1;
    else cart.items.push({ id: id, qty: 1 });
    if (!window.KABAMAN.writeCart(cart)) {
      say("This browser blocked saving the order. Allow site data for this page and try again.");
      return;
    }
    renderCart();
    flash(button);
    const units = window.KABAMAN.cartUnits(window.KABAMAN.readCart());
    say(service.name + " added. " + window.KABAMAN.shipmentLabel(units) + " in your order.");
    if (wasEmpty) scrollToId("your-order");
  }

  function flash(button) {
    if (!button) return;
    const label = button.querySelector(".btn-label");
    if (!label) return;
    label.textContent = "Added";
    button.classList.add("is-added");
    const prior = flashTimers.get(button);
    if (prior) window.clearTimeout(prior);
    flashTimers.set(
      button,
      window.setTimeout(() => {
        label.textContent = button.dataset.label || "Add to order";
        button.classList.remove("is-added");
      }, 1000)
    );
  }

  function addFact(list, term, value) {
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = value;
    list.append(dt, dd);
  }

  function buildSummary(model, includeContact) {
    const wrap = document.createElement("div");
    const list = document.createElement("ul");
    list.className = "summary";
    model.services.forEach((item) => {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.textContent = item.name;
      const qty = document.createElement("span");
      qty.textContent = window.KABAMAN.shipmentLabel(item.qty);
      li.append(name, qty);
      list.append(li);
    });
    wrap.append(list);

    const quote = document.createElement("p");
    quote.className = "price-line";
    quote.append("Custom quote");
    const note = document.createElement("span");
    note.textContent = "Price confirmed after review. Nothing is charged on this page.";
    quote.append(note);
    wrap.append(quote);

    const facts = document.createElement("dl");
    facts.className = "facts";
    addFact(facts, "Goods to import", model.goods.goods);
    addFact(facts, "Approximate quantity", model.goods.goodsQty);
    addFact(facts, "Destination", model.goods.destination);
    addFact(facts, "Notes", model.goods.notes ? model.goods.notes : "None added");
    if (includeContact && model.contact) {
      addFact(facts, "Name", model.contact.name);
      addFact(facts, "Email", model.contact.email);
      if (model.contact.phone) addFact(facts, "Phone or WhatsApp", model.contact.phone);
    }
    if (model.placedAt) addFact(facts, "Requested", formatWhen(model.placedAt));
    wrap.append(facts);
    if (Array.isArray(model.goods.links) && model.goods.links.length) {
      const sourced = document.createElement("div");
      sourced.className = "sourced-links";
      const heading = document.createElement("h3");
      heading.textContent = "Alibaba links on this service order";
      sourced.append(heading, linkList(model.goods.links));
      wrap.append(sourced);
    }
    return wrap;
  }

  function formatWhen(iso) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }

  function showShop() {
    document.body.dataset.view = "shop";
    document.title = PAGE_TITLE;
    orderFlow.hidden = false;
    catalog.hidden = false;
    yourOrder.hidden = false;
    checkout.hidden = true;
    confirmation.hidden = true;
    setStep(window.KABAMAN.readCart().items.length ? 2 : 1);
    syncDock();
  }

  function validateDetails() {
    saveDetailsFromInputs();
    const cart = window.KABAMAN.readCart();
    const goods = document.getElementById("goods");
    const goodsQty = document.getElementById("goods-qty");
    const destination = document.getElementById("destination");
    [goods, goodsQty, destination, document.getElementById("notes")].forEach((input) => {
      input.value = input.value.trim();
    });
    saveDetailsFromInputs();

    if (window.KABAMAN.cartUnits(cart) < 1) {
      setStatus("details-status", "Choose a service before checkout.", true);
      scrollToId("catalog");
      return false;
    }

    const missingGoods = !goods.value;
    const missingQty = !goodsQty.value;
    const missingDestination = !destination.value;
    goods.setAttribute("aria-invalid", String(missingGoods));
    goodsQty.setAttribute("aria-invalid", String(missingQty));
    destination.setAttribute("aria-invalid", String(missingDestination));

    if (missingGoods || missingQty || missingDestination) {
      setStatus(
        "details-status",
        "Add what you want imported, an approximate quantity of goods, and the destination country and city.",
        true
      );
      (missingGoods ? goods : missingQty ? goodsQty : destination).focus();
      return false;
    }

    setStatus("details-status", "", false);
    return true;
  }

  function showCheckout() {
    if (!validateDetails()) return;
    const summary = document.getElementById("checkout-summary");
    summary.replaceChildren(buildSummary(summaryModelFromCart(), false));
    document.body.dataset.view = "checkout";
    catalog.hidden = true;
    yourOrder.hidden = true;
    checkout.hidden = false;
    confirmation.hidden = true;
    orderFlow.hidden = false;
    setStep(3);
    syncDock();
    scrollToId("checkout");
    document.getElementById("customer-name").focus();
  }

  function summaryModelFromCart() {
    const cart = window.KABAMAN.readCart();
    return {
      services: cart.items.map((item) => {
        const service = window.KABAMAN.findService(item.id);
        return { name: service.name, qty: item.qty };
      }),
      goods: cart.details,
    };
  }

  function presentConfirmation(order, options) {
    const opts = options || {};
    document.getElementById("order-ref").textContent = order.ref;
    const box = document.getElementById("confirm-summary");
    box.replaceChildren(buildSummary(order, true));
    document.body.dataset.view = "done";
    document.title = order.ref + " | KABAMAN Importation Service";
    orderFlow.hidden = true;
    confirmation.hidden = false;
    setStep(4);
    syncDock();
    if (opts.history !== false) history.replaceState({ view: "done" }, "", "#confirmed");
    if (opts.scroll !== false) scrollToId("confirmation");
    if (opts.focus !== false) document.getElementById("confirm-title").focus();
  }

  function placeOrder(event) {
    event.preventDefault();
    if (!validateDetails()) {
      showShop();
      scrollToId("your-order");
      return;
    }

    const name = document.getElementById("customer-name");
    const email = document.getElementById("customer-email");
    const phone = document.getElementById("customer-phone");
    name.value = name.value.trim();
    email.value = email.value.trim();
    phone.value = phone.value.trim();

    if (!checkoutForm.checkValidity()) {
      setStatus(
        "checkout-status",
        "Enter your name and a valid email. Phone is optional. Nothing is charged.",
        true
      );
      checkoutForm.reportValidity();
      return;
    }

    const submitBtn = checkoutForm.querySelector("[type='submit']");
    submitBtn.disabled = true;
    const cart = window.KABAMAN.readCart();
    const saved = window.KABAMAN.saveOrder({
      ref: window.KABAMAN.nextRef(),
      placedAt: new Date().toISOString(),
      services: cart.items.map((item) => {
        const service = window.KABAMAN.findService(item.id);
        return { id: service.id, name: service.name, qty: item.qty };
      }),
      goods: {
        goods: cart.details.goods,
        goodsQty: cart.details.goodsQty,
        destination: cart.details.destination,
        notes: cart.details.notes,
        links: cart.details.links || [],
      },
      contact: {
        name: name.value,
        email: email.value,
        phone: phone.value,
      },
    });
    submitBtn.disabled = false;

    if (!saved) {
      setStatus(
        "checkout-status",
        "This browser blocked local storage, so the order was not saved on this device.",
        true
      );
      return;
    }

    window.KABAMAN.clearCart();
    checkoutForm.reset();
    fillDetails();
    setStatus("checkout-status", "", false);
    setStatus("details-status", "", false);
    renderCart();
    presentConfirmation(saved);
    say("Service order " + saved.ref + " saved. Your order is empty. Nothing was charged.");
  }

  function openOrderEditor() {
    history.replaceState({ view: "shop" }, "", location.pathname + "#your-order");
    showShop();
    scrollToId("your-order");
    closeMenu();
  }

  document.querySelectorAll("[data-add]").forEach((button) => {
    button.addEventListener("click", () => {
      if (document.body.dataset.view !== "shop") showShop();
      addService(button.dataset.add, button);
    });
  });

  cartLines.addEventListener("click", (event) => {
    const row = event.target.closest("[data-id]");
    if (!row) return;
    const id = row.dataset.id;
    if (event.target.closest("[data-inc]")) {
      const cart = window.KABAMAN.readCart();
      const item = cart.items.find((entry) => entry.id === id);
      if (!item) return;
      if (item.qty >= 99) {
        say(window.KABAMAN.findService(id).name + " already covers 99 shipments on this order.");
        return;
      }
      commitQty(id, item.qty + 1);
      renderCart();
      return;
    }
    if (event.target.closest("[data-dec]")) {
      const cart = window.KABAMAN.readCart();
      const item = cart.items.find((entry) => entry.id === id);
      if (!item) return;
      if (item.qty <= 1) {
        removeItem(id);
        return;
      }
      commitQty(id, item.qty - 1);
      renderCart();
      return;
    }
    if (event.target.closest("[data-remove]")) removeItem(id);
  });

  cartLines.addEventListener("input", (event) => {
    const input = event.target.closest("[data-qty-input]");
    if (!input) return;
    const n = Number.parseInt(input.value, 10);
    if (!Number.isFinite(n) || n < 1) return;
    commitQty(input.closest("[data-id]").dataset.id, Math.min(99, n));
  });

  cartLines.addEventListener("focusout", (event) => {
    const input = event.target.closest("[data-qty-input]");
    if (!input) return;
    const n = Number.parseInt(input.value, 10);
    const qty = Number.isFinite(n) && n >= 1 ? Math.min(99, n) : 1;
    input.value = String(qty);
    commitQty(input.closest("[data-id]").dataset.id, qty);
  });

  document.querySelectorAll("[data-detail]").forEach((input) => {
    input.addEventListener("input", () => {
      input.setAttribute("aria-invalid", "false");
      saveDetailsFromInputs();
      if (document.getElementById("details-status").textContent) setStatus("details-status", "", false);
    });
  });

  detailsForm.addEventListener("submit", (event) => {
    event.preventDefault();
    showCheckout();
  });

  checkoutForm.addEventListener("submit", placeOrder);

  document.getElementById("back-to-order").addEventListener("click", openOrderEditor);
  document.getElementById("order-dock").addEventListener("click", (event) => {
    event.preventDefault();
    openOrderEditor();
  });

  document.querySelector(".cart-link").addEventListener("click", (event) => {
    event.preventDefault();
    openOrderEditor();
  });

  document.querySelector(".nav-import").addEventListener("click", (event) => {
    event.preventDefault();
    history.replaceState({ view: "shop" }, "", location.pathname);
    showShop();
    scrollToId("catalog");
    closeMenu();
  });

  document.getElementById("order-again").addEventListener("click", () => {
    history.replaceState({ view: "shop" }, "", location.pathname);
    showShop();
    scrollToId("catalog");
  });

  window.addEventListener("resize", syncDock);

  fillDetails();
  renderCart();
  const orders = window.KABAMAN.readOrders();
  const lastOrder = orders[orders.length - 1];
  const review = new URLSearchParams(location.search).get("review") === "1";
  if (!review && location.hash === "#confirmed" && lastOrder) {
    presentConfirmation(lastOrder, { history: false, scroll: false, focus: false });
  } else if (review && validateDetails()) {
    showCheckout();
  } else {
    showShop();
  }
})();
