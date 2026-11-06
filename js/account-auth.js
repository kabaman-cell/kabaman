import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

(function () {
  "use strict";

  var config = window.KABAMAN_CONFIG || {};
  var gate = document.getElementById("account-gate");
  var board = document.getElementById("account-board");
  var authForm = document.getElementById("auth-form");
  var authNote = document.getElementById("auth-note");
  var configNote = document.getElementById("auth-config-note");
  var authHeading = document.getElementById("auth-heading");
  var authIntro = document.getElementById("auth-intro");
  var registerFields = document.getElementById("auth-register-fields");
  var submitButton = document.getElementById("auth-submit");
  var switchButton = document.getElementById("auth-switch");
  var client = null;
  var mode = "login";

  function setNote(node, message, isError) {
    if (!node) return;
    node.textContent = message || "";
    node.classList.toggle("is-error", Boolean(isError && message));
  }

  function redirectUrl() {
    return window.location.href.split(/[?#]/)[0];
  }

  function friendlyError(error) {
    var message = String(error && error.message || "");
    var lower = message.toLowerCase();
    if (lower.indexOf("invalid login credentials") !== -1) return "E-mail ou mot de passe incorrect.";
    if (lower.indexOf("email not confirmed") !== -1) return "Confirme ton adresse e-mail avant de te connecter.";
    if (lower.indexOf("user already registered") !== -1) return "Un compte utilise déjà cette adresse e-mail. Connecte-toi plutôt.";
    if (lower.indexOf("provider is not enabled") !== -1 || lower.indexOf("unsupported provider") !== -1) {
      return "Cette option n’est pas encore activée dans la configuration KABAMAN.";
    }
    if (lower.indexOf("password should be at least") !== -1) return "Choisis un mot de passe d’au moins 8 caractères.";
    return message || "La connexion n’a pas abouti. Réessaie.";
  }

  function setMode(nextMode) {
    mode = nextMode;
    var registering = mode === "register";
    registerFields.hidden = !registering;
    authHeading.textContent = registering ? "Créer mon compte" : "Connexion";
    authIntro.textContent = registering
      ? "Crée ton espace client KABAMAN en quelques étapes."
      : "Connecte-toi ou crée ton compte pour accéder à ton espace client.";
    submitButton.textContent = registering ? "Créer mon compte avec e-mail" : "Se connecter avec e-mail";
    switchButton.textContent = registering ? "J’ai déjà un compte" : "Créer un compte avec e-mail";
    document.getElementById("auth-name").required = registering;
    document.getElementById("auth-confirm-password").required = registering;
    document.getElementById("auth-password").autocomplete = registering ? "new-password" : "current-password";
    setNote(authNote, "", false);
  }

  function toggleFormBusy(isBusy) {
    Array.from(authForm.elements).forEach(function (element) {
      element.disabled = isBusy;
    });
    document.querySelectorAll("[data-social-provider]").forEach(function (button) {
      button.disabled = isBusy;
    });
  }

  function accountOrders(email) {
    var host = document.getElementById("account-orders");
    host.replaceChildren();
    var orders = window.KABAMAN && window.KABAMAN.readOrders ? window.KABAMAN.readOrders() : [];
    var targetEmail = String(email || "").trim().toLowerCase();
    var matching = orders.filter(function (order) {
      return String(order && order.contact && order.contact.email || "").trim().toLowerCase() === targetEmail;
    });
    if (!matching.length) {
      var empty = document.createElement("p");
      empty.className = "search-hint";
      empty.textContent = "Aucune commande enregistrée sur cet appareil pour ce compte.";
      host.appendChild(empty);
      return;
    }
    matching.slice().reverse().forEach(function (order) {
      var card = document.createElement("article");
      card.className = "account-order-card";
      var title = document.createElement("h3");
      var service = order.services && order.services[0] && order.services[0].name || "Commande";
      title.textContent = service + " · " + order.ref;
      var status = document.createElement("p");
      status.textContent = "État : " + (order.status || "En attente");
      card.append(title, status);
      if (order.placedAt) {
        var date = new Date(order.placedAt);
        if (!isNaN(date.getTime())) {
          var when = document.createElement("p");
          when.textContent = "Créée le " + new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium" }).format(date);
          card.appendChild(when);
        }
      }
      host.appendChild(card);
    });
  }

  function paintSession(session) {
    var user = session && session.user;
    gate.hidden = Boolean(user);
    board.hidden = !user;
    if (!user) return;

    var metadata = user.user_metadata || {};
    var fullName = metadata.full_name || metadata.name || metadata.display_name || "";
    document.getElementById("account-heading").textContent = fullName ? "Bonjour " + fullName : "Mon compte";
    document.getElementById("profile-email").textContent = user.email || "";
    var nameInput = document.getElementById("profile-name");
    var phoneInput = document.getElementById("profile-phone");
    if (document.activeElement !== nameInput) nameInput.value = fullName;
    if (document.activeElement !== phoneInput) phoneInput.value = metadata.phone || "";
    accountOrders(user.email);
  }

  async function startSocial(provider) {
    if (!client) return;
    setNote(authNote, "", false);
    toggleFormBusy(true);
    var result = await client.auth.signInWithOAuth({
      provider: provider,
      options: { redirectTo: redirectUrl() }
    });
    if (result.error) {
      toggleFormBusy(false);
      setNote(authNote, friendlyError(result.error), true);
    }
  }

  async function submitAuth(event) {
    event.preventDefault();
    if (!client) return;
    setNote(authNote, "", false);
    var email = document.getElementById("auth-email").value.trim();
    var password = document.getElementById("auth-password").value;
    toggleFormBusy(true);
    try {
      if (mode === "register") {
        var confirmPassword = document.getElementById("auth-confirm-password").value;
        if (password !== confirmPassword) {
          toggleFormBusy(false);
          setNote(authNote, "Les deux mots de passe ne correspondent pas.", true);
          return;
        }
        var signup = await client.auth.signUp({
          email: email,
          password: password,
          options: {
            emailRedirectTo: redirectUrl(),
            data: {
              full_name: document.getElementById("auth-name").value.trim(),
              phone: document.getElementById("auth-phone").value.trim()
            }
          }
        });
        if (signup.error) throw signup.error;
        if (signup.data && signup.data.session) {
          setNote(authNote, "Compte créé. Bienvenue chez KABAMAN !", false);
        } else {
          setNote(authNote, "Compte créé. Vérifie ton e-mail pour confirmer l’inscription.", false);
        }
      } else {
        var login = await client.auth.signInWithPassword({ email: email, password: password });
        if (login.error) throw login.error;
      }
    } catch (error) {
      setNote(authNote, friendlyError(error), true);
    } finally {
      toggleFormBusy(false);
    }
  }

  async function saveProfile(event) {
    event.preventDefault();
    var name = document.getElementById("profile-name").value.trim();
    var phone = document.getElementById("profile-phone").value.trim();
    var note = document.getElementById("profile-note");
    if (!name) {
      setNote(note, "Indique ton nom.", true);
      return;
    }
    var button = document.querySelector("#profile-form button[type='submit']");
    button.disabled = true;
    try {
      var result = await client.auth.updateUser({ data: { full_name: name, phone: phone } });
      if (result.error) throw result.error;
      setNote(note, "Profil enregistré.", false);
      paintSession({ user: result.data.user });
    } catch (error) {
      setNote(note, friendlyError(error), true);
    } finally {
      button.disabled = false;
    }
  }

  switchButton.addEventListener("click", function () {
    setMode(mode === "login" ? "register" : "login");
  });
  authForm.addEventListener("submit", submitAuth);
  document.getElementById("profile-form").addEventListener("submit", saveProfile);
  document.getElementById("account-logout").addEventListener("click", async function () {
    var button = this;
    button.disabled = true;
    var result = await client.auth.signOut();
    button.disabled = false;
    if (result.error) setNote(document.getElementById("profile-note"), friendlyError(result.error), true);
  });
  document.querySelectorAll("[data-social-provider]").forEach(function (button) {
    button.addEventListener("click", function () {
      startSocial(button.getAttribute("data-social-provider")).catch(function (error) {
        toggleFormBusy(false);
        setNote(authNote, friendlyError(error), true);
      });
    });
  });

  setMode("login");
  var supabaseUrl = String(config.supabaseUrl || "").trim();
  var supabaseKey = String(config.supabaseAnonKey || "").trim();
  if (!supabaseUrl || !supabaseKey) {
    configNote.hidden = false;
    configNote.textContent = "La création de compte n’est pas encore activée. Le service de comptes KABAMAN doit être configuré avant de pouvoir s’inscrire.";
    toggleFormBusy(true);
    Array.from(authForm.elements).forEach(function (element) { element.disabled = true; });
    return;
  }

  try {
    client = createClient(supabaseUrl, supabaseKey);
  } catch (error) {
    configNote.hidden = false;
    configNote.textContent = "La configuration du service de comptes est invalide.";
    toggleFormBusy(true);
    Array.from(authForm.elements).forEach(function (element) { element.disabled = true; });
    return;
  }

  client.auth.onAuthStateChange(function (_event, session) {
    paintSession(session);
  });
  client.auth.getSession().then(function (result) {
    if (result.error) {
      setNote(authNote, friendlyError(result.error), true);
      return;
    }
    paintSession(result.data.session);
  });
})();
