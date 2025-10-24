document.addEventListener("DOMContentLoaded", function () {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("overlay");
  const toggle = document.getElementById("sidebarToggle");
  const main = document.getElementById("mainContent");
  const sidebarLinks = sidebar ? sidebar.querySelectorAll("a") : [];

  function openSidebar() {
    sidebar.classList.add("open");
    overlay.classList.add("visible");
    document.body.classList.add("sidebar-open");
  }

  function closeSidebar() {
    sidebar.classList.remove("open");
    overlay.classList.remove("visible");
    document.body.classList.remove("sidebar-open");
  }

  if (toggle) {
    toggle.addEventListener("click", function () {
      if (sidebar.classList.contains("open")) closeSidebar();
      else openSidebar();
    });
  }

  if (overlay) {
    overlay.addEventListener("click", closeSidebar);
  }

  sidebarLinks.forEach(link => {
    link.addEventListener("click", closeSidebar);
  });

  if (main) {
    main.addEventListener("click", function () {
      if (sidebar.classList.contains("open")) closeSidebar();
    });
  }
});
