(() => {
  const configSelect = document.getElementById("config-select");
  const addBtn = document.getElementById("add-config-btn");
  const editBtn = document.getElementById("edit-config-btn");
  const continueBtn = document.getElementById("continue-btn");

  const configModalEl = document.getElementById("configModal");
  const configModalLabel = document.getElementById("configModalLabel");
  const configName = document.getElementById("config-name");
  const sourceSite = document.getElementById("source-site");
  const targetSite = document.getElementById("target-site");
  const notes = document.getElementById("notes");
  const saveConfigBtn = document.getElementById("save-config-btn");

  const workflowSection = document.getElementById("workflow-section");
  const configurationSection = document.getElementById("configuration-section");
  const checkBtn = document.getElementById("check-btn");
  const runBtn = document.getElementById("run-btn");
  const cancelBtn = document.getElementById("cancel-btn");
  const componentsBody = document.getElementById("components-body");

  const componentRows = [...componentsBody.querySelectorAll("tr")];
  let modalMode = "add";

  const setWorkflowActive = (active) => {
    workflowSection.classList.toggle("inactive-section", !active);
    workflowSection.setAttribute("aria-disabled", active ? "false" : "true");

    configurationSection.classList.toggle("section-locked", active);

    checkBtn.disabled = !active;
    runBtn.disabled = !active;
    cancelBtn.disabled = !active;
  };

  const updateRowStatuses = (state) => {
    componentRows.forEach((row) => {
      const badge = row.querySelector(".badge");
      if (!badge) return;

      badge.className = "badge";

      if (state === "pending") {
        badge.classList.add("text-bg-secondary");
        badge.textContent = "Pending";
      }

      if (state === "checking") {
        badge.classList.add("text-bg-warning");
        badge.textContent = "Checking";
      }

      if (state === "ready") {
        badge.classList.add("text-bg-success");
        badge.textContent = "Ready";
      }

      if (state === "running") {
        badge.classList.add("text-bg-primary");
        badge.textContent = "Running";
      }

      if (state === "stopped") {
        badge.classList.add("text-bg-danger");
        badge.textContent = "Stopped";
      }
    });
  };

  addBtn.addEventListener("click", () => {
    modalMode = "add";
    configModalLabel.textContent = "Add New Configuration";
    configName.value = "";
    sourceSite.value = "";
    targetSite.value = "";
    notes.value = "";
  });

  editBtn.addEventListener("click", () => {
    modalMode = "edit";
    configModalLabel.textContent = "Edit Configuration";

    const selectedLabel = configSelect.options[configSelect.selectedIndex]?.text || "";
    configName.value = selectedLabel;
    sourceSite.value = "Site A";
    targetSite.value = "Site B";
    notes.value = "Placeholder settings for selected profile.";
  });

  saveConfigBtn.addEventListener("click", () => {
    const name = configName.value.trim();
    if (!name) {
      configName.focus();
      return;
    }

    if (modalMode === "add") {
      const option = document.createElement("option");
      option.value = name.toLowerCase().replace(/\s+/g, "-");
      option.textContent = name;
      configSelect.appendChild(option);
      configSelect.value = option.value;
    } else {
      configSelect.options[configSelect.selectedIndex].text = name;
    }

    bootstrap.Modal.getInstance(configModalEl)?.hide();
  });

  continueBtn.addEventListener("click", () => {
    setWorkflowActive(true);
    updateRowStatuses("pending");
  });

  checkBtn.addEventListener("click", () => {
    updateRowStatuses("checking");
    window.setTimeout(() => updateRowStatuses("ready"), 700);
  });

  runBtn.addEventListener("click", () => {
    updateRowStatuses("running");

    const selectedName = configSelect.options[configSelect.selectedIndex]?.text || "Unknown Configuration";
    const statusUrl = `/workflow-status?config=${encodeURIComponent(selectedName)}&status=${encodeURIComponent("Running")}`;

    window.open(statusUrl, "_blank", "noopener,noreferrer");
    setWorkflowActive(false);
  });

  cancelBtn.addEventListener("click", () => {
    updateRowStatuses("stopped");
    setWorkflowActive(false);
  });

  setWorkflowActive(false);
})();
