(function () {
  var online = false;
  var checked = null;
  var meCache = null;
  var ordersCache = [];
  var orderWaiters = [];
  var source = null;
  var pollTimer = 0;

  function request(method, url, body) {
    return fetch(url, {
      method: method,
      credentials: "same-origin",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) {
          var error = new Error((data && data.error) || "Request failed.");
          error.status = response.status;
          throw error;
        }
        return data;
      });
    });
  }

  function available() {
    if (checked) return checked;
    checked = fetch("/api/health", { credentials: "same-origin" })
      .then(function (response) {
        online = response.ok;
        return online;
      })
      .catch(function () {
        online = false;
        return false;
      });
    return checked;
  }

  function rememberMe(data) {
    meCache = data && data.role ? data : { role: "" };
    var link = document.getElementById("account-link");
    if (link) link.textContent = meCache.role === "customer" ? "Your orders" : "Account";
    return meCache;
  }

  function me() {
    return available().then(function (ok) {
      if (!ok) return { role: "" };
      return request("GET", "/api/me").then(rememberMe);
    });
  }

  function notifyOrders() {
    orderWaiters.slice().forEach(function (fn) { fn(ordersCache); });
  }

  function loadOrders() {
    if (!online || !meCache || meCache.role !== "customer") {
      ordersCache = [];
      notifyOrders();
      return Promise.resolve(ordersCache);
    }
    return request("GET", "/api/orders").then(function (data) {
      ordersCache = data && data.orders ? data.orders : [];
      notifyOrders();
      return ordersCache;
    }).catch(function () {
      return ordersCache;
    });
  }

  function watchOrders() {
    available().then(function (ok) {
      if (!ok) return me();
      return me();
    }).then(function () {
      if (!online || !meCache || !meCache.role) return;
      loadOrders();
      if (window.EventSource && !source) {
        source = new EventSource("/api/events");
        source.onmessage = function () { loadOrders(); };
      }
      if (!pollTimer) {
        pollTimer = window.setInterval(loadOrders, 5000);
      }
    });
  }

  function ensureCustomer() {
    var gate = document.getElementById("account-gate");
    if (!gate) return Promise.resolve(false);
    gate.hidden = false;
    if (gate.scrollIntoView) gate.scrollIntoView({ behavior: "smooth", block: "start" });
    return new Promise(function (resolve) {
      var form = document.getElementById("auth-form");
      var note = document.getElementById("auth-note");
      var extra = document.getElementById("auth-register-fields");
      var submit = document.getElementById("auth-submit");
      var toggle = document.getElementById("auth-switch");
      var cancel = document.getElementById("auth-cancel");
      var mode = "login";
      function finish(ok) {
        gate.hidden = true;
        if (note) note.textContent = "";
        resolve(ok);
      }
      function setMode(next) {
        mode = next;
        if (extra) extra.hidden = mode !== "register";
        if (submit) submit.textContent = mode === "register" ? "Create account" : "Log in";
        if (toggle) toggle.textContent = mode === "register" ? "I already have an account" : "Create an account";
      }
      setMode("login");
      function onSubmit(event) {
        event.preventDefault();
        var email = document.getElementById("auth-email").value.trim();
        var password = document.getElementById("auth-password").value;
        var name = document.getElementById("auth-name") ? document.getElementById("auth-name").value.trim() : "";
        var phone = document.getElementById("auth-phone") ? document.getElementById("auth-phone").value.trim() : "";
        var action = mode === "register"
          ? request("POST", "/api/register", { email: email, password: password, name: name, phone: phone })
          : request("POST", "/api/login", { email: email, password: password });
        action.then(function (data) {
          rememberMe(data);
          form.removeEventListener("submit", onSubmit);
          if (toggle) toggle.removeEventListener("click", onToggle);
          if (cancel) cancel.removeEventListener("click", onCancel);
          loadOrders();
          watchOrders();
          finish(true);
        }).catch(function (err) {
          if (note) note.textContent = err.message || "Could not sign in.";
        });
      }
      function onToggle() {
        setMode(mode === "login" ? "register" : "login");
      }
      function onCancel() {
        form.removeEventListener("submit", onSubmit);
        if (toggle) toggle.removeEventListener("click", onToggle);
        if (cancel) cancel.removeEventListener("click", onCancel);
        finish(false);
      }
      form.addEventListener("submit", onSubmit);
      if (toggle) toggle.addEventListener("click", onToggle);
      if (cancel) cancel.addEventListener("click", onCancel);
    });
  }

  function createOrder(order) {
    var contact = Object.assign({}, order.contact || {});
    var image = contact.idImage || "";
    delete contact.idImage;
    return request("POST", "/api/orders", {
      order: Object.assign({}, order, { contact: contact, status: "Not verified" }),
      idImage: image,
      idFileName: contact.idFileName || "",
    }).then(function (saved) {
      ordersCache = ordersCache.filter(function (item) { return item.ref !== saved.ref; }).concat([saved]);
      notifyOrders();
      return saved;
    });
  }

  function mountAccount() {
    var gate = document.getElementById("account-gate");
    var board = document.getElementById("account-board");
    if (!gate || !board) return;
    available().then(me).then(function (session) {
      if (!online) {
        gate.hidden = false;
        var note = document.getElementById("auth-note");
        if (note) note.textContent = "The account server is not running.";
        return;
      }
      if (!session || session.role !== "customer") {
        gate.hidden = false;
        board.hidden = true;
        ensureCustomer().then(function (ok) {
          if (ok) window.location.reload();
        });
        return;
      }
      gate.hidden = true;
      board.hidden = false;
      paintAccount(session.customer || {});
      watchOrders();
    });
    var profileForm = document.getElementById("profile-form");
    if (profileForm) {
      profileForm.addEventListener("submit", function (event) {
        event.preventDefault();
        request("PATCH", "/api/me", {
          name: document.getElementById("profile-name").value.trim(),
          phone: document.getElementById("profile-phone").value.trim(),
        }).then(function (data) {
          rememberMe(data);
          paintAccount((data && data.customer) || {});
        }).catch(function (err) {
          var note = document.getElementById("profile-note");
          if (note) note.textContent = err.message || "Could not save the profile.";
        });
      });
    }
    var logout = document.getElementById("account-logout");
    if (logout) {
      logout.addEventListener("click", function () {
        request("POST", "/api/logout").finally(function () { window.location.reload(); });
      });
    }
  }

  function paintAccount(customer) {
    var heading = document.getElementById("account-heading");
    if (heading) heading.textContent = customer.name ? customer.name : "Your orders";
    var email = document.getElementById("profile-email");
    if (email) email.textContent = customer.email || "";
    var name = document.getElementById("profile-name");
    if (name && document.activeElement !== name) name.value = customer.name || "";
    var phone = document.getElementById("profile-phone");
    if (phone && document.activeElement !== phone) phone.value = customer.phone || "";
    paintOrderList();
  }

  function paintOrderList() {
    var host = document.getElementById("account-orders");
    if (!host) return;
    host.replaceChildren();
    if (!ordersCache.length) {
      var empty = document.createElement("p");
      empty.textContent = "No orders yet.";
      host.appendChild(empty);
      return;
    }
    ordersCache.slice().reverse().forEach(function (order) {
      var card = document.createElement("article");
      card.className = "account-card";
      var title = document.createElement("h2");
      var service = (order.services && order.services[0] && order.services[0].name) || "Order";
      title.textContent = service + " · " + order.ref;
      var status = document.createElement("p");
      var verified = window.KABAMAN && window.KABAMAN.identityVerified(order);
      status.className = "order-status " + (verified ? "status-verified" : "status-not-verified");
      status.textContent = verified ? "Verified" : "Not verified";
      card.append(title, status);
      if (order.reply) {
        var reply = document.createElement("p");
        reply.className = "customer-reply";
        reply.textContent = order.reply;
        card.appendChild(reply);
      }
      host.appendChild(card);
    });
  }

  window.KABAMAN_API = {
    available: available,
    usingServer: function () { return online; },
    me: me,
    role: function () { return meCache && meCache.role || ""; },
    ensureCustomer: ensureCustomer,
    createOrder: createOrder,
    cachedOrders: function () { return ordersCache.slice(); },
    onOrders: function (fn) { orderWaiters.push(fn); },
    watchOrders: watchOrders,
    site: function () {
      return available().then(function (ok) {
        if (!ok) return null;
        return request("GET", "/api/site");
      });
    },
    adminLogin: function (password) {
      return request("POST", "/api/admin/login", { password: password }).then(rememberMe);
    },
    saveSite: function (site) { return request("PUT", "/api/admin/site", site); },
    resetSite: function () { return request("POST", "/api/admin/site/reset", {}); },
    adminOrders: function () {
      return request("GET", "/api/admin/orders").then(function (data) { return data.orders || []; });
    },
    updateOrder: function (ref, patch) { return request("PATCH", "/api/admin/orders/" + encodeURIComponent(ref), patch); },
    deleteOrder: function (ref) { return request("DELETE", "/api/admin/orders/" + encodeURIComponent(ref)); },
    openId: function (ref) {
      return fetch("/api/admin/orders/" + encodeURIComponent(ref) + "/id", { credentials: "same-origin" })
        .then(function (response) {
          if (!response.ok) throw new Error("The ID file is not available.");
          return response.blob();
        })
        .then(function (blob) {
          var url = URL.createObjectURL(blob);
          window.open(url, "_blank", "noopener");
          return url;
        });
    },
    mountAccount: mountAccount,
  };

  if (document.getElementById("account-board")) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountAccount);
    else mountAccount();
  } else {
    watchOrders();
  }
  window.KABAMAN_API.onOrders(paintOrderList);
})();
