(function () {
  "use strict";

  var api = window.KABAMAN_API;
  var notice = document.getElementById("wa-notice");
  var login = document.getElementById("wa-login");
  var app = document.getElementById("wa-app");
  var loginForm = document.getElementById("wa-login-form");
  var logoutButton = document.getElementById("inbox-logout");
  var list = document.getElementById("wa-thread-list");
  var search = document.getElementById("wa-search");
  var messages = document.getElementById("wa-messages");
  var replyForm = document.getElementById("wa-reply-form");
  var replyInput = document.getElementById("wa-reply");
  var activeWaId = "";
  var conversations = [];
  var timer = 0;

  function setNotice(text, error) {
    notice.textContent = text;
    notice.classList.toggle("is-error", Boolean(error));
  }

  function setChatStatus(text, error) {
    var status = document.getElementById("wa-chat-status");
    status.textContent = text || "";
    status.classList.toggle("is-error", Boolean(error));
  }

  function formatTime(value) {
    if (!value) return "";
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("fr-DZ", { dateStyle: "short", timeStyle: "short" }).format(date);
  }

  function textNode(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = text || "";
    return node;
  }

  function renderConversations() {
    var query = search.value.trim().toLowerCase();
    var rows = conversations.filter(function (item) {
      return !query || (String(item.contact_name || "") + " " + String(item.wa_id || "") + " " + String(item.last_message_preview || "")).toLowerCase().includes(query);
    });
    list.replaceChildren();
    if (!rows.length) {
      list.appendChild(textNode("p", "wa-empty", query ? "Aucun résultat." : "Aucune conversation reçue."));
      return;
    }
    rows.forEach(function (item) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "wa-thread" + (item.wa_id === activeWaId ? " is-active" : "");
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", String(item.wa_id === activeWaId));
      button.dataset.waId = item.wa_id;
      button.appendChild(textNode("span", "wa-thread-name", item.contact_name || item.wa_id));
      button.appendChild(textNode("time", "wa-thread-time", formatTime(item.last_message_at)));
      button.appendChild(textNode("span", "wa-thread-phone", item.wa_id));
      if (Number(item.unread_count) > 0) button.appendChild(textNode("span", "wa-unread", String(item.unread_count)));
      button.appendChild(textNode("span", "wa-thread-preview", item.last_message_preview || "Nouveau message"));
      button.addEventListener("click", function () { selectConversation(item.wa_id); });
      list.appendChild(button);
    });
  }

  function renderMessages(items) {
    messages.replaceChildren();
    if (!items || !items.length) {
      messages.appendChild(textNode("p", "wa-empty", "Aucun message dans cette conversation."));
      return;
    }
    items.forEach(function (item) {
      var outbound = item.direction === "outbound";
      var bubble = document.createElement("article");
      bubble.className = "wa-message" + (outbound ? " is-outbound" : "");
      var body = item.body || "";
      if (item.message_type && item.message_type !== "text" && !body) body = "Contenu de type " + item.message_type + " reçu dans WhatsApp.";
      bubble.appendChild(textNode("p", "wa-message-body", body));
      if (item.media_id) {
        var mediaUrl = "/api/admin/whatsapp/media/" + encodeURIComponent(item.media_id);
        if (item.message_type === "image" || item.message_type === "sticker") {
          var image = document.createElement("img");
          image.className = "wa-attachment";
          image.src = mediaUrl;
          image.alt = "Pièce jointe reçue dans WhatsApp";
          image.loading = "lazy";
          bubble.appendChild(image);
        } else if (item.message_type === "video") {
          var video = document.createElement("video");
          video.className = "wa-attachment";
          video.src = mediaUrl;
          video.controls = true;
          video.preload = "metadata";
          bubble.appendChild(video);
        } else if (item.message_type === "audio") {
          var audio = document.createElement("audio");
          audio.className = "wa-attachment-audio";
          audio.src = mediaUrl;
          audio.controls = true;
          audio.preload = "metadata";
          bubble.appendChild(audio);
        } else {
          var attachment = document.createElement("a");
          attachment.className = "wa-attachment-link";
          attachment.href = mediaUrl;
          attachment.target = "_blank";
          attachment.rel = "noopener noreferrer";
          attachment.textContent = "Ouvrir la pièce jointe";
          bubble.appendChild(attachment);
        }
      }
      var meta = document.createElement("div");
      meta.className = "wa-message-meta";
      meta.appendChild(textNode("time", "", formatTime(item.created_at)));
      if (outbound && item.status) meta.appendChild(textNode("span", "", item.status));
      bubble.appendChild(meta);
      messages.appendChild(bubble);
    });
    messages.scrollTop = messages.scrollHeight;
  }

  function loadMessages(waId) {
    if (!waId) return Promise.resolve();
    return api.whatsappMessages(waId).then(function (items) {
      if (waId === activeWaId) renderMessages(items);
    });
  }

  function loadConversations() {
    return api.whatsappConversations().then(function (items) {
      conversations = Array.isArray(items) ? items : [];
      document.getElementById("wa-count").textContent = conversations.length + (conversations.length === 1 ? " conversation" : " conversations");
      renderConversations();
      if (activeWaId && !conversations.some(function (item) { return item.wa_id === activeWaId; })) {
        activeWaId = "";
        showNoSelection();
      }
      if (activeWaId) return loadMessages(activeWaId);
    });
  }

  function showNoSelection() {
    document.getElementById("wa-chat-name").textContent = "Choisis une conversation";
    document.getElementById("wa-chat-number").textContent = "";
    document.getElementById("wa-open-phone").hidden = true;
    replyForm.hidden = true;
    renderMessages([]);
  }

  function selectConversation(waId) {
    activeWaId = waId;
    var item = conversations.find(function (row) { return row.wa_id === waId; });
    if (!item) return;
    document.getElementById("wa-chat-name").textContent = item.contact_name || waId;
    document.getElementById("wa-chat-number").textContent = waId;
    var open = document.getElementById("wa-open-phone");
    open.href = "https://wa.me/" + encodeURIComponent(waId);
    open.hidden = false;
    replyForm.hidden = false;
    setChatStatus("");
    renderConversations();
    renderMessages([]);
    api.whatsappMarkRead(waId).then(loadConversations).catch(function () {});
  }

  function showInbox() {
    login.hidden = true;
    app.hidden = false;
    logoutButton.hidden = false;
    return api.whatsappStatus().then(function (state) {
      if (!state || !state.enabled) {
        setNotice("Le serveur est connecté, mais WhatsApp Business Platform n’est pas encore configuré.", true);
      } else {
        setNotice("Connecté au serveur KABAMAN. Actualisation automatique.", false);
      }
      return loadConversations();
    });
  }

  if (!api) {
    setNotice("Le tableau de bord ne peut pas se connecter au serveur KABAMAN.", true);
    return;
  }

  api.available().then(function (online) {
    if (!online) {
      setNotice("Le serveur KABAMAN doit être hébergé pour recevoir les messages WhatsApp.", true);
      return;
    }
    return api.me().then(function (session) {
      if (session && session.role === "admin") {
        return showInbox();
      }
      login.hidden = false;
      setNotice("Connecte-toi pour ouvrir la boîte WhatsApp.", false);
    });
  }).catch(function (err) {
    setNotice(err.message || "Impossible de joindre le serveur KABAMAN.", true);
  });

  loginForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var note = document.getElementById("wa-login-error");
    note.textContent = "";
    api.adminLogin(document.getElementById("wa-admin-password").value).then(showInbox).catch(function (err) {
      note.textContent = err.message || "Connexion impossible.";
    });
  });

  logoutButton.addEventListener("click", function () {
    api.logout().then(function () { window.location.reload(); }).catch(function (err) {
      setNotice(err.message || "Déconnexion impossible.", true);
    });
  });

  document.getElementById("wa-refresh").addEventListener("click", function () {
    loadConversations().catch(function (err) { setNotice(err.message || "Actualisation impossible.", true); });
  });
  search.addEventListener("input", renderConversations);

  replyForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = replyInput.value.trim();
    if (!activeWaId || !text) return;
    var submit = replyForm.querySelector("[type=submit]");
    submit.disabled = true;
    setChatStatus("Envoi du message…");
    api.whatsappSendReply(activeWaId, text).then(function () {
      replyInput.value = "";
      setChatStatus("Message envoyé.");
      return loadConversations();
    }).catch(function (err) {
      setChatStatus(err.message || "Le message n’a pas pu être envoyé.", true);
    }).finally(function () { submit.disabled = false; });
  });

  timer = window.setInterval(function () {
    if (!app.hidden) loadConversations().catch(function () {});
  }, 7000);
  window.addEventListener("beforeunload", function () { if (timer) window.clearInterval(timer); });
})();
