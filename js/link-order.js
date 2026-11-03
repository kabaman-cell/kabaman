(function () {
  const form = document.getElementById("import-form");
  if (!form || !window.KABAMAN) return;

  const linkInput = document.getElementById("product-link");
  const error = document.getElementById("link-error");
  const preview = document.getElementById("link-preview");
  const labelEl = document.getElementById("link-label");
  const urlEl = document.getElementById("link-url");
  const descriptionInput = document.getElementById("link-description");
  const serviceInput = document.getElementById("order-service");
  const payService = document.getElementById("pay-service");
  const payAction = document.getElementById("pay-action");
  function serviceList() {
    const site = window.KABAMAN_SITE && window.KABAMAN_SITE.get();
    const items = site && site.services && site.services.length ? site.services : [
      { name: "Importation", action: "" },
      { name: "Sourcing", action: "" },
      { name: "Inspection", action: "" },
    ];
    const ids = ["importation", "sourcing", "inspection"];
    return items.map((item, index) => ({
      name: item.name,
      action: item.action || item.name,
      id: ids[index] || "service-" + index,
    }));
  }
  const moqInput = document.getElementById("moq");
  const moqMinus = document.getElementById("moq-minus");
  const moqPlus = document.getElementById("moq-plus");
  const moqError = document.getElementById("moq-error");
  const payMoq = document.getElementById("pay-moq");
  const payDescription = document.getElementById("pay-description");
  const payWilaya = document.getElementById("pay-wilaya");
  const payCurrency = document.getElementById("pay-currency");
  const payPrice = document.getElementById("pay-price");
  const currencyInput = document.getElementById("currency");
  const nameInput = document.getElementById("link-name");
  const wilayaInput = document.getElementById("link-wilaya");
  const phoneInput = document.getElementById("link-phone");
  const emailInput = document.getElementById("link-email");
  const addressInput = document.getElementById("link-address");
  const idFileInput = document.getElementById("id-file");
  const idScanInput = document.getElementById("id-scan");
  const idName = document.getElementById("id-file-name");
  const confirmation = document.getElementById("link-confirmation");
  let idFile = { name: "", attached: false };
  let activeServiceIndex = null;

  function sourcingMode() {
    return activeServiceIndex === 1;
  }

  function inspectionMode() {
    return activeServiceIndex === 2;
  }

  function formMode() {
    if (sourcingMode()) return "sourcing";
    if (inspectionMode()) return "inspection";
    return "import";
  }

  function readPayment() {
    const input = document.getElementById("order-payment");
    return input ? input.value : "";
  }

  function paymentInvalid() {
    return !readPayment();
  }

  function isSourcingOrder(order) {
    if (!order) return false;
    const serviceId = order.services && order.services[0] && order.services[0].id;
    const serviceName = (order.goods && order.goods.service) || (order.services[0] && order.services[0].name);
    return serviceId === "sourcing" || serviceName === "Sourcing" || order.status === "Waiting for sourcing price";
  }

  function isInspectionOrder(order) {
    if (!order) return false;
    const serviceId = order.services && order.services[0] && order.services[0].id;
    const serviceName = (order.goods && order.goods.service) || (order.services[0] && order.services[0].name);
    return serviceId === "inspection" || serviceName === "Inspection";
  }

  function applyFormMode() {
    const mode = formMode();
    document.querySelectorAll("[data-mode]").forEach((el) => {
      const modes = el.getAttribute("data-mode").split(/\s+/);
      el.hidden = modes.indexOf(mode) === -1;
    });
    hideSteps();
    const nameLabel = document.getElementById("name-label");
    if (nameLabel) nameLabel.textContent = mode === "sourcing" ? "Customer name" : "Name";
    const linkLabel = document.getElementById("product-link-label");
    if (linkLabel) linkLabel.textContent = mode === "sourcing" ? "Product link" : "Paste the product link";
    const idLegend = document.getElementById("id-legend");
    if (idLegend) {
      idLegend.textContent = mode === "sourcing" ? "ID verification" : mode === "inspection" ? "ID" : "ID document";
    }
    if (mode !== "import") showLaterSteps(false);
    paintPrices();
  }

  const USD_PER_KG = 25;

  function formatUsd(amount) {
    const rounded = Math.round(amount * 10) / 10;
    return (rounded % 1 === 0 ? String(rounded) : rounded.toFixed(1)) + " USD";
  }

  function formatKg(kg) {
    const rounded = Math.round(kg * 10) / 10;
    return (rounded % 1 === 0 ? String(rounded) : rounded.toFixed(1)) + " kg";
  }

  function readWeight() {
    const input = document.getElementById("import-weight");
    if (!input) return null;
    const raw = input.value.trim().replace(",", ".");
    if (!raw) return null;
    const value = Number(raw);
    if (!Number.isFinite(value)) return { bad: true };
    if (value > 100) {
      input.value = "100";
      return { kg: 100 };
    }
    if (!/^\d+(\.\d)?$/.test(raw) || value < 1) return { bad: true };
    return { kg: Math.round(value * 10) / 10 };
  }

  function paintPrices() {
    const mode = formMode();
    const fee = document.getElementById("service-fee");
    const total = document.getElementById("import-total");
    const amount = document.getElementById("amount-line");
    const weight = readWeight();
    const importLine = weight && weight.kg
      ? formatKg(weight.kg) + " = " + formatUsd(weight.kg * USD_PER_KG)
      : "25 USD / kg";
    if (fee) fee.textContent = mode === "sourcing" ? "Free" : mode === "inspection" ? "100 USD" : "25 USD / kg";
    if (total) total.textContent = importLine;
    if (amount) amount.textContent = mode === "sourcing" ? "Free" : mode === "inspection" ? "100 USD" : importLine;
  }

  function showError(message, field) {
    error.textContent = message;
    error.classList.toggle("is-error", Boolean(message));
    const anchor = !field || field === linkInput
      ? linkInput
      : field.id === "id-file" || field.id === "id-scan"
        ? document.querySelector(".id-upload")
        : field;
    if (anchor) anchor.insertAdjacentElement("afterend", error);
  }

  function markInvalid(input, bad) {
    if (!input) return;
    input.setAttribute("aria-invalid", bad ? "true" : "false");
  }

  function currentLink() {
    return window.KABAMAN.parseListingUrl(linkInput.value);
  }

  function showPreview(parsed) {
    if (!parsed) {
      preview.hidden = true;
      labelEl.textContent = "";
      urlEl.textContent = "";
      urlEl.removeAttribute("href");
      return;
    }
    preview.hidden = false;
    labelEl.textContent = parsed.label;
    urlEl.textContent = parsed.url;
    urlEl.href = parsed.url;
  }

  function readMoq() {
    if (!moqInput) return 250;
    const digits = String(moqInput.value).replace(/[^\d]/g, "");
    const n = Number.parseInt(digits, 10);
    if (!Number.isFinite(n) || n < 250) return 250;
    return Math.min(9999, n);
  }

  function setMoq(next) {
    if (!moqInput) return 250;
    const moq = Math.min(9999, Math.max(250, next));
    moqInput.value = String(moq);
    if (moqMinus) moqMinus.disabled = moq <= 250;
    if (moqPlus) moqPlus.disabled = moq >= 9999;
    moqInput.setAttribute("aria-invalid", "false");
    if (moqError) moqError.textContent = "";
    if (payMoq) payMoq.textContent = moq + " pieces";
    return moq;
  }

  if (moqMinus) moqMinus.addEventListener("click", () => setMoq(readMoq() - 1));
  if (moqPlus) moqPlus.addEventListener("click", () => setMoq(readMoq() + 1));
  if (moqInput) {
    moqInput.addEventListener("input", () => {
      if (moqInput.value === "") return;
      setMoq(readMoq());
    });
    moqInput.addEventListener("change", () => setMoq(readMoq()));
    setMoq(250);
  }

  function paintCurrency() {
    if (!currencyInput) return;
    const code = currencyInput.value || "DA";
    const label = currencyInput.selectedOptions[0]
      ? currencyInput.selectedOptions[0].textContent
      : code;
    if (payCurrency) payCurrency.textContent = label;
    if (payPrice) payPrice.textContent = "— " + code;
  }

  if (currencyInput) {
    currencyInput.addEventListener("change", paintCurrency);
    paintCurrency();
  }

  function chosenRecord() {
    const list = serviceList();
    const value = serviceInput && serviceInput.value;
    return list.find((item) => item.name === value) || list[0];
  }

  function chosenService() {
    return chosenRecord().name;
  }

  function chosenAction() {
    return chosenRecord().action;
  }

  function paintService() {
    if (payService) payService.textContent = chosenService();
    if (payAction) payAction.textContent = chosenAction();
  }

  if (serviceInput) {
    serviceInput.addEventListener("change", paintService);
    paintService();
  }

  function openService(index) {
    if (!serviceInput || !serviceInput.options[index]) return;
    activeServiceIndex = index;
    serviceInput.selectedIndex = index;
    serviceInput.dispatchEvent(new Event("change", { bubbles: true }));
    const title = document.getElementById("service-detail-title");
    if (title) title.textContent = serviceInput.options[index].textContent;
    document.querySelectorAll("[data-service-info]").forEach((block) => {
      block.hidden = Number(block.getAttribute("data-service-info")) !== index;
    });
    applyFormMode();
    const latest = latestOrder();
    const keepResult = (index === 1 && isSourcingOrder(latest)) || (index === 2 && isInspectionOrder(latest));
    form.hidden = keepResult;
    confirmation.hidden = !keepResult;
    document.querySelectorAll("[data-pick-service]").forEach((button) => {
      button.setAttribute("aria-pressed", String(Number(button.getAttribute("data-pick-service")) === index));
    });
    const detail = document.getElementById("service-detail");
    if (detail) {
      detail.hidden = false;
      detail.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    refreshOrder();
  }

  document.querySelectorAll("[data-pick-service]").forEach((button) => {
    button.addEventListener("click", () => openService(Number(button.getAttribute("data-pick-service"))));
  });

  function rememberId(file) {
    if (!file) return;
    idFile = { name: file.name, attached: true };
    idName.textContent = "Selected: " + file.name;
    showError("");
  }

  idFileInput.addEventListener("change", () => rememberId(idFileInput.files && idFileInput.files[0]));
  idScanInput.addEventListener("change", () => rememberId(idScanInput.files && idScanInput.files[0]));

  linkInput.addEventListener("input", () => {
    showError("");
    markInvalid(linkInput, false);
    showPreview(currentLink());
  });

  const weightInput = document.getElementById("import-weight");
  if (weightInput) {
    weightInput.addEventListener("input", () => {
      readWeight();
      paintPrices();
      markInvalid(weightInput, false);
    });
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (inspectionMode()) {
      submitInspection();
      return;
    }
    const parsed = currentLink();
    if (!linkInput.value.trim()) {
      showPreview(null);
      markInvalid(linkInput, true);
      showError("Paste the product link.");
      linkInput.focus();
      return;
    }
    if (!parsed) {
      showPreview(null);
      markInvalid(linkInput, true);
      showError("Enter a full link, starting with http:// or https://.");
      linkInput.focus();
      return;
    }
    markInvalid(linkInput, false);
    showPreview(parsed);

    if (sourcingMode()) {
      submitSourcing(parsed);
      return;
    }

    const service = chosenService();
    const action = chosenAction();
    const description = descriptionInput.value.trim();
    const name = nameInput.value.trim();
    const wilaya = wilayaInput.value;
    const phone = phoneInput.value.trim();
    const email = emailInput.value.trim();
    const address = addressInput.value.trim();
    const weightInput = document.getElementById("import-weight");
    const weight = readWeight();
    descriptionInput.value = description;
    nameInput.value = name;
    phoneInput.value = phone;
    emailInput.value = email;
    addressInput.value = address;
    const emailBad = !email || !emailInput.checkValidity();
    const checks = [
      [serviceInput, !service, "Select a service."],
      [descriptionInput, !description, "Add a description with quantity, color, and size."],
      [nameInput, !name, "Add your full name."],
      [wilayaInput, !wilaya, "Select a wilaya."],
      [phoneInput, !phone, "Add a phone number."],
      [emailInput, emailBad, "Enter a valid email."],
      [addressInput, !address, "Add the delivery address."],
      [weightInput, !weight || weight.bad, "Enter a weight from 1 to 100 kg, with at most one decimal."],
      [document.getElementById("order-payment"), paymentInvalid(), "Select a payment method."],
    ];
    let firstBad = null;
    checks.forEach((item) => {
      markInvalid(item[0], item[1]);
      if (item[1] && !firstBad) firstBad = item;
    });
    if (!idFile.attached) {
      if (!firstBad) firstBad = [idFileInput, true, "Add an ID document or scan it with your camera."];
    }
    if (firstBad) {
      showError(firstBad[2], firstBad[0]);
      if (firstBad[0] !== idFileInput) firstBad[0].focus();
      return;
    }

    const saved = window.KABAMAN.saveOrder({
      ref: window.KABAMAN.nextRef(),
      placedAt: new Date().toISOString(),
      services: [
        {
          id: chosenRecord().id,
          name: service,
          action: action,
          qty: 1,
        },
      ],
      goods: {
        goods: parsed.label,
        service: service,
        action: action,
        description: description,
        moq: readMoq(),
        currency: currencyInput ? currencyInput.value : "DA",
        wilaya: wilaya,
        address: address,
        weight: weight.kg,
        servicePrice: formatUsd(weight.kg * USD_PER_KG),
        amountUsd: Math.round(weight.kg * USD_PER_KG * 10) / 10,
        links: [
          { url: parsed.url, label: parsed.label },
        ],
      },
      contact: {
        name: name,
        email: email,
        phone: phone,
        wilaya: wilaya,
        address: address,
        idFileName: idFile.name,
        idAttached: true,
      },
      paymentMethod: readPayment(),
      status: "Awaiting ID confirmation",
      reviewWindow: "24 hours",
    });

    if (!saved) {
      showError("This browser blocked saving the order. Allow site data for this page and try again.");
      return;
    }

    window.KABAMAN.clearCart();
    document.getElementById("link-ref").textContent = saved.ref;
    document.getElementById("confirm-label").textContent = parsed.label;
    const confirmUrl = document.getElementById("confirm-url");
    confirmUrl.textContent = parsed.url;
    confirmUrl.href = parsed.url;
    const facts = document.getElementById("confirm-facts");
    facts.replaceChildren();
    [
      ["Service", service],
      ["Action", action],
      ["Description", description],
      ["Name", name],
      ["Wilaya", wilaya],
      ["Phone number", phone],
      ["Email", email],
      ["Address", address],
      ["Weight", formatKg(weight.kg)],
      ["Service price", formatUsd(weight.kg * USD_PER_KG)],
    ].forEach((pair) => {
      const dt = document.createElement("dt");
      dt.textContent = pair[0];
      const dd = document.createElement("dd");
      dd.textContent = pair[1];
      facts.append(dt, dd);
    });
    paintService();
    if (payDescription) payDescription.textContent = description;
    if (payWilaya) payWilaya.textContent = wilaya;
    paintCurrency();
    document.getElementById("confirm-id").textContent =
      "ID received for review: " + idFile.name;
    form.hidden = true;
    confirmation.hidden = false;
    document.title = saved.ref + " | KABAMAN Importation Service";
    refreshOrder();
    confirmation.focus();
  });

  function submitSourcing(parsed) {
    const name = nameInput.value.trim();
    nameInput.value = name;
    const sampleInput = document.getElementById("ask-sample");
    const sample = sampleInput ? sampleInput.value : "";
    const checks = [
      [nameInput, !name, "Add the customer name."],
      [sampleInput, !sample, "Choose Yes or No."],
      [document.getElementById("order-payment"), paymentInvalid(), "Select a payment method."],
    ];
    let firstBad = null;
    checks.forEach((item) => {
      if (!item[0]) return;
      markInvalid(item[0], item[1]);
      if (item[1] && !firstBad) firstBad = item;
    });
    if (!idFile.attached && !firstBad) {
      firstBad = [idFileInput, true, "Add an ID document or scan it with your camera."];
    }
    if (firstBad) {
      showError(firstBad[2], firstBad[0]);
      if (firstBad[0] !== idFileInput) firstBad[0].focus();
      return;
    }
    const service = chosenService();
    const action = chosenAction();
    const saved = window.KABAMAN.saveOrder({
      ref: window.KABAMAN.nextRef(),
      placedAt: new Date().toISOString(),
      services: [{ id: chosenRecord().id, name: service, action: action, qty: 1 }],
      goods: {
        goods: parsed.label,
        service: service,
        action: action,
        sample: sample,
        servicePrice: "Free",
        amountUsd: 0,
        links: [{ url: parsed.url, label: parsed.label }],
      },
      contact: {
        name: name,
        idFileName: idFile.name,
        idAttached: true,
      },
      paymentMethod: readPayment(),
      status: "Waiting for sourcing price",
    });
    if (!saved) {
      showError("This browser blocked saving the order. Allow site data for this page and try again.");
      return;
    }
    showSourcingResult(saved, parsed, name, sample);
  }

  function showSourcingResult(order, parsed, name, sample) {
    document.getElementById("link-ref").textContent = order.ref;
    document.getElementById("confirm-label").textContent = parsed.label;
    const confirmUrl = document.getElementById("confirm-url");
    confirmUrl.textContent = parsed.url;
    confirmUrl.href = parsed.url;
    const facts = document.getElementById("confirm-facts");
    facts.replaceChildren();
    [
      ["Service", order.goods.service],
      ["Customer name", name],
      ["Ask for sample", sample],
      ["Product link", parsed.url],
      ["Service price", "Free"],
    ].forEach((pair) => {
      const dt = document.createElement("dt");
      dt.textContent = pair[0];
      const dd = document.createElement("dd");
      dd.textContent = pair[1];
      facts.append(dt, dd);
    });
    document.getElementById("link-confirm-title").textContent = "Waiting for sourcing price.";
    document.getElementById("confirm-wait").textContent = "Waiting for sourcing price.";
    const lede = document.getElementById("confirm-lede");
    if (lede) lede.hidden = true;
    document.getElementById("confirm-id").textContent = "ID received for review: " + (order.contact.idFileName || "");
    form.hidden = true;
    confirmation.hidden = false;
    showLaterSteps(false);
    document.title = order.ref + " | KABAMAN";
    refreshOrder();
    confirmation.focus();
  }

  function submitInspection() {
    const countryInput = document.getElementById("inspect-country");
    const shipmentInput = document.getElementById("shipment-info");
    const country = countryInput.value.trim();
    const address = addressInput.value.trim();
    const shipment = shipmentInput.value.trim();
    countryInput.value = country;
    addressInput.value = address;
    shipmentInput.value = shipment;
    const checks = [
      [countryInput, !country, "Add the country."],
      [addressInput, !address, "Add the address."],
      [shipmentInput, !shipment, "Add the shipment information."],
      [document.getElementById("order-payment"), paymentInvalid(), "Select a payment method."],
    ];
    let firstBad = null;
    checks.forEach((item) => {
      markInvalid(item[0], item[1]);
      if (item[1] && !firstBad) firstBad = item;
    });
    if (!idFile.attached && !firstBad) {
      firstBad = [idFileInput, true, "Add an ID document or scan it with your camera."];
    }
    if (firstBad) {
      showError(firstBad[2], firstBad[0]);
      if (firstBad[0] !== idFileInput) firstBad[0].focus();
      return;
    }
    const service = chosenService();
    const action = chosenAction();
    const saved = window.KABAMAN.saveOrder({
      ref: window.KABAMAN.nextRef(),
      placedAt: new Date().toISOString(),
      services: [{ id: chosenRecord().id, name: service, action: action, qty: 1 }],
      goods: {
        service: service,
        action: action,
        country: country,
        address: address,
        shipment: shipment,
        servicePrice: "100 USD",
        amountUsd: 100,
      },
      contact: {
        address: address,
        country: country,
        idFileName: idFile.name,
        idAttached: true,
      },
      paymentMethod: readPayment(),
      status: "Awaiting ID confirmation",
      reviewWindow: "24 hours",
    });
    if (!saved) {
      showError("This browser blocked saving the order. Allow site data for this page and try again.");
      return;
    }
    document.getElementById("link-ref").textContent = saved.ref;
    const facts = document.getElementById("confirm-facts");
    facts.replaceChildren();
    [
      ["Service", service],
      ["Country", country],
      ["Address", address],
      ["Shipment information", shipment],
      ["Service price", "100 USD"],
      ["Payment method", readPayment()],
    ].forEach((pair) => {
      const dt = document.createElement("dt");
      dt.textContent = pair[0];
      const dd = document.createElement("dd");
      dd.textContent = pair[1];
      facts.append(dt, dd);
    });
    document.getElementById("link-confirm-title").textContent = "Your inspection request is placed";
    document.getElementById("confirm-wait").textContent = "Your order has been placed. Please wait while we confirm your ID. Confirmation within 24 hours.";
    const lede = document.getElementById("confirm-lede");
    if (lede) lede.hidden = true;
    document.getElementById("confirm-id").textContent = "ID received for review: " + idFile.name;
    document.getElementById("confirm-label").textContent = "";
    const confirmUrl = document.getElementById("confirm-url");
    confirmUrl.textContent = "";
    confirmUrl.removeAttribute("href");
    form.hidden = true;
    confirmation.hidden = false;
    showLaterSteps(false);
    document.title = saved.ref + " | KABAMAN";
    refreshOrder();
    confirmation.focus();
  }

  function latestOrder() {
    const rows = window.KABAMAN.readOrders();
    return rows.length ? rows[rows.length - 1] : null;
  }

  function setStep2Locked() {
    hideSteps();
  }

  function setStep3Locked() {
    hideSteps();
  }

  function hideSteps() {
    ["order-step-list", "step-1-mark", "step-2", "step-3", "step-2-mark", "step-3-mark"].forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.hidden = true;
      el.setAttribute("aria-hidden", "true");
    });
  }

  function showLaterSteps() {
    hideSteps();
  }

  function refreshOrder() {
    const order = latestOrder();
    const panel = document.getElementById("live-order");
    const mode = formMode();
    const matches = order && (
      (mode === "sourcing" && isSourcingOrder(order)) ||
      (mode === "inspection" && isInspectionOrder(order)) ||
      (mode === "import" && !isSourcingOrder(order) && !isInspectionOrder(order))
    );
    if (!matches) {
      if (panel) panel.hidden = true;
      showLaterSteps(false);
      setStep2Locked(true);
      setStep3Locked(true);
      return;
    }
    if (isSourcingOrder(order)) {
      if (panel) panel.hidden = false;
      document.getElementById("live-ref").textContent = order.ref;
      document.getElementById("live-status").textContent = "Waiting for sourcing price";
      document.getElementById("live-wait").textContent = "Waiting for sourcing price.";
      const fileName = order.contact && order.contact.idFileName;
      document.getElementById("live-id").textContent = fileName ? "ID received for review: " + fileName : "";
      document.getElementById("live-reply").textContent = order.reply ? order.reply : "";
      showLaterSteps(false);
      setStep2Locked(true);
      setStep3Locked(true);
      const lede = document.getElementById("confirm-lede");
      if (lede) lede.hidden = true;
      return;
    }
    if (isInspectionOrder(order)) {
      if (panel) panel.hidden = false;
      document.getElementById("live-ref").textContent = order.ref;
      document.getElementById("live-status").textContent = order.status || "Awaiting ID confirmation";
      document.getElementById("live-wait").textContent = "Your order has been placed. Please wait while we confirm your ID. Confirmation within 24 hours.";
      const fileName = order.contact && order.contact.idFileName;
      document.getElementById("live-id").textContent = fileName ? "ID received for review: " + fileName : "";
      document.getElementById("live-reply").textContent = order.reply ? order.reply : "";
      showLaterSteps(false);
      setStep2Locked(true);
      setStep3Locked(true);
      return;
    }
    const lede = document.getElementById("confirm-lede");
    if (lede) lede.hidden = false;
    showLaterSteps(true);
    if (panel) panel.hidden = false;
    document.getElementById("live-ref").textContent = order.ref;
    document.getElementById("live-status").textContent = order.status || "";
    document.getElementById("live-wait").textContent = order.status === "Awaiting ID confirmation"
      ? "Your order has been placed. Please wait while we confirm your ID. Confirmation within 24 hours."
      : "";
    const fileName = order.contact && order.contact.idFileName;
    document.getElementById("live-id").textContent = fileName ? "ID received for review: " + fileName : "";
    document.getElementById("live-reply").textContent = order.reply ? order.reply : "";
    const confirmed = order.status === "ID confirmed";
    setStep2Locked(!confirmed);
    setStep3Locked(!(confirmed && order.negotiationSent));
    if (order.goods && order.goods.moq) setMoq(order.goods.moq);
    if (order.goods && order.goods.currency && currencyInput) {
      currencyInput.value = order.goods.currency;
      paintCurrency();
    }
    if (order.goods && order.goods.targetPrice && payPrice) {
      payPrice.textContent = order.goods.targetPrice + " " + (order.goods.currency || "DA");
    }
    if (order.paymentMethod) {
      const method = document.getElementById("payment-method");
      if (method) method.value = order.paymentMethod;
    }
  }


  window.addEventListener("focus", refreshOrder);
  window.addEventListener("storage", refreshOrder);
  if (window.KABAMAN_SITE) window.KABAMAN_SITE.whenReady(refreshOrder);
  else refreshOrder();
})();
