const nav = document.querySelector(".nav");
const toggle = document.querySelector(".nav-toggle");
const form = document.getElementById("quote-form");
const statusEl = form?.querySelector(".form-status");

toggle?.addEventListener("click", () => {
  const open = nav.classList.toggle("open");
  toggle.setAttribute("aria-expanded", String(open));
});

document.querySelectorAll(".nav-links a, .nav-import, .cart-link").forEach((link) => {
  link.addEventListener("click", () => {
    nav.classList.remove("open");
    toggle?.setAttribute("aria-expanded", "false");
  });
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && nav?.classList.contains("open")) {
    nav.classList.remove("open");
    toggle?.setAttribute("aria-expanded", "false");
    toggle?.focus();
  }
});

form?.addEventListener("submit", (event) => {
  event.preventDefault();
  statusEl.classList.remove("error");

  if (!form.checkValidity()) {
    statusEl.classList.add("error");
    statusEl.textContent = "Please fill in your name, email, and request.";
    form.reportValidity();
    return;
  }

  statusEl.textContent = "Thank you. Your quote request has been noted. Add an email later to send these for real.";
  form.reset();
});

window.KABAMAN?.paintCartCount();
