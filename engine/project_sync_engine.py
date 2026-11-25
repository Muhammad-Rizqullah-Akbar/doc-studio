"""Deterministic Codebase Scanner for Living Docs & Diagram Regeneration after Refactoring."""
import hashlib
import json
import os
import re

SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", ".next", ".turbo", "target",
    "__pycache__", ".venv", "venv", "coverage", ".cache", "vendor",
}


def _iter_source_files(root_dir, exts):
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            if any(fn.lower().endswith(e) for e in exts):
                yield os.path.join(dirpath, fn)


def _extract_prisma_erd(root_dir):
    """Parse Prisma schema.prisma files into structured ERD nodes & FK edges."""
    models = []
    edges = []
    model_names = set()
    prisma_files = list(_iter_source_files(root_dir, (".prisma",)))

    raw_models = []
    for pf in prisma_files:
        txt = open(pf, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"model\s+(\w+)\s*\{([^}]*)\}", txt, re.S):
            name = m.group(1)
            body = m.group(2)
            model_names.add(name)
            raw_models.append((name, body, os.path.relpath(pf, root_dir)))

    for name, body, rel in raw_models:
        fields = []
        for line in body.splitlines():
            ln = line.strip()
            if not ln or ln.startswith("//") or ln.startswith("@@"):
                continue
            parts = ln.split()
            if len(parts) < 2:
                continue
            fname, ftype = parts[0], parts[1]
            clean_type = ftype.rstrip("?[]")
            is_pk = "@id" in ln
            is_rel = "@relation" in ln
            if clean_type in model_names:
                if is_rel:
                    fk_m = re.search(r"fields:\s*\[([^\]]+)\]", ln)
                    ref_m = re.search(r"references:\s*\[([^\]]+)\]", ln)
                    fk_f = fk_m.group(1).split(",")[0].strip() if fk_m else ""
                    ref_f = ref_m.group(1).split(",")[0].strip() if ref_m else "id"
                    edges.append({
                        "source": clean_type,
                        "target": name,
                        "source_field": ref_f,
                        "target_field": fk_f,
                        "label": f"{fname} (1:N)",
                        "cardinality": "1:N",
                    })
                continue
            tag = "PK " if is_pk else ("FK " if fname.endswith("Id") else "")
            fields.append(f"{tag}{fname}: {ftype}")
        models.append({"id": name, "label": name, "fields": fields[:16], "source_file": rel})

    return {"prisma_files": [os.path.relpath(p, root_dir) for p in prisma_files], "nodes": models, "edges": edges}


def _extract_sql_erd(root_dir):
    """Parse SQL DDL CREATE TABLE statements into exact row-level ERD nodes & FK edges."""
    models = []
    edges = []
    sql_files = list(_iter_source_files(root_dir, (".sql",)))
    for sf in sql_files:
        txt = open(sf, encoding="utf-8", errors="replace").read()
        rel = os.path.relpath(sf, root_dir)
        for m in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?([\w.]+)[`\"\]]?\s*\((.*?)\);", txt, re.I | re.S):
            tname = m.group(1).split(".")[-1]
            body = m.group(2)
            fields = []
            for raw_line in body.split(","):
                ln = raw_line.strip()
                if not ln or ln.upper().startswith(("CONSTRAINT", "INDEX", "KEY", "UNIQUE", "CHECK")):
                    fk_c = re.search(r"FOREIGN\s+KEY\s*\([`\"\[]?(\w+)[`\"\]]?\)\s*REFERENCES\s+[`\"\[]?([\w.]+)[`\"\]]?\s*\([`\"\[]?(\w+)[`\"\]]?\)", ln, re.I)
                    if fk_c:
                        edges.append({
                            "source": fk_c.group(2).split(".")[-1],
                            "target": tname,
                            "source_field": fk_c.group(3),
                            "target_field": fk_c.group(1),
                            "label": f"{fk_c.group(1)} (1:N)",
                            "cardinality": "1:N",
                        })
                    continue
                if ln.upper().startswith("PRIMARY KEY"):
                    continue
                parts = ln.split()
                if len(parts) < 2:
                    continue
                col = parts[0].strip('`"[]')
                ctype = parts[1].strip()
                is_pk = "PRIMARY KEY" in ln.upper()
                ref_m = re.search(r"REFERENCES\s+[`\"\[]?([\w.]+)[`\"\]]?\s*\([`\"\[]?(\w+)[`\"\]]?\)", ln, re.I)
                if ref_m:
                    edges.append({
                        "source": ref_m.group(1).split(".")[-1],
                        "target": tname,
                        "source_field": ref_m.group(2),
                        "target_field": col,
                        "label": f"{col} (1:N)",
                        "cardinality": "1:N",
                    })
                tag = "PK " if is_pk else ("FK " if ref_m or col.lower().endswith("_id") else "")
                fields.append(f"{tag}{col}: {ctype}")
            if fields:
                models.append({"id": tname, "label": tname, "fields": fields[:16], "source_file": rel})
    return {"sql_files": [os.path.relpath(p, root_dir) for p in sql_files], "nodes": models, "edges": edges}


def _extract_openapi_routes(root_dir):
    """Extract HTTP endpoints from OpenAPI/Swagger JSON specs."""
    routes = []
    for fp in _iter_source_files(root_dir, (".json",)):
        fn = os.path.basename(fp).lower()
        if not any(k in fn for k in ("openapi", "swagger")):
            continue
        try:
            data = json.load(open(fp, encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if isinstance(data, dict) and isinstance(data.get("paths"), dict):
            rel = os.path.relpath(fp, root_dir)
            for path_str, methods in data["paths"].items():
                if isinstance(methods, dict):
                    for m in methods:
                        if m.lower() in ("get", "post", "put", "patch", "delete"):
                            routes.append({"method": m.upper(), "path": path_str, "file": rel, "framework": "openapi"})
    return routes


def _extract_api_routes(root_dir):
    """Extract NestJS, Express, and FastAPI HTTP routes deterministically."""
    routes = []
    for fp in _iter_source_files(root_dir, (".ts", ".js", ".py")):
        rel = os.path.relpath(fp, root_dir)
        txt = open(fp, encoding="utf-8", errors="replace").read()
        # NestJS controller
        ctrl = re.search(r"@Controller\(['\"]([^'\"]*)['\"]\)", txt)
        if ctrl:
            prefix = ctrl.group(1).strip("/")
            for m in re.finditer(r"@(Get|Post|Put|Patch|Delete)\((?:['\"]([^'\"]*)['\"])?\)", txt):
                method = m.group(1).upper()
                sub = (m.group(2) or "").strip("/")
                full = "/" + "/".join(p for p in (prefix, sub) if p)
                routes.append({"method": method, "path": full, "file": rel, "framework": "nestjs"})
        # FastAPI / Flask / Express
        for m in re.finditer(r"(?:@app|@router|router|app)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]", txt):
            routes.append({"method": m.group(1).upper(), "path": m.group(2), "file": rel, "framework": "http-router"})
    return routes


def _extract_top_modules(root_dir):
    """Discover monorepo apps/packages/services for high-level architecture diagram."""
    modules = []
    for base in ("apps", "packages", "services", "src", "crates"):
        bp = os.path.join(root_dir, base)
        if os.path.isdir(bp):
            for entry in sorted(os.listdir(bp)):
                ep = os.path.join(bp, entry)
                if os.path.isdir(ep) and entry not in SKIP_DIRS:
                    modules.append({"id": f"{base}_{entry}", "label": f"{base}/{entry}", "group": base})
    return modules


def sync_project_docs_manifest(project_dir, out_manifest_path=None):
    """Generate deterministic project manifest + ready-to-draw ERD/Arch diagram specs + drift diff vs previous snapshot."""
    root = os.path.abspath(project_dir)
    if not os.path.isdir(root):
        raise FileNotFoundError(f"Project directory not found: {root}")

    erd_prisma = _extract_prisma_erd(root)
    erd_sql = _extract_sql_erd(root)
    # Merge Prisma + SQL models without duplicates
    seen_ids = {n["id"] for n in erd_prisma["nodes"]}
    erd = {
        "nodes": erd_prisma["nodes"] + [n for n in erd_sql["nodes"] if n["id"] not in seen_ids],
        "edges": erd_prisma["edges"] + erd_sql["edges"],
    }
    routes = _extract_api_routes(root) + _extract_openapi_routes(root)
    modules = _extract_top_modules(root)

    fingerprint_src = json.dumps({"erd": erd, "routes": routes, "modules": modules}, sort_keys=True)
    fingerprint = hashlib.sha256(fingerprint_src.encode("utf-8")).hexdigest()[:16]

    manifest = {
        "project_dir": root,
        "fingerprint": fingerprint,
        "summary": {
            "erd_model_count": len(erd["nodes"]),
            "erd_relation_count": len(erd["edges"]),
            "api_route_count": len(routes),
            "module_count": len(modules),
        },
        "modules": modules,
        "api_routes": routes[:200],
        "erd_diagram_spec": {
            "type": "erd",
            "title": f"Entity Relationship Diagram - {os.path.basename(root)}",
            "direction": "RIGHT",
            "nodes": erd["nodes"],
            "edges": erd["edges"],
        },
    }

    drift = {"first_snapshot": True, "changed": False, "details": []}
    if out_manifest_path:
        mpath = os.path.abspath(out_manifest_path)
        if os.path.exists(mpath):
            try:
                prev = json.load(open(mpath, encoding="utf-8"))
                drift["first_snapshot"] = False
                if prev.get("fingerprint") != fingerprint:
                    drift["changed"] = True
                    prev_models = {n["id"] for n in prev.get("erd_diagram_spec", {}).get("nodes", [])}
                    curr_models = {n["id"] for n in erd["nodes"]}
                    if prev_models != curr_models:
                        drift["details"].append({
                            "area": "erd_models",
                            "added": sorted(curr_models - prev_models),
                            "removed": sorted(prev_models - curr_models),
                        })
                    prev_routes = {(r["method"], r["path"]) for r in prev.get("api_routes", [])}
                    curr_routes = {(r["method"], r["path"]) for r in routes}
                    if prev_routes != curr_routes:
                        drift["details"].append({
                            "area": "api_routes",
                            "added": [f"{m} {p}" for m, p in sorted(curr_routes - prev_routes)][:30],
                            "removed": [f"{m} {p}" for m, p in sorted(prev_routes - curr_routes)][:30],
                        })
            except Exception:
                pass
        os.makedirs(os.path.dirname(mpath), exist_ok=True)
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        manifest["manifest_path"] = mpath

    manifest["drift"] = drift
    return manifest
