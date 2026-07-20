// Class-based dark mode shared by all pages; persisted per browser.
const themeBtn = document.getElementById("theme");
function applyTheme(dark) {
  document.documentElement.classList.toggle("dark", dark);
  themeBtn.innerHTML = dark ? "&#9789;" : "&#9788;";
}
applyTheme(localStorage.theme === "dark" ||
  (!localStorage.theme && matchMedia("(prefers-color-scheme: dark)").matches));
themeBtn.onclick = () => {
  const dark = !document.documentElement.classList.contains("dark");
  localStorage.theme = dark ? "dark" : "light";
  applyTheme(dark);
};

const INR = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

// Highlight the current page in the shared nav.
document.querySelectorAll(".nav-link").forEach(a => {
  const href = a.getAttribute("href");
  const here = href === "/" ? ["/", "/index.html"] : [href];
  if (here.includes(location.pathname)) a.classList.add("active");
});
