(() => {
  const configSelect = document.getElementById("config-select");
  const addBtn = document.getElementById("add-config-btn");
  const editBtn = document.getElementById("edit-config-btn");
  const continueBtn = document.getElementById("continue-btn");

  const configModalEl = document.getElementById("configModal");
  const configModalLabel = document.getElementById("configModalLabel");
  const configName = document.getElementById("config-name");
  const saveConfigBtn = document.getElementById("save-config-btn");
  const dataSourceHelpBtn = document.getElementById("data-source-help-btn");
  const dataSourceHelpModalEl = document.getElementById("dataSourceHelpModal");

  const dataSourceLive = document.getElementById("data-source-live");
  const dataSourceFiles = document.getElementById("data-source-files");
  const liveDaqPanel = document.getElementById("live-daq-panel");
  const filesPanel = document.getElementById("files-panel");
  const daqSystemSelect = document.getElementById("daq-system");
  const codaSettings = document.getElementById("coda-settings");
  const daqUnsupportedMessage = document.getElementById("daq-unsupported-message");
  const unsupportedSystemName = document.getElementById("unsupported-system-name");

  const etHost = document.getElementById("et-host");
  const etPort = document.getElementById("et-port");
  const stationName = document.getElementById("station-name");
  const blocking = document.getElementById("blocking");
  const dataIdLabel = document.getElementById("data-id-label");
  const filesPath = document.getElementById("files-path");
  const filesRegex = document.getElementById("files-regex");
  const filesLoop = document.getElementById("files-loop");
  const browseBtn = document.getElementById("browse-btn");

  const filesystemModalEl = document.getElementById("filesystemModal");
  const filesystemModalLabel = document.getElementById("filesystemModalLabel");
  const fsCurrentPath = document.getElementById("fs-current-path");
  const fsItems = document.getElementById("fs-items");
  const fsError = document.getElementById("fs-error");
  const fsHomeBtn = document.getElementById("fs-home-btn");
  const fsUpBtn = document.getElementById("fs-up-btn");
  const fsRefreshBtn = document.getElementById("fs-refresh-btn");
  const fsSelectBtn = document.getElementById("fs-select-btn");
  const fsSelectionSummary = document.getElementById("fs-selection-summary");

  const workflowSection = document.getElementById("workflow-section");
  const configurationSection = document.getElementById("configuration-section");
  const checkBtn = document.getElementById("check-btn");
  const runBtn = document.getElementById("run-btn");
  const cancelBtn = document.getElementById("cancel-btn");
  const componentsBody = document.getElementById("components-body");

  const componentRows = [...componentsBody.querySelectorAll("tr")];
  let modalMode = "add";
  let fsCurrentDir = "";
  let fsParentDir = null;
  let fsSelectedFiles = new Set();
  let baselineConfigJson = "";

  const setSelectOptions = (items, selectedFile = "") => {
    configSelect.innerHTML = "";

    if (!items.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No saved configurations";
      configSelect.appendChild(option);
      configSelect.disabled = true;
      editBtn.disabled = true;
      continueBtn.disabled = true;
      return;
    }

    configSelect.disabled = false;
    editBtn.disabled = false;
    continueBtn.disabled = false;

    items.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.file;
      option.textContent = item.name;
      option.dataset.file = item.file;
      configSelect.appendChild(option);
    });

    if (selectedFile) {
      const match = [...configSelect.options].find((opt) => opt.dataset.file === selectedFile);
      if (match) {
        configSelect.value = match.value;
      }
    }
  };

  const loadConfigList = async (selectedFile = "") => {
    try {
      const response = await fetch("/api/config/list");
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Unable to load configurations");
      }

      setSelectOptions(payload.items || [], selectedFile);
    } catch {
      setSelectOptions([], "");
    }
  };

  const filesystemModal = new bootstrap.Modal(filesystemModalEl);
  const dataSourceHelpModal = new bootstrap.Modal(dataSourceHelpModalEl);

  const buildConfigurationPayload = () => {
    const dataSourceMode = dataSourceFiles.checked ? "files" : "live";
    const selectedSystemLabel = daqSystemSelect.options[daqSystemSelect.selectedIndex]?.text || "";
    const selectedFiles = filesRegex.value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

    return {
      name: configName.value.trim(),
      dataSource: {
        mode: dataSourceMode,
        live: {
          system: selectedSystemLabel,
          etHost: etHost.value.trim(),
          port: etPort.value.trim(),
          stationName: stationName.value.trim(),
          blocking: blocking.checked,
        },
        files: {
          path: filesPath.value.trim(),
          files: selectedFiles,
          loop: filesLoop.checked,
          dataId: dataIdLabel.textContent.trim(),
        },
      },
    };
  };

  const updateSaveButtonState = () => {
    const currentJson = JSON.stringify(buildConfigurationPayload());
    saveConfigBtn.disabled = !baselineConfigJson || currentJson === baselineConfigJson;
  };

  const setBaselineFromCurrent = () => {
    baselineConfigJson = JSON.stringify(buildConfigurationPayload());
    updateSaveButtonState();
  };

  const escapeHtml = (value) =>
    value
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  const updateFsSelectionSummary = () => {
    const count = fsSelectedFiles.size;
    if (count) {
      fsSelectionSummary.textContent = `${count} file${count === 1 ? "" : "s"} selected`;
      return;
    }

    fsSelectionSummary.textContent = fsCurrentDir
      ? `No files selected. Select will choose folder: ${fsCurrentDir}`
      : "No files selected";
  };

  const renderFsItems = (entries) => {
    if (!entries.length) {
      fsItems.innerHTML = '<li class="list-group-item text-secondary">No entries in this folder.</li>';
      updateFsSelectionSummary();
      return;
    }

    const rows = entries
      .map((entry) => {
        const icon = entry.isDirectory ? "📁" : "📄";
        const safeName = escapeHtml(entry.name);
        const safePath = escapeHtml(entry.path);

        if (entry.isDirectory) {
          return `<li class="list-group-item d-flex align-items-center justify-content-between gap-2">
              <button type="button" class="btn btn-link p-0 text-decoration-none fs-open-dir" data-path="${safePath}">
                ${icon} ${safeName}
              </button>
              <span class="badge text-bg-light border">folder</span>
            </li>`;
        }

        const checked = fsSelectedFiles.has(entry.name) ? "checked" : "";
        return `<li class="list-group-item d-flex align-items-center gap-2">
            <input class="form-check-input mt-0 fs-file-check" type="checkbox" data-name="${safeName}" ${checked} />
            <span>${icon} ${safeName}</span>
          </li>`;
      })
      .join("");

    fsItems.innerHTML = rows;
    updateFsSelectionSummary();
  };

  const showFsError = (message) => {
    fsError.textContent = message;
    fsError.classList.remove("d-none");
  };

  const clearFsError = () => {
    fsError.textContent = "";
    fsError.classList.add("d-none");
  };

  const loadDirectory = async (path = "") => {
    clearFsError();
    fsItems.innerHTML = '<li class="list-group-item text-secondary">Loading...</li>';

    try {
      const query = path ? `?path=${encodeURIComponent(path)}` : "";
      const response = await fetch(`/api/fs/list${query}`);
      const payload = await response.json();

      if (!response.ok) {
        throw new Error(payload.error || "Unable to browse filesystem");
      }

      fsCurrentDir = payload.path;
      fsParentDir = payload.parent;
      fsCurrentPath.textContent = payload.path;
      fsUpBtn.disabled = !payload.parent;

      fsSelectedFiles.clear();

      renderFsItems(payload.entries || []);
    } catch (error) {
      fsItems.innerHTML = "";
      showFsError(error.message || "Unable to browse filesystem");
    }
  };

  const openFilesystemModal = async () => {
    fsSelectedFiles.clear();
    filesystemModalLabel.textContent = "Choose Files or Folder";
    fsSelectBtn.textContent = "Select";
    updateFsSelectionSummary();

    let startPath = filesPath.value.trim();
    if (!startPath.startsWith("/")) {
      startPath = "";
    }

    await loadDirectory(startPath);
    filesystemModal.show();
  };

  const setDataSourcePanel = () => {
    const filesSelected = dataSourceFiles.checked;
    liveDaqPanel.classList.toggle("d-none", filesSelected);
    filesPanel.classList.toggle("d-none", !filesSelected);
  };

  const setDaqSystemPanel = () => {
    const selectedSystem = daqSystemSelect.value;
    const isCoda = selectedSystem === "coda-et";

    codaSettings.classList.toggle("d-none", !isCoda);
    daqUnsupportedMessage.classList.toggle("d-none", isCoda);

    if (!isCoda) {
      const systemLabel = selectedSystem === "ddaq" ? "dDAQ" : "GLRS";
      unsupportedSystemName.textContent = systemLabel;
    }
  };

  const resetModalFields = () => {
    dataSourceLive.checked = true;
    dataSourceFiles.checked = false;
    daqSystemSelect.value = "coda-et";
    etHost.value = "";
    etPort.value = "";
    stationName.value = "";
    blocking.checked = false;

    dataIdLabel.textContent = "-";
    filesPath.value = "";
    filesRegex.value = "";
    filesLoop.checked = false;

    setDataSourcePanel();
    setDaqSystemPanel();
  };

  const applyConfigToForm = (config = {}) => {
    const dataSource = config.dataSource || {};
    const live = dataSource.live || {};
    const files = dataSource.files || {};

    configName.value = config.name || "";

    const mode = dataSource.mode === "files" ? "files" : "live";
    dataSourceFiles.checked = mode === "files";
    dataSourceLive.checked = mode !== "files";

    const systemMap = {
      "CODA (ET)": "coda-et",
      GLRS: "glrs",
      dDAQ: "ddaq",
    };

    daqSystemSelect.value = systemMap[live.system] || "coda-et";
    etHost.value = live.etHost || "";
    etPort.value = live.port || "";
    stationName.value = live.stationName || "";
    blocking.checked = Boolean(live.blocking);

    filesPath.value = files.path || "";
    filesRegex.value = Array.isArray(files.files) ? files.files.join(", ") : "";
    filesLoop.checked = Boolean(files.loop);
    dataIdLabel.textContent = files.dataId || "-";

    setDataSourcePanel();
    setDaqSystemPanel();
  };

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
    resetModalFields();
    setBaselineFromCurrent();
  });

  editBtn.addEventListener("click", async () => {
    modalMode = "edit";
    configModalLabel.textContent = "Edit Configuration";

    const selectedOption = configSelect.options[configSelect.selectedIndex];
    const selectedFile = selectedOption?.dataset?.file || selectedOption?.value || "";

    if (!selectedFile) {
      resetModalFields();
      setBaselineFromCurrent();
      return;
    }

    try {
      const response = await fetch(`/api/config/load?file=${encodeURIComponent(selectedFile)}`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Unable to load configuration");
      }

      applyConfigToForm(payload.config || {});
      setBaselineFromCurrent();
    } catch (error) {
      window.alert(error.message || "Unable to load configuration");
      resetModalFields();
      configName.value = selectedOption?.text || "";
      setBaselineFromCurrent();
    }
  });

  saveConfigBtn.addEventListener("click", async () => {
    const name = configName.value.trim();
    if (!name) {
      configName.focus();
      return;
    }

    const payload = buildConfigurationPayload();

    try {
      const response = await fetch("/api/config/save", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || "Unable to save configuration");
      }

      await loadConfigList(result.file || "");
      baselineConfigJson = JSON.stringify(payload);
      updateSaveButtonState();
    } catch (error) {
      window.alert(error.message || "Unable to save configuration");
      return;
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

  dataSourceLive.addEventListener("change", setDataSourcePanel);
  dataSourceFiles.addEventListener("change", setDataSourcePanel);
  daqSystemSelect.addEventListener("change", setDaqSystemPanel);

  [
    configName,
    dataSourceLive,
    dataSourceFiles,
    daqSystemSelect,
    etHost,
    etPort,
    stationName,
    blocking,
    filesPath,
    filesRegex,
    filesLoop,
  ].forEach((element) => {
    element.addEventListener("input", updateSaveButtonState);
    element.addEventListener("change", updateSaveButtonState);
  });

  browseBtn.addEventListener("click", () => {
    openFilesystemModal();
  });

  dataSourceHelpBtn.addEventListener("click", () => {
    dataSourceHelpModal.show();
  });

  fsHomeBtn.addEventListener("click", () => {
    loadDirectory("");
  });

  fsUpBtn.addEventListener("click", () => {
    if (!fsParentDir) return;
    loadDirectory(fsParentDir);
  });

  fsRefreshBtn.addEventListener("click", () => {
    loadDirectory(fsCurrentDir);
  });

  fsItems.addEventListener("click", (event) => {
    const openDirBtn = event.target.closest(".fs-open-dir");
    if (openDirBtn) {
      const targetPath = openDirBtn.getAttribute("data-path") || "";
      loadDirectory(targetPath);
      return;
    }

    const fileCheckbox = event.target.closest(".fs-file-check");
    if (!fileCheckbox) return;

    const fileName = fileCheckbox.getAttribute("data-name") || "";
    if (!fileName) return;

    if (fileCheckbox.checked) {
      fsSelectedFiles.add(fileName);
    } else {
      fsSelectedFiles.delete(fileName);
    }

    updateFsSelectionSummary();
  });

  fsSelectBtn.addEventListener("click", () => {
    const selected = [...fsSelectedFiles];

    if (!selected.length) {
      filesPath.value = fsCurrentDir;
      filesRegex.value = "*";
      filesystemModal.hide();
      updateSaveButtonState();
      return;
    }

    filesPath.value = fsCurrentDir;
    filesRegex.value = selected.join(", ");
    filesystemModal.hide();
    updateSaveButtonState();
  });

  loadConfigList();
  resetModalFields();
  setBaselineFromCurrent();
  setWorkflowActive(false);
})();
