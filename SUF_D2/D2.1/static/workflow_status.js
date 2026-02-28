(() => {
  const bootstrap = window.WORKFLOW_STATUS_BOOTSTRAP || {};
  const canvas = document.getElementById("workflow-monitor-canvas");
  const badge = document.getElementById("monitor-connection-badge");
  const statThroughput = document.getElementById("stat-throughput");
  const statJobs = document.getElementById("stat-jobs");
  const statWorkers = document.getElementById("stat-workers");
  const statUpdated = document.getElementById("stat-updated");

  if (!canvas) {
    return;
  }

  const svg = d3.select(canvas).append("svg").attr("class", "workflow-monitor-svg");
  const linkLayer = svg.append("g").attr("class", "link-layer");
  const nodeLayer = svg.append("g").attr("class", "node-layer");

  let currentSnapshot = bootstrap.snapshot || null;
  let ws = null;
  let pollTimer = null;

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
    const centerY = height * 0.5;

    const source = components.find((c) => c.id === "source");
    if (source) map.set(source.id, { ...source, x: width * 0.08, y: centerY });

    const ejfat = components.find((c) => c.id === "ejfat");
    if (ejfat) map.set(ejfat.id, { ...ejfat, x: width * 0.24, y: centerY });

    const workerStartX = ejfat ? width * 0.42 : width * 0.28;
    const workerEndX = width * 0.68;
    const workerCols = Math.max(2, Math.min(4, Math.ceil(Math.sqrt(workerNodes.length))));
    const workerRows = Math.max(1, Math.ceil(workerNodes.length / workerCols));
    const xGap = workerCols > 1 ? (workerEndX - workerStartX) / (workerCols - 1) : 0;
    const yStart = height * 0.2;
    const yEnd = height * 0.8;
    const yGap = workerRows > 1 ? (yEnd - yStart) / (workerRows - 1) : 0;

    workerNodes.forEach((node, i) => {
      const col = i % workerCols;
      const row = Math.floor(i / workerCols);
      map.set(node.id, {
        ...node,
        x: workerStartX + xGap * col,
        y: yStart + yGap * row,
      });
    });

    const aggregator = components.find((c) => c.id === "aggregator");
    if (aggregator) map.set(aggregator.id, { ...aggregator, x: width * 0.78, y: height * 0.35 });

    const plotter = components.find((c) => c.id === "plotter");
    if (plotter) map.set(plotter.id, { ...plotter, x: width * 0.9, y: height * 0.35 });

    const viewer = components.find((c) => c.id === "viewer");
    if (viewer) map.set(viewer.id, { ...viewer, x: width * 0.9, y: height * 0.65 });

    const hpc = components.find((c) => c.id === "hpc");
    if (hpc) map.set(hpc.id, { ...hpc, x: width * 0.78, y: height * 0.65 });

    return {
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
    if (node.group === "source") return [`${stats.eventsPerSec || 0} evt/s`, `${stats.rateGbps || 0} Gbps`];
    if (node.group === "transport") return [`${stats.outStreams || 0} streams`, `${stats.splitRateGbps || 0} Gbps/stream`];
    if (node.group === "worker") return [`${stats.eventsPerSec || 0} evt/s`, `${stats.inferenceMs || 0} ms infer`];
    if (node.group === "aggregate") return [`${stats.histogramsPerSec || 0} hist/s`, `Q=${stats.queueDepth || 0}`];
    if (node.group === "plot") return [`${stats.imagesPerMin || 0} img/min`, `${stats.lastRenderMs || 0} ms`];
    if (node.group === "monitor") return [`${stats.latestImageAgeSec || 0} s age`, `${stats.viewers || 0} viewers`];
    if (node.group === "hpc") return [`jobs ${stats.runningJobs || 0}/${stats.totalWorkers || 0}`, `${stats.busyPct || 0}% busy`];
    return ["--"];
  };

  const render = (snapshot) => {
    currentSnapshot = snapshot;
    const bounds = canvas.getBoundingClientRect();
    const width = Math.max(900, Math.floor(bounds.width));
    const height = Math.max(520, Math.floor(window.innerHeight * 0.62));

    svg.attr("viewBox", `0 0 ${width} ${height}`).attr("width", "100%").attr("height", height);

    const { nodes, links } = buildLayout(snapshot, width, height);
    const stats = snapshot?.nodeStats || {};

    const linkSel = linkLayer.selectAll("line.flow-link").data(links, (d) => `${d.source}->${d.target}`);
    linkSel
      .join((enter) => enter.append("line").attr("class", "flow-link"), (update) => update, (exit) => exit.remove())
      .attr("x1", (d) => d.sourceNode.x)
      .attr("y1", (d) => d.sourceNode.y)
      .attr("x2", (d) => d.targetNode.x)
      .attr("y2", (d) => d.targetNode.y)
      .classed("flow-link-meta", (d) => d.meta === "contains");

    const nodeSel = nodeLayer.selectAll("g.wf-node").data(nodes, (d) => d.id);
    const nodeEnter = nodeSel.join(
      (enter) => {
        const g = enter.append("g").attr("class", "wf-node");
        g.append("rect").attr("rx", 10).attr("ry", 10).attr("width", 158).attr("height", 64).attr("x", -79).attr("y", -32);
        g.append("text").attr("class", "wf-node-title").attr("text-anchor", "middle").attr("y", -10);
        g.append("text").attr("class", "wf-node-metric").attr("text-anchor", "middle").attr("y", 8);
        g.append("text").attr("class", "wf-node-metric").attr("text-anchor", "middle").attr("y", 23);
        return g;
      },
      (update) => update,
      (exit) => exit.remove()
    );

    nodeEnter.attr("transform", (d) => `translate(${d.x},${d.y})`);
    nodeEnter.select("rect").attr("class", (d) => `wf-node-box wf-node-${d.group}`);
    nodeEnter.select("text.wf-node-title").text((d) => d.label);

    nodeEnter.selectAll("text.wf-node-metric").each(function (d, i) {
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
    render(payload.snapshot);
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
      if (!pollTimer) {
        startPolling();
      }
    };
  };

  if (currentSnapshot) {
    render(currentSnapshot);
  }

  window.addEventListener("resize", () => {
    if (currentSnapshot) {
      render(currentSnapshot);
    }
  });

  if (bootstrap.websocketEnabled) {
    startWebSocket();
  } else {
    startPolling();
  }
})();
