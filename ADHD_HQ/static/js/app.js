function populateSubcats(pillarSel, subcatSel, subcats, currentValue=null) {
  const pillar = pillarSel.value;
  const list = subcats[pillar] || [];
  subcatSel.innerHTML = "";
  list.forEach(sc => {
    const opt = document.createElement("option");
    opt.value = sc;
    opt.textContent = sc;
    subcatSel.appendChild(opt);
  });
  if (currentValue && list.includes(currentValue)) {
    subcatSel.value = currentValue;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const subcats = window.TASKHQ_SUBCATS || null;

  // Add form
  const pillarSelect = document.getElementById("pillarSelect");
  const subcatSelect = document.getElementById("subcatSelect");
  if (pillarSelect && subcatSelect && subcats) {
    populateSubcats(pillarSelect, subcatSelect, subcats);
    pillarSelect.addEventListener("change", () => populateSubcats(pillarSelect, subcatSelect, subcats));
  }

  // Edit rows - populate subcategories for edit forms
  document.querySelectorAll(".subcatEdit").forEach(subcatSelect => {
    if (!subcats) return;
    const current = subcatSelect.getAttribute("data-current");
    // For School tasks, always use School pillar
    const pillar = "School";
    const list = subcats[pillar] || [];
    subcatSelect.innerHTML = "";
    list.forEach(sc => {
      const opt = document.createElement("option");
      opt.value = sc;
      opt.textContent = sc;
      subcatSelect.appendChild(opt);
    });
    if (current && list.includes(current)) {
      subcatSelect.value = current;
    }
  });
});
