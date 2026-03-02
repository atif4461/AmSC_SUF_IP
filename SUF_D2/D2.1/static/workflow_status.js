(() => {
  const bootstrap = window.WORKFLOW_STATUS_BOOTSTRAP || {};
  const canvas = document.getElementById("workflow-monitor-canvas");
  const badge = document.getElementById("monitor-connection-badge");
  const statThroughput = document.getElementById("stat-throughput");
  const statJobs = document.getElementById("stat-jobs");
  const statWorkers = document.getElementById("stat-workers");
  const statUpdated = document.getElementById("stat-updated");
  const workflowStateBadge = document.getElementById("workflow-state-badge");
  const stopWorkflowBtn = document.getElementById("stop-workflow-btn");
  const workflowSummaryBody = document.getElementById("workflow-summary-body");
  const workflowSummaryModalEl = document.getElementById("workflowSummaryModal");

  if (!canvas) {
    return;
  }

  const svg = d3.select(canvas).append("svg").attr("class", "workflow-monitor-svg");
  const facilityLayer = svg.append("g").attr("class", "facility-layer");
  const linkLayer = svg.append("g").attr("class", "link-layer");
  const nodeLayer = svg.append("g").attr("class", "node-layer");

  let currentSnapshot = bootstrap.snapshot || null;
  let currentConfig = bootstrap.config || {};
  let ws = null;
  let pollTimer = null;
  let workflowStopped = !Boolean(bootstrap.workflowRunning);

  const workflowSummaryModal =
    workflowSummaryModalEl && window.bootstrap ? new window.bootstrap.Modal(workflowSummaryModalEl) : null;

  const setConnectionBadge = (state, text) => {
    badge.classList.remove("text-bg-secondary", "text-bg-success", "text-bg-warning", "text-bg-danger");
    if (state === "connected") {
      badge.classList.add("text-bg-success");
    } else if (state === "polling") {
      badge.classList.add("text-bg-warning");
    } else if (state === "error") {
      badge.classList.add("text-bg-danger");
    } else {
      badge.classList.add("text-bg-secondary");
    }
    badge.textContent = text;
  };

  const setHeaderBadgesVisibility = () => {
    if (workflowStateBadge) {
      workflowStateBadge.classList.toggle("d-none", workflowStopped);
    }
    if (badge) {
      badge.classList.toggle("d-none", workflowStopped);
    }
  };

  const applyWorkflowState = (workflowState, runningFlag) => {
    const normalized = String(workflowState || "").toLowerCase();
    if (normalized === "running" || normalized === "idle" || typeof runningFlag === "boolean") {
      workflowStopped = typeof runningFlag === "boolean" ? !runningFlag : normalized !== "running";
      setWorkflowToggleButton();
      setHeaderBadgesVisibility();
    }
  };

  const setWorkflowToggleButton = () => {
    if (!stopWorkflowBtn) return;

    stopWorkflowBtn.classList.remove("btn-danger", "btn-success", "btn-outline-danger", "btn-outline-success");
    if (workflowStopped) {
      stopWorkflowBtn.classList.add("btn-success");
      stopWorkflowBtn.textContent = "Start Workflow";
    } else {
      stopWorkflowBtn.classList.add("btn-danger");
      stopWorkflowBtn.textContent = "Stop Workflow";
    }
  };

  const formatUpdated = (ms) => {
    if (!ms) return "--";
    const d = new Date(ms);
    return d.toLocaleTimeString();
  };

  const buildLayout = (snapshot, width, height) => {
    const topology = snapshot?.topology || {};
    const components = topology.components || [];
    const links = topology.links || [];
    const workerNodes = components.filter((c) => c.group === "worker");

    const map = new Map();
    const centerY = height * 0.46;

    const sourceRegion = { x: width * 0.03, y: height * 0.08, w: Math.max(120, width * 0.216 - 20), h: height * 0.84, label: "Data Source: BNL" };
    const transportRegion = {
      x: width * 0.28 - 20,
      y: height * 0.08,
      w: width * 0.18 + 20,
      h: height * 0.84,
      label: "Data Transport: ESnet",
    };
    const hpcLocation = String(currentConfig?.hpcCompute?.location || "HPC").trim() || "HPC";
    const hpcRegion = {
      x: width * 0.48,
      y: height * 0.08,
      w: width * 0.49,
      h: height * 0.84,
      label: `HPC: ${hpcLocation}`,
    };

    const source = components.find((c) => c.id === "source");
    if (source) map.set(source.id, { ...source, x: sourceRegion.x + sourceRegion.w * 0.46, y: height * 0.28 });

    const ejfat = components.find((c) => c.id === "ejfat");
    if (ejfat) map.set(ejfat.id, { ...ejfat, x: transportRegion.x + transportRegion.w * 0.5, y: centerY });

    const workerStartX = hpcRegion.x + hpcRegion.w * 0.12;
    const workerEndX = hpcRegion.x + hpcRegion.w * 0.58;
    const workerCols = Math.max(2, Math.min(4, Math.ceil(Math.sqrt(workerNodes.length))));
    const workerRows = Math.max(1, Math.ceil(workerNodes.length / workerCols));
    const workerExtraSpacing = 0;
    const xAvailable = workerEndX - workerStartX - workerExtraSpacing * Math.max(0, workerCols - 1);
    const xGap = workerCols > 1 ? xAvailable / (workerCols - 1) : 0;
    const yStart = hpcRegion.y + hpcRegion.h * 0.12;
    const yEnd = hpcRegion.y + hpcRegion.h * 0.80;
    const yAvailable = yEnd - yStart - workerExtraSpacing * Math.max(0, workerRows - 1);
    const yGap = workerRows > 1 ? yAvailable / (workerRows - 1) : 0;

    workerNodes.forEach((node, i) => {
      const col = i % workerCols;
      const row = Math.floor(i / workerCols);
      map.set(node.id, {
        ...node,
        x: workerStartX + (xGap + workerExtraSpacing) * col,
        y: yStart + (yGap + workerExtraSpacing) * row,
      });
    });

    const aggregator = components.find((c) => c.id === "aggregator");
    if (aggregator) map.set(aggregator.id, { ...aggregator, x: hpcRegion.x + hpcRegion.w * 0.78 + 30, y: hpcRegion.y + hpcRegion.h * 0.28 });

    const plotter = components.find((c) => c.id === "plotter");
    if (plotter) map.set(plotter.id, { ...plotter, x: hpcRegion.x + hpcRegion.w * 0.78 + 30, y: hpcRegion.y + hpcRegion.h * 0.82 });

    const viewer = components.find((c) => c.id === "viewer");
    if (viewer) map.set(viewer.id, { ...viewer, x: sourceRegion.x + sourceRegion.w * 0.52, y: sourceRegion.y + sourceRegion.h * 0.82 });

    return {
      facilities: [sourceRegion, transportRegion, hpcRegion],
      nodes: [...map.values()],
      links: links
        .map((l) => {
          const sourceNode = map.get(l.source);
          const targetNode = map.get(l.target);
          if (!sourceNode || !targetNode) return null;
          return { ...l, sourceNode, targetNode };
        })
        .filter(Boolean),
    };
  };

  const nodeDetails = (node, stats) => {
    if (!stats) return ["no stats"];
    if (node.group === "source") return [`${stats.framesPerSec || stats.eventsPerSec || 0} evt/s`, `${stats.rateGbps || 0} Gbps`];
    if (node.group === "transport") return [`${stats.outStreams || 0} streams`, `${stats.splitRateGbps || 0} Gbps/stream`];
    if (node.group === "worker") return [`${stats.framesPerSec || stats.eventsPerSec || 0} evt/s`, `${stats.inferenceMs || 0} ms infer`];
    if (node.group === "aggregate") return [`${stats.histogramsPerSec || 0} hist/s`, `Q=${stats.queueDepth || 0}`];
    if (node.group === "plot") return [`${stats.imagesPerMin || 0} img/min`, `${stats.lastRenderMs || 0} ms`];
    if (node.group === "monitor") return [`${stats.latestImageAgeSec || 0} s age`, `${stats.viewers || 0} viewers`];
    return ["--"];
  };

  const nodeBoxSize = (node) => {
    if (node.group === "worker" || node.group === "aggregate" || node.group === "plot") {
      return { width: 128, height: 58 };
    }
    return { width: 158, height: 64 };
  };

  const linkPath = (link) => {
    const sx = link.sourceNode.x;
    const sy = link.sourceNode.y;
    const tx = link.targetNode.x;
    const ty = link.targetNode.y;

    if (link.source === "plotter" && link.target === "viewer") {
      const c1x = sx;
      const c1y = sy + 120;
      const c2x = tx + 150;
      const c2y = ty + 70;
      return `M ${sx} ${sy} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${tx} ${ty}`;
    }

    return `M ${sx} ${sy} L ${tx} ${ty}`;
  };

  const render = (snapshot) => {
    currentSnapshot = snapshot;
    const bounds = canvas.getBoundingClientRect();
    const width = Math.max(900, Math.floor(bounds.width));
    const height = Math.max(520, Math.floor(window.innerHeight * 0.62));

    svg.attr("viewBox", `0 0 ${width} ${height}`).attr("width", "100%").attr("height", height);
    svg.classed("workflow-stopped", workflowStopped);

    const { facilities, nodes, links } = buildLayout(snapshot, width, height);
    const stats = snapshot?.nodeStats || {};
    const linkStats = snapshot?.linkStats || {};
    const workerCount = Number(snapshot?.topology?.workerCount || 1);
    const downstreamWidth = 2.4;

    const facilitySel = facilityLayer.selectAll("g.facility").data(facilities, (d) => d.label);
    const facilityEnter = facilitySel.join(
      (enter) => {
        const g = enter.append("g").attr("class", "facility");
        g.append("rect").attr("class", "facility-box").attr("rx", 14).attr("ry", 14);
        g.append("text").attr("class", "facility-label");
        return g;
      },
      (update) => update,
      (exit) => exit.remove()
    );

    facilityEnter.select("rect").attr("x", (d) => d.x).attr("y", (d) => d.y).attr("width", (d) => d.w).attr("height", (d) => d.h);
    facilityEnter
      .select("text")
      .attr("x", (d) => d.x + 10)
      .attr("y", (d) => d.y + 22)
      .text((d) => d.label);

    const toNum = (value) => {
      const n = Number(value);
      return Number.isFinite(n) ? n : 0;
    };

    const nodeFlowActive = (nodeId) => {
      const ns = stats[nodeId] || {};
      if (nodeId === "source") return toNum(ns.framesPerSec ?? ns.eventsPerSec) > 0;
      if (nodeId === "ejfat") return toNum(ns.splitRateGbps) > 0;
      if (String(nodeId).startsWith("worker-")) return toNum(ns.framesPerSec ?? ns.eventsPerSec) > 0;
      if (nodeId === "aggregator") return toNum(ns.histogramsPerSec) > 0;
      if (nodeId === "plotter") return toNum(ns.imagesPerMin) > 0;
      if (nodeId === "viewer") return toNum(ns.latestImageAgeSec) > 0;
      return false;
    };

    const linkIsActive = (link) => {
      if (workflowStopped) {
        return false;
      }

      const linkKey = `${link.source}->${link.target}`;
      if (Object.prototype.hasOwnProperty.call(linkStats, linkKey)) {
        const linkInfo = linkStats[linkKey] || {};
        if (typeof linkInfo.active === "boolean") {
          return linkInfo.active;
        }
      }

      // For source->EJFAT, activation is gated by source flow.
      if (link.source === "source" && link.target === "ejfat") {
        return nodeFlowActive("source");
      }

      // For EJFAT->worker, each worker activates independently from proxy delays.
      if (link.source === "ejfat" && String(link.target).startsWith("worker-")) {
        return nodeFlowActive(link.target);
      }

      // For direct source->worker topology, use worker activation.
      if (link.source === "source" && String(link.target).startsWith("worker-")) {
        return nodeFlowActive(link.target);
      }

      // Downstream links activate with their source node.
      return nodeFlowActive(link.source);
    };

    const linkSel = linkLayer.selectAll("path.flow-link").data(links, (d) => `${d.source}->${d.target}`);
    linkSel
      .join((enter) => enter.append("path").attr("class", "flow-link").attr("fill", "none"), (update) => update, (exit) => exit.remove())
      .attr("d", (d) => linkPath(d))
      .style("stroke-width", (d) => {
        if (!linkIsActive(d)) {
          return 2;
        }
        if (d.source === "source" && d.target === "ejfat") {
          return downstreamWidth * (workerCount / 2);
        }
        return downstreamWidth;
      })
      .classed("flow-link-inactive", (d) => !linkIsActive(d))
      .classed("flow-link-meta", (d) => d.meta === "contains");

    const nodeSel = nodeLayer.selectAll("g.wf-node").data(nodes, (d) => d.id);
    const nodeEnter = nodeSel.join(
      (enter) => {
        const g = enter.append("g").attr("class", "wf-node");
        g.append("rect").attr("rx", 10).attr("ry", 10);
        g.append("text").attr("class", "wf-node-title").attr("text-anchor", "middle").attr("y", -10);
        g.append("text").attr("class", "wf-node-metric").attr("text-anchor", "middle").attr("y", 8);
        g.append("text").attr("class", "wf-node-metric").attr("text-anchor", "middle").attr("y", 23);
        return g;
      },
      (update) => update,
      (exit) => exit.remove()
    );

    nodeEnter.attr("transform", (d) => `translate(${d.x},${d.y})`);
    nodeEnter
      .select("rect")
      .attr("class", (d) => `wf-node-box wf-node-${d.group}`)
      .attr("width", (d) => nodeBoxSize(d).width)
      .attr("height", (d) => nodeBoxSize(d).height)
      .attr("x", (d) => -nodeBoxSize(d).width / 2)
      .attr("y", (d) => -nodeBoxSize(d).height / 2);
    nodeEnter.select("text.wf-node-title").text((d) => d.label);

    nodeEnter.selectAll("text.wf-node-metric").each(function (d, i) {
      if (workflowStopped) {
        d3.select(this).text(i === 0 ? "inactive" : "");
        return;
      }
      const metricLines = nodeDetails(d, stats[d.id]);
      d3.select(this).text(metricLines[i] || "");
    });

    const topStats = snapshot?.stats || {};
    statThroughput.textContent = `${topStats.throughputGbps || 0} Gbps`;
    statJobs.textContent = `${topStats.runningJobs || 0} running`;
    statWorkers.textContent = `${topStats.workerCount || 0}`;
    statUpdated.textContent = formatUpdated(snapshot?.timestamp);
  };

  const handleIncoming = (payload) => {
    if (!payload || !payload.snapshot) return;
    applyWorkflowState(payload.workflowState, payload.workflowRunning);
    if (payload.config) {
      currentConfig = payload.config;
    }
    render(payload.snapshot);
  };

  const showWorkflowSummary = () => {
    if (!workflowSummaryBody) {
      return;
    }

    const topStats = currentSnapshot?.stats || {};
    const workerCount = Number(topStats.workerCount || 0);
    const runningJobs = Number(topStats.runningJobs || 0);
    const throughput = Number(topStats.throughputGbps || 0);

    workflowSummaryBody.innerHTML = `
      <p class="mb-2">Workflow has been stopped.</p>
      <ul class="mb-0">
        <li>Configuration: <strong>${bootstrap.configName || "Unknown"}</strong></li>
        <li>Workers configured: <strong>${workerCount}</strong></li>
        <li>Running jobs at stop: <strong>${runningJobs}</strong></li>
        <li>Last throughput: <strong>${throughput} Gbps</strong></li>
        <li>Stopped at: <strong>${new Date().toLocaleTimeString()}</strong></li>
      </ul>
    `;

    if (workflowSummaryModal) {
      workflowSummaryModal.show();
    }
  };

  const stopWorkflow = () => {
    const doStop = async () => {
      if (workflowStopped) {
        showWorkflowSummary();
        return;
      }

      try {
        const stopResponse = await fetch("/api/workflow/stop", { method: "POST" });
        const stopPayload = await stopResponse.json();
        if (!stopResponse.ok || stopPayload.ok === false) {
          throw new Error(stopPayload.error || "Unable to stop workflow.");
        }

        applyWorkflowState(stopPayload.status, stopPayload.running);
        setConnectionBadge("error", "Live: Stopped");
        stopLiveUpdates();

        if (currentSnapshot) {
          render(currentSnapshot);
        }

        showWorkflowSummary();
      } catch (error) {
        if (workflowSummaryBody) {
          workflowSummaryBody.innerHTML = `<p class="mb-0 text-danger">${error.message || "Unable to stop workflow."}</p>`;
        }
        if (workflowSummaryModal) {
          workflowSummaryModal.show();
        }
      }
    };

    doStop();
  };

  const startWorkflow = async () => {
    if (!workflowStopped) {
      return;
    }

    try {
      const statusResponse = await fetch("/api/proxy/status");
      const statusPayload = await statusResponse.json();
      if (!statusResponse.ok) {
        throw new Error(statusPayload.error || "Unable to query proxy status.");
      }

      if (!statusPayload.connected) {
        const startResponse = await fetch("/api/proxy/start", { method: "POST" });
        const startPayload = await startResponse.json();
        if (!startResponse.ok || !startPayload.ok) {
          throw new Error(startPayload.error || "Failed to launch simulator.");
        }
      }

      const runResponse = await fetch("/api/workflow/run", { method: "POST" });
      const runPayload = await runResponse.json();
      if (!runResponse.ok || runPayload.ok === false) {
        throw new Error(runPayload.error || "Unable to start workflow.");
      }

      const stateResponse = await fetch("/api/workflow/state");
      const statePayload = await stateResponse.json();
      if (!stateResponse.ok || statePayload.ok === false) {
        throw new Error(statePayload.error || "Unable to confirm workflow state.");
      }

      applyWorkflowState(statePayload.status, statePayload.running);
      setConnectionBadge("polling", "Live: Reconnecting…");
      startLiveUpdates();

      if (currentSnapshot) {
        render(currentSnapshot);
      }
    } catch (error) {
      if (workflowSummaryBody) {
        workflowSummaryBody.innerHTML = `<p class="mb-0 text-danger">${error.message || "Unable to start workflow."}</p>`;
      }
      if (workflowSummaryModal) {
        workflowSummaryModal.show();
      }
    }
  };

  const startPolling = () => {
    if (pollTimer) return;

    setConnectionBadge("polling", "Live: Polling");
    const file = encodeURIComponent(bootstrap.configFile || "");
    pollTimer = window.setInterval(async () => {
      try {
        const res = await fetch(`/api/workflow-status/snapshot?file=${file}`);
        const payload = await res.json();
        if (!res.ok || payload.ok === false) {
          throw new Error(payload.error || "Polling failed");
        }
        handleIncoming(payload);
      } catch {
        setConnectionBadge("error", "Live: Polling Error");
      }
    }, 1000);
  };

  const startWebSocket = () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      return;
    }

    const wsProto = window.location.protocol === "https:" ? "wss" : "ws";
    const file = encodeURIComponent(bootstrap.configFile || "");
    const wsUrl = `${wsProto}://${window.location.host}/ws/workflow-status?file=${file}`;

    try {
      ws = new WebSocket(wsUrl);
    } catch {
      startPolling();
      return;
    }

    ws.onopen = () => setConnectionBadge("connected", "Live: WebSocket");
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        handleIncoming(payload);
      } catch {
        // ignore malformed update
      }
    };
    ws.onerror = () => {
      setConnectionBadge("error", "Live: WebSocket Error");
      startPolling();
    };
    ws.onclose = () => {
      ws = null;
      if (!pollTimer) {
        startPolling();
      }
    };
  };

  const stopLiveUpdates = () => {
    if (ws) {
      try {
        ws.close();
      } catch {
        // ignore
      }
      ws = null;
    }

    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  };

  const startLiveUpdates = () => {
    if (bootstrap.websocketEnabled) {
      startWebSocket();
    } else {
      startPolling();
    }
  };

  if (currentSnapshot) {
    render(currentSnapshot);
  }

  setWorkflowToggleButton();
  setHeaderBadgesVisibility();

  if (stopWorkflowBtn) {
    stopWorkflowBtn.addEventListener("click", () => {
      if (workflowStopped) {
        startWorkflow();
      } else {
        stopWorkflow();
      }
    });
  }

  window.addEventListener("resize", () => {
    if (currentSnapshot) {
      render(currentSnapshot);
    }
  });

  const initializeWorkflowState = async () => {
    try {
      const response = await fetch("/api/workflow/state");
      const payload = await response.json();
      if (response.ok && payload.ok !== false) {
        applyWorkflowState(payload.status, payload.running);
      }
    } catch {
      // fallback to bootstrap state
    }

    startLiveUpdates();
  };

  initializeWorkflowState();
})();
