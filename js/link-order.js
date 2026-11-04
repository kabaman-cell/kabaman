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
  function normalizeForm(value, name) {
    const key = String(value || "").trim().toLowerCase();
    if (key === "import" || key === "importation") return "importation";
    if (key === "sourcing" || key === "inspection" || key === "products" || key === "auction" || key === "auctions") {
      return key === "auctions" ? "auction" : key;
    }
    const byName = {
      importation: "importation",
      sourcing: "sourcing",
      inspection: "inspection",
      products: "products",
      auction: "auction",
      auctions: "auction",
    };
    return byName[String(name || "").trim().toLowerCase()] || "importation";
  }
  function serviceList() {
    const site = window.KABAMAN_SITE && window.KABAMAN_SITE.get();
    const items = site && site.services && site.services.length ? site.services : [
      { name: "Sourcing", price: "19,99 USD", action: "", form: "sourcing" },
      { name: "Importation", price: "24,99 USD / kg", action: "", form: "importation" },
      { name: "Inspection", price: "99,99 USD", action: "", form: "inspection" },
      { name: "Auctions", price: "Place a bid", action: "", form: "auction" },
    ];
    return items.filter((item) => normalizeForm(item.form, item.name) !== "products").map((item) => {
      const form = normalizeForm(item.form, item.name);
      return {
        name: item.name,
        action: item.action || item.name,
        form,
        id: form,
        price: item.price || "",
      };
    });
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
  const addressInput = document.getElementById("link-address");
  const quantityInput = document.getElementById("import-quantity");
  const idFileInput = document.getElementById("id-file");
  const idScanInput = document.getElementById("id-scan");
  const idName = document.getElementById("id-file-name");
  const confirmation = document.getElementById("link-confirmation");
  let idFile = { name: "", attached: false, dataUrl: "", pending: false };
  let idReady = Promise.resolve();
  let activeForm = "";

  function formMode() {
    if (activeForm === "sourcing") return "sourcing";
    if (activeForm === "inspection") return "inspection";
    if (activeForm === "products") return "products";
    if (activeForm === "auction") return "auction";
    return "import";
  }

  function sourcingMode() {
    return formMode() === "sourcing";
  }

  function inspectionMode() {
    return formMode() === "inspection";
  }

  function productsMode() {
    return formMode() === "products";
  }

  function auctionMode() {
    return formMode() === "auction";
  }

  function orderForm(order) {
    if (!order) return "";
    const serviceId = order.services && order.services[0] && order.services[0].id;
    const byId = {
      sourcing: "sourcing",
      inspection: "inspection",
      products: "products",
      auction: "auction",
      importation: "importation",
      import: "importation",
    };
    if (byId[serviceId]) return byId[serviceId];
    const serviceName = (order.goods && order.goods.service) || (order.services && order.services[0] && order.services[0].name) || "";
    const byName = {
      Sourcing: "sourcing",
      Inspection: "inspection",
      Products: "products",
      Auction: "auction",
      Auctions: "auction",
      Importation: "importation",
    };
    if (byName[serviceName]) return byName[serviceName];
    if (order.status === "Waiting for sourcing price") return "sourcing";
    return "importation";
  }

  function isSourcingOrder(order) {
    return orderForm(order) === "sourcing";
  }

  function isInspectionOrder(order) {
    return orderForm(order) === "inspection";
  }

  function isProductsOrder(order) {
    return orderForm(order) === "products";
  }

  function isAuctionOrder(order) {
    return orderForm(order) === "auction";
  }

  function applyFormMode() {
    const mode = formMode();
    document.querySelectorAll("[data-mode]").forEach((el) => {
      const modes = el.getAttribute("data-mode").split(/\s+/);
      el.hidden = modes.indexOf(mode) === -1;
    });
    hideSteps();
    const nameLabel = document.getElementById("name-label");
    if (nameLabel) nameLabel.textContent = "Name";
    const linkLabel = document.getElementById("product-link-label");
    if (linkLabel) linkLabel.textContent = "Product link";
    const idLegend = document.getElementById("id-legend");
    if (idLegend) idLegend.textContent = "ID";
    form.querySelectorAll("[aria-invalid='true']").forEach((el) => markInvalid(el, false));
    showError("");
    if (mode === "import" || mode === "sourcing") showPreview(currentLink());
    else preview.hidden = true;
    if (mode !== "import") showLaterSteps(false);
    paintPrices();
  }

  function siteSettings() {
    const site = window.KABAMAN_SITE && window.KABAMAN_SITE.get();
    const prices = site && site.prices ? site.prices : {};
    const perKg = Number(prices.importPerKg);
    const maxKg = Number(prices.importMaxKg);
    const inspection = Number(prices.inspectionUsd);
    const record = chosenRecord();
    const line = record && record.price;
    return {
      perKg: Number.isFinite(perKg) && perKg > 0 ? perKg : 24.99,
      maxKg: Number.isFinite(maxKg) && maxKg > 0 ? maxKg : 100,
      inspection: Number.isFinite(inspection) && inspection > 0 ? inspection : 99.99,
      sourcingPrice: record && record.form === "sourcing" && line ? line : "19,99 USD",
      productsPrice: record && record.form === "products" && line ? line : "On request",
      auctionPrice: record && record.form === "auction" && line ? line : "Place a bid",
    };
  }

  function formatUsd(amount) {
    const rounded = Math.round(Number(amount) * 100) / 100;
    return rounded.toFixed(2).replace(".", ",") + " USD";
  }

  function readQuantity() {
    if (!quantityInput) return null;
    const raw = quantityInput.value.trim();
    if (!raw) return null;
    if (!/^\d+$/.test(raw)) return { bad: true };
    const pieces = Number(raw);
    if (!Number.isFinite(pieces) || pieces < 250) return { bad: true };
    return { pieces: pieces };
  }

  function paintPrices() {
    const mode = formMode();
    const fee = document.getElementById("service-fee");
    const rates = siteSettings();
    const inspectionPrice = formatUsd(rates.inspection);
    const importLine = formatUsd(rates.perKg).replace(" USD", "") + " USD / kg";
    const text = mode === "sourcing" ? rates.sourcingPrice
      : mode === "inspection" ? inspectionPrice
      : mode === "products" ? rates.productsPrice
      : mode === "auction" ? rates.auctionPrice
      : importLine;
    if (fee) fee.textContent = text;
  }

  function showError(message, field) {
    error.hidden = !message;
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
    const index = serviceInput ? serviceInput.selectedIndex : -1;
    if (index >= 0 && list[index]) return list[index];
    return list[0] || { name: "Importation", action: "Importation", form: "importation", id: "importation", price: "" };
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
    const list = serviceList();
    const record = list[index];
    if (!serviceInput || !record || !serviceInput.options[index]) return;
    activeForm = record.form;
    serviceInput.selectedIndex = index;
    serviceInput.dispatchEvent(new Event("change", { bubbles: true }));
    const title = document.getElementById("service-detail-title");
    if (title) title.textContent = serviceInput.options[index].textContent;
    applyFormMode();
    const latest = latestOrder();
    const keepResult = record.form !== "importation" && !!latest && orderForm(latest) === record.form;
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

  const choiceGrid = document.getElementById("service-choices");
  if (choiceGrid) {
    choiceGrid.addEventListener("click", (event) => {
      const button = event.target.closest("[data-pick-service]");
      if (!button || !choiceGrid.contains(button)) return;
      openService(Number(button.getAttribute("data-pick-service")));
    });
  }

  function readFile(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  function shrinkImage(dataUrl) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const max = 1200;
        let width = img.width;
        let height = img.height;
        if (width > max) {
          height = Math.round(height * (max / width));
          width = max;
        }
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, width, height);
        resolve(canvas.toDataURL("image/jpeg", 0.72));
      };
      img.onerror = () => resolve("");
      img.src = dataUrl;
    });
  }

  function compressId(file) {
    const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
    if (isPdf) {
      if (file.size > 1.5 * 1024 * 1024) return Promise.resolve("");
      return readFile(file);
    }
    return readFile(file).then(shrinkImage);
  }

  function rememberId(file) {
    if (!file) return;
    idFile = { name: file.name, attached: true, dataUrl: "", pending: true };
    idName.textContent = "Selected: " + file.name;
    showError("");
    const chosen = file;
    idReady = compressId(chosen).then((dataUrl) => {
      if (idFile.name !== chosen.name) return;
      idFile = { name: chosen.name, attached: true, dataUrl: dataUrl || "", pending: false };
    }).catch(() => {
      if (idFile.name !== chosen.name) return;
      idFile = { name: chosen.name, attached: true, dataUrl: "", pending: false };
    });
  }

  function idContact(extra) {
    return Object.assign({
      idFileName: idFile.name,
      idAttached: true,
      idImage: idFile.dataUrl || "",
    }, extra || {});
  }

  idFileInput.addEventListener("change", () => rememberId(idFileInput.files && idFileInput.files[0]));
  idScanInput.addEventListener("change", () => rememberId(idScanInput.files && idScanInput.files[0]));

  linkInput.addEventListener("input", () => {
    showError("");
    markInvalid(linkInput, false);
    showPreview(currentLink());
  });

  if (quantityInput) {
    quantityInput.addEventListener("input", () => {
      markInvalid(quantityInput, false);
      showError("");
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (idFile.pending) {
      try { await idReady; } catch (err) { /* keep the file name if the picture cannot be read */ }
    }
    if (inspectionMode()) {
      await submitInspection();
      return;
    }
    if (productsMode()) {
      await submitProducts();
      return;
    }
    if (auctionMode()) {
      await submitAuction();
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
      await submitSourcing(parsed);
      return;
    }

    const service = chosenService();
    const action = chosenAction();
    const specification = descriptionInput.value.trim();
    const name = nameInput.value.trim();
    const wilaya = wilayaInput.value;
    const phone = phoneInput.value.trim();
    const address = addressInput.value.trim();
    const quantity = readQuantity();
    descriptionInput.value = specification;
    nameInput.value = name;
    phoneInput.value = phone;
    addressInput.value = address;
    const checks = [
      [quantityInput, !quantity || quantity.bad, "Enter a whole number of at least 250 pieces."],
      [descriptionInput, !specification, "Add the product specification."],
      [nameInput, !name, "Add your name."],
      [phoneInput, !phone, "Add a phone number."],
      [wilayaInput, !wilaya, "Select a wilaya."],
      [addressInput, !address, "Add the address."],
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

    const saved = await commitOrder({
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
        specification: specification,
        quantity: quantity.pieces,
        wilaya: wilaya,
        address: address,
        servicePrice: formatUsd(siteSettings().perKg).replace(" USD", "") + " USD / kg",
        links: [
          { url: parsed.url, label: parsed.label },
        ],
      },
      contact: idContact({
        name: name,
        phone: phone,
        wilaya: wilaya,
        address: address,
      }),
      status: "Not verified",
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
      ["Product link", parsed.url],
      ["Quantity", quantity.pieces + " pieces"],
      ["Product specification", specification],
      ["Name", name],
      ["Phone number", phone],
      ["Wilaya", wilaya],
      ["Address", address],
      ["Service price", formatUsd(siteSettings().perKg).replace(" USD", "") + " USD / kg"],
    ].forEach((pair) => {
      const dt = document.createElement("dt");
      dt.textContent = pair[0];
      const dd = document.createElement("dd");
      dd.textContent = pair[1];
      facts.append(dt, dd);
    });
    paintService();
    if (payDescription) payDescription.textContent = specification;
    if (payWilaya) payWilaya.textContent = wilaya;
    paintCurrency();
    document.getElementById("link-confirm-title").textContent = "Your import order is placed";
    document.getElementById("confirm-wait").textContent = "Your order has been placed. Please wait while we confirm your ID. Confirmation within 24 hours.";
    const lede = document.getElementById("confirm-lede");
    if (lede) lede.hidden = false;
    document.getElementById("confirm-id").textContent =
      "ID received for review: " + idFile.name;
    form.hidden = true;
    confirmation.hidden = false;
    document.title = saved.ref + " | KABAMAN Importation Service";
    refreshOrder();
    confirmation.focus();
  });

  async function commitOrder(order) {
    if (!(window.KABAMAN_API && await window.KABAMAN_API.available())) {
      return window.KABAMAN.saveOrder(order);
    }
    const session = await window.KABAMAN_API.me();
    if (!session || session.role !== "customer") {
      const ok = await window.KABAMAN_API.ensureCustomer();
      if (!ok) {
        showError("Create an account or log in before the order is saved.");
        return null;
      }
    }
    try {
      return await window.KABAMAN_API.createOrder(order);
    } catch (err) {
      showError(err.message || "The order could not be saved.");
      return null;
    }
  }

  async function submitSourcing(parsed) {
    const name = nameInput.value.trim();
    const phone = phoneInput.value.trim();
    nameInput.value = name;
    phoneInput.value = phone;
    const checks = [
      [nameInput, !name, "Add your name."],
      [phoneInput, !phone, "Add a phone number."],
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
    const saved = await commitOrder({
      ref: window.KABAMAN.nextRef(),
      placedAt: new Date().toISOString(),
      services: [{ id: chosenRecord().id, name: service, action: action, qty: 1 }],
      goods: {
        goods: parsed.label,
        service: service,
        action: action,
        servicePrice: siteSettings().sourcingPrice,
        links: [{ url: parsed.url, label: parsed.label }],
      },
      contact: idContact({ name: name, phone: phone }),
      status: "Not verified",
    });
    if (!saved) {
      showError("This browser blocked saving the order. Allow site data for this page and try again.");
      return;
    }
    showSourcingResult(saved, parsed, name, phone);
  }

  function showSourcingResult(order, parsed, name, phone) {
    document.getElementById("link-ref").textContent = order.ref;
    document.getElementById("confirm-label").textContent = parsed.label;
    const confirmUrl = document.getElementById("confirm-url");
    confirmUrl.textContent = parsed.url;
    confirmUrl.href = parsed.url;
    const facts = document.getElementById("confirm-facts");
    facts.replaceChildren();
    [
      ["Service", order.goods.service],
      ["Name", name],
      ["Phone number", phone],
      ["Product link", parsed.url],
      ["Service price", order.goods.servicePrice || ""],
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

  async function submitInspection() {
    const countryInput = document.getElementById("supplier-country");
    const supplierAddressInput = document.getElementById("supplier-address");
    const supplierPhoneInput = document.getElementById("supplier-phone");
    const checklistInput = document.getElementById("inspect-checklist");
    const country = countryInput.value.trim();
    const supplierAddress = supplierAddressInput.value.trim();
    const supplierPhone = supplierPhoneInput.value.trim();
    const checklist = checklistInput.value.trim();
    countryInput.value = country;
    supplierAddressInput.value = supplierAddress;
    supplierPhoneInput.value = supplierPhone;
    checklistInput.value = checklist;
    const checks = [
      [countryInput, !country, "Add the country of the customer's supplier."],
      [supplierAddressInput, !supplierAddress, "Add the address of the customer's supplier."],
      [supplierPhoneInput, !supplierPhone, "Add the phone number of the supplier."],
      [checklistInput, !checklist, "Add the checklist to inspect."],
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
    const saved = await commitOrder({
      ref: window.KABAMAN.nextRef(),
      placedAt: new Date().toISOString(),
      services: [{ id: chosenRecord().id, name: service, action: action, qty: 1 }],
      goods: {
        service: service,
        action: action,
        supplierCountry: country,
        supplierAddress: supplierAddress,
        supplierPhone: supplierPhone,
        checklist: checklist,
        servicePrice: formatUsd(siteSettings().inspection),
      },
      contact: idContact({
        supplierCountry: country,
        supplierAddress: supplierAddress,
        supplierPhone: supplierPhone,
      }),
      status: "Not verified",
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
      ["Country of the customer's supplier", country],
      ["Address of the customer's supplier", supplierAddress],
      ["Phone number of the supplier", supplierPhone],
      ["Checklist to inspect", checklist],
      ["Service price", formatUsd(siteSettings().inspection)],
    ].forEach((pair) => {
      const dt = document.createElement("dt");
      dt.textContent = pair[0];
      const dd = document.createElement("dd");
      dd.textContent = pair[1];
      facts.append(dt, dd);
    });
    document.getElementById("link-confirm-title").textContent = "Your inspection request is placed";
    document.getElementById("confirm-wait").textContent = "Your inspection request is placed. Nothing has been charged.";
    const lede = document.getElementById("confirm-lede");
    if (lede) lede.hidden = true;
    document.getElementById("confirm-id").textContent = "ID received for review: " + (saved.contact.idFileName || "");
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

  function showPlaced(order, title, wait, pairs) {
    document.getElementById("link-ref").textContent = order.ref;
    const facts = document.getElementById("confirm-facts");
    facts.replaceChildren();
    pairs.forEach((pair) => {
      const dt = document.createElement("dt");
      dt.textContent = pair[0];
      const dd = document.createElement("dd");
      dd.textContent = pair[1];
      facts.append(dt, dd);
    });
    document.getElementById("link-confirm-title").textContent = title;
    document.getElementById("confirm-wait").textContent = wait;
    const lede = document.getElementById("confirm-lede");
    if (lede) lede.hidden = true;
    document.getElementById("confirm-id").textContent = "ID received for review: " + ((order.contact && order.contact.idFileName) || "");
    document.getElementById("confirm-label").textContent = "";
    const confirmUrl = document.getElementById("confirm-url");
    confirmUrl.textContent = "";
    confirmUrl.removeAttribute("href");
    form.hidden = true;
    confirmation.hidden = false;
    showLaterSteps(false);
    document.title = order.ref + " | KABAMAN";
    refreshOrder();
    confirmation.focus();
  }

  function firstInvalid(checks) {
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
      return true;
    }
    return false;
  }

  async function submitProducts() {
    const productNameInput = document.getElementById("product-name");
    const productQtyInput = document.getElementById("product-quantity");
    const productName = productNameInput.value.trim();
    const qtyRaw = productQtyInput.value.trim();
    const quantity = /^\d+$/.test(qtyRaw) ? Number(qtyRaw) : 0;
    const name = nameInput.value.trim();
    const phone = phoneInput.value.trim();
    const wilaya = wilayaInput.value;
    const address = addressInput.value.trim();
    productNameInput.value = productName;
    nameInput.value = name;
    phoneInput.value = phone;
    addressInput.value = address;
    if (firstInvalid([
      [productNameInput, !productName, "Add the product name."],
      [productQtyInput, !Number.isInteger(quantity) || quantity < 1, "Enter a whole number of at least 1."],
      [nameInput, !name, "Add your name."],
      [phoneInput, !phone, "Add a phone number."],
      [wilayaInput, !wilaya, "Select a wilaya."],
      [addressInput, !address, "Add the address."],
    ])) return;
    const service = chosenService();
    const action = chosenAction();
    const saved = await commitOrder({
      ref: window.KABAMAN.nextRef(),
      placedAt: new Date().toISOString(),
      services: [{ id: chosenRecord().id, name: service, action: action, qty: 1 }],
      goods: {
        service: service,
        action: action,
        productName: productName,
        quantity: quantity,
        wilaya: wilaya,
        address: address,
        servicePrice: siteSettings().productsPrice,
      },
      contact: idContact({
        name: name,
        phone: phone,
        wilaya: wilaya,
        address: address,
      }),
      status: "Not verified",
    });
    if (!saved) {
      showError("This browser blocked saving the order. Allow site data for this page and try again.");
      return;
    }
    showPlaced(saved, "Your products order is placed", "Your products order is placed. Nothing has been charged.", [
      ["Service", service],
      ["Product name", productName],
      ["Quantity", String(quantity)],
      ["Name", name],
      ["Phone number", phone],
      ["Wilaya", wilaya],
      ["Address", address],
      ["Price", saved.goods.servicePrice || "On request"],
    ]);
  }

  async function submitAuction() {
    const descriptionInput = document.getElementById("auction-description");
    const bidInput = document.getElementById("auction-bid");
    const description = descriptionInput.value.trim();
    const bid = Number(String(bidInput.value).trim().replace(",", "."));
    const name = nameInput.value.trim();
    const phone = phoneInput.value.trim();
    descriptionInput.value = description;
    nameInput.value = name;
    phoneInput.value = phone;
    if (firstInvalid([
      [descriptionInput, !description, "Describe the goods."],
      [bidInput, !Number.isFinite(bid) || bid <= 0, "Enter a bid greater than 0."],
      [nameInput, !name, "Add your name."],
      [phoneInput, !phone, "Add a phone number."],
    ])) return;
    const service = chosenService();
    const action = chosenAction();
    const saved = await commitOrder({
      ref: window.KABAMAN.nextRef(),
      placedAt: new Date().toISOString(),
      services: [{ id: chosenRecord().id, name: service, action: action, qty: 1 }],
      goods: {
        service: service,
        action: action,
        description: description,
        bid: bid,
        servicePrice: formatUsd(bid),
      },
      contact: idContact({ name: name, phone: phone }),
      status: "Not verified",
    });
    if (!saved) {
      showError("This browser blocked saving the order. Allow site data for this page and try again.");
      return;
    }
    showPlaced(saved, "Your bid is placed", "Your bid is placed. Nothing has been charged.", [
      ["Service", service],
      ["Description of the goods", description],
      ["Bid amount in USD", formatUsd(bid)],
      ["Name", name],
      ["Phone number", phone],
    ]);
  }

  function latestOrder() {
    if (window.KABAMAN_API && window.KABAMAN_API.usingServer()) {
      const rows = window.KABAMAN_API.cachedOrders();
      return rows.length ? rows[rows.length - 1] : null;
    }
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

  function customerStatus(order) {
    if (window.KABAMAN.identityVerified(order)) {
      return { text: "Verified", className: "status-verified" };
    }
    return { text: "Not verified", className: "status-not-verified" };
  }

  function paintStatus(el, order) {
    if (!el) return;
    const status = customerStatus(order);
    el.textContent = status.text;
    el.classList.remove("status-verified", "status-waiting", "status-not-verified");
    el.classList.add(status.className);
  }

  function customerWait(order) {
    if (isSourcingOrder(order) && !window.KABAMAN.identityVerified(order)) {
      return "Waiting for sourcing price.";
    }
    const stored = (order && order.status) || "";
    if (stored === "Pending Verification" || stored === "Awaiting ID confirmation") {
      return "Your order has been placed. Please wait while we confirm your ID. Confirmation within 24 hours.";
    }
    return "";
  }

  function paintLiveLink(order) {
    const slot = document.getElementById("live-link");
    if (!slot) return;
    slot.replaceChildren();
    window.KABAMAN.productUrls(order).forEach((item, index) => {
      if (index) slot.appendChild(document.createTextNode(" "));
      const anchor = document.createElement("a");
      anchor.href = item.href;
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
      anchor.textContent = item.href;
      slot.appendChild(anchor);
    });
  }

  function paintLive(order) {
    document.getElementById("live-ref").textContent = order.ref;
    paintStatus(document.getElementById("live-status"), order);
    paintStatus(document.getElementById("confirm-status"), order);
    document.getElementById("live-wait").textContent = customerWait(order);
    const fileName = order.contact && order.contact.idFileName;
    const idLine = fileName ? "ID received for review: " + fileName : "";
    document.getElementById("live-id").textContent = idLine;
    const confirmId = document.getElementById("confirm-id");
    if (confirmId) confirmId.textContent = idLine;
    const reply = order.reply ? order.reply : "";
    document.getElementById("live-reply").textContent = reply;
    const confirmReply = document.getElementById("confirm-reply");
    if (confirmReply) confirmReply.textContent = reply;
    paintLiveLink(order);
  }

  function refreshOrder() {
    const order = latestOrder();
    const panel = document.getElementById("live-order");
    const mode = formMode();
    const matches = order && (
      (mode === "sourcing" && isSourcingOrder(order)) ||
      (mode === "inspection" && isInspectionOrder(order)) ||
      (mode === "products" && isProductsOrder(order)) ||
      (mode === "auction" && isAuctionOrder(order)) ||
      (mode === "import" && !isSourcingOrder(order) && !isInspectionOrder(order) && !isProductsOrder(order) && !isAuctionOrder(order))
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
      paintLive(order);
      showLaterSteps(false);
      setStep2Locked(true);
      setStep3Locked(true);
      const lede = document.getElementById("confirm-lede");
      if (lede) lede.hidden = true;
      return;
    }
    if (isInspectionOrder(order) || isProductsOrder(order) || isAuctionOrder(order)) {
      if (panel) panel.hidden = false;
      paintLive(order);
      showLaterSteps(false);
      setStep2Locked(true);
      setStep3Locked(true);
      const placedLede = document.getElementById("confirm-lede");
      if (placedLede && !isInspectionOrder(order)) placedLede.hidden = true;
      return;
    }
    const lede = document.getElementById("confirm-lede");
    if (lede) lede.hidden = false;
    showLaterSteps(true);
    if (panel) panel.hidden = false;
    paintLive(order);
    const confirmed = window.KABAMAN.identityVerified(order);
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
  function onSiteReady() {
    paintPrices();
    refreshOrder();
  }

  if (window.KABAMAN_SITE) window.KABAMAN_SITE.whenReady(onSiteReady);
  else onSiteReady();
  if (window.KABAMAN_API) window.KABAMAN_API.onOrders(refreshOrder);
})();
