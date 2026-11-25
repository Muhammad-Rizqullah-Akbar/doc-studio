import ELK from 'elkjs';
import fs from 'node:fs';

const elk = new ELK();

const inputRaw = fs.readFileSync(0, 'utf8');
const spec = JSON.parse(inputRaw);

function estimateLabelSize(text, fontSize = 11) {
  const lines = String(text || '').split(/\r?\n|<br\s*\/?>/i);
  const maxLen = Math.max(1, ...lines.map((l) => l.replace(/<[^>]+>/g, '').length));
  const charW = fontSize * 0.62;
  const lineH = fontSize * 1.45;
  return {
    width: Math.ceil(maxLen * charW + 16),
    height: Math.ceil(lines.length * lineH + 8),
  };
}

const direction = spec.direction || 'DOWN'; // DOWN, RIGHT, LEFT, UP
const spacingNode = spec.nodeSpacing ?? 56;
const spacingLayer = spec.layerSpacing ?? 84;
const spacingEdgeNode = spec.edgeNodeSpacing ?? 32;
const spacingEdgeEdge = spec.edgeEdgeSpacing ?? 22;

const layoutOptions = {
  'elk.algorithm': spec.algorithm || 'layered',
  'elk.direction': direction,
  'elk.edgeRouting': 'ORTHOGONAL',
  'elk.hierarchyHandling': 'INCLUDE_CHILDREN',
  'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
  'elk.layered.crossingMinimization.greedySwitch.type': 'TWO_SIDED',
  'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
  'elk.layered.nodePlacement.favorStraightEdges': 'true',
  'elk.layered.thoroughness': '15',
  'elk.layered.mergeEdges': 'false',
  'elk.layered.spacing.nodeNodeBetweenLayers': String(spacingLayer),
  'elk.layered.spacing.edgeNodeBetweenLayers': String(spacingEdgeNode),
  'elk.layered.spacing.edgeEdgeBetweenLayers': String(spacingEdgeEdge),
  'elk.spacing.nodeNode': String(spacingNode),
  'elk.spacing.edgeNode': String(spacingEdgeNode),
  'elk.spacing.edgeEdge': String(spacingEdgeEdge),
  'elk.spacing.componentComponent': String(spacingNode + 20),
  'elk.padding': '[top=48,left=48,bottom=48,right=48]',
  'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
};

function buildNode(n) {
  const nodeObj = {
    id: String(n.id),
    width: Number(n.width || 180),
    height: Number(n.height || 64),
  };
  if (n.children && n.children.length > 0) {
    delete nodeObj.width;
    delete nodeObj.height;
    nodeObj.layoutOptions = {
      'elk.padding': '[top=46,left=28,bottom=28,right=28]',
      'elk.spacing.nodeNode': String(Math.max(36, spacingNode - 8)),
      'elk.layered.spacing.nodeNodeBetweenLayers': String(Math.max(60, spacingLayer - 10)),
      'elk.edgeRouting': 'ORTHOGONAL',
    };
    nodeObj.children = n.children.map(buildNode);
  }
  return nodeObj;
}

const graph = {
  id: 'root',
  layoutOptions,
  children: (spec.nodes || []).map(buildNode),
  edges: (spec.edges || []).map((e, idx) => {
    const eid = String(e.id || `e${idx}`);
    const edgeObj = {
      id: eid,
      sources: [String(e.source)],
      targets: [String(e.target)],
    };
    if (e.label && String(e.label).trim().length > 0) {
      const sz = estimateLabelSize(e.label, spec.edgeFontSize || 11);
      edgeObj.labels = [
        {
          id: `${eid}_lbl`,
          text: String(e.label),
          width: sz.width,
          height: sz.height,
          layoutOptions: {
            'elk.edgeLabels.placement': 'CENTER',
            'elk.edgeLabels.inline': 'false',
          },
        },
      ];
    }
    return edgeObj;
  }),
};

const laidOut = await elk.layout(graph);

// Flatten absolute coordinates for all nodes & edges
const absNodes = {};
function collectNodes(node, offX = 0, offY = 0, parentId = null) {
  for (const ch of node.children || []) {
    const ax = offX + (ch.x || 0);
    const ay = offY + (ch.y || 0);
    absNodes[ch.id] = {
      id: ch.id,
      parent: parentId,
      x: Math.round(ax),
      y: Math.round(ay),
      relX: Math.round(ch.x || 0),
      relY: Math.round(ch.y || 0),
      width: Math.round(ch.width || 0),
      height: Math.round(ch.height || 0),
    };
    if (ch.children && ch.children.length > 0) {
      collectNodes(ch, ax, ay, ch.id);
    }
  }
}
collectNodes(laidOut, 0, 0, null);

function collectEdges(node, offX = 0, offY = 0, out = []) {
  for (const e of node.edges || []) {
    const sec = (e.sections && e.sections[0]) || null;
    let start = null;
    let end = null;
    let bendPoints = [];
    if (sec) {
      start = {
        x: Math.round(offX + sec.startPoint.x),
        y: Math.round(offY + sec.startPoint.y),
      };
      end = {
        x: Math.round(offX + sec.endPoint.x),
        y: Math.round(offY + sec.endPoint.y),
      };
      bendPoints = (sec.bendPoints || []).map((bp) => ({
        x: Math.round(offX + bp.x),
        y: Math.round(offY + bp.y),
      }));
    }
    let labelPos = null;
    if (e.labels && e.labels[0] && e.labels[0].x !== undefined) {
      labelPos = {
        x: Math.round(offX + e.labels[0].x),
        y: Math.round(offY + e.labels[0].y),
        width: Math.round(e.labels[0].width || 0),
        height: Math.round(e.labels[0].height || 0),
      };
    }
    const srcNode = absNodes[e.sources[0]];
    const tgtNode = absNodes[e.targets[0]];
    const clamp = (v) => Math.max(0.05, Math.min(0.95, Number(v.toFixed(3))));
    const port = (pt, box) => {
      if (!pt || !box || !box.width || !box.height) return null;
      const rx = (pt.x - box.x) / box.width;
      const ry = (pt.y - box.y) / box.height;
      // Snap near-boundary port cleanly to 0 or 1 on the contact side
      const dLeft = Math.abs(rx);
      const dRight = Math.abs(rx - 1);
      const dTop = Math.abs(ry);
      const dBot = Math.abs(ry - 1);
      const m = Math.min(dLeft, dRight, dTop, dBot);
      if (m === dLeft) return { x: 0, y: clamp(ry) };
      if (m === dRight) return { x: 1, y: clamp(ry) };
      if (m === dTop) return { x: clamp(rx), y: 0 };
      return { x: clamp(rx), y: 1 };
    };
    out.push({
      id: e.id,
      source: e.sources[0],
      target: e.targets[0],
      start,
      end,
      exitPort: port(start, srcNode),
      entryPort: port(end, tgtNode),
      bendPoints,
      labelPos,
    });
  }
  for (const ch of node.children || []) {
    collectEdges(ch, offX + (ch.x || 0), offY + (ch.y || 0), out);
  }
  return out;
}

const edges = collectEdges(laidOut, 0, 0, []);
const result = {
  width: Math.round(laidOut.width || 800),
  height: Math.round(laidOut.height || 600),
  nodes: absNodes,
  edges,
};

process.stdout.write(JSON.stringify(result));
