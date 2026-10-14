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

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("input, select, textarea").forEach(field => {
    if (!field.labels?.length && !field.getAttribute("aria-label")) {
      field.setAttribute("aria-label", field.placeholder || field.name.replaceAll("_", " "));
    }
  });
  document.querySelectorAll("form[method='post']").forEach(form => {
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (form.action.endsWith("/delete") && !confirm("Delete this item? This cannot be undone.")) return;
      const button = event.submitter;
      if (button?.disabled) return;
      if (button) button.disabled = true;
      const feedback = document.createElement("p");
      feedback.setAttribute("role", "alert");
      try {
        const response = await fetch(form.action, { method: "POST", body: new URLSearchParams(new FormData(form)) });
        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.error || "Check the form values and try again.");
        }
        window.location.assign(response.url);
      } catch (error) {
        feedback.textContent = error.message || "Could not save. Try again.";
        form.querySelector("[role='alert']")?.remove();
        form.append(feedback);
        if (button) button.disabled = false;
      }
    });
  });
});
