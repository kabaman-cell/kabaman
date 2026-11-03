const nav = document.querySelector(".nav");
const menuBtn = document.querySelector(".menu-btn");
const form = document.getElementById("quote-form");
const status = document.getElementById("form-status");

function closeMenu() {
  nav?.classList.remove("open");
  menuBtn?.setAttribute("aria-expanded", "false");
  menuBtn?.setAttribute("aria-label", "Open menu");
}

menuBtn?.addEventListener("click", () => {
  const open = nav.classList.toggle("open");
  menuBtn.setAttribute("aria-expanded", String(open));
  menuBtn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
});

document.querySelectorAll(".nav-links a, .nav-import, .cart-link").forEach((link) => {
  link.addEventListener("click", () => {
    closeMenu();
  });
});

document.addEventListener("click", (event) => {
  if (!nav?.classList.contains("open")) return;
  if (nav.contains(event.target)) return;
  closeMenu();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && nav?.classList.contains("open")) {
    closeMenu();
    menuBtn?.focus();
  }
});

form?.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!form.checkValidity()) {
    status.textContent = "Please complete all fields with a valid email.";
    status.classList.add("is-error");
    return;
  }
  form.reset();
  status.classList.remove("is-error");
  status.textContent = "Thank you. Your request has been received.";
});

window.KABAMAN?.paintCartCount();
