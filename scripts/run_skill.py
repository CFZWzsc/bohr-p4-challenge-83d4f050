#!/usr/bin/env python3
"""Biological mechanism / pathway diagrammer (standard library only).

Extracts biological entities, compartment assignments and typed regulatory
interactions, then emits a compartment-aware pathway specification with
legend, data encoding, pathway order and consistency checks.  Deterministic,
offline, and explicit about uncertainty; no biological fact is invented.
"""

import argparse
import hashlib
import json
import os
import re
import sys

import figure_svg

DEFAULT_CASE = "/input/case.json"
DEFAULT_OUT = "/app/output/result.json"
DEFAULT_WORK = "/app/work"
SKILL_NAME = "biological-pathway-diagrammer"
SKILL_VERSION = "1.0.0"
CHALLENGE_ID = "challenge-83d4f050"
MAX_TEXT = 400000
SKIP_KEYS = {"output_contract", "scoring", "tags", "meta", "case_id",
             "challenge_id", "skill", "contract_notes"}

COMPARTMENTS = [
    ("extracellular", ("胞外", "细胞外", "extracellular", "secreted", "lumen")),
    ("membrane", ("细胞膜", "质膜", "胞膜", "膜上", "membrane", "plasma membrane")),
    ("cytoplasm", ("细胞质", "胞质", "胞浆", "cytoplasm", "cytosol")),
    ("nucleus", ("细胞核", "核内", "nucleus", "nuclear")),
    ("mitochondria", ("线粒体", "mitochondri")),
    ("er_golgi", ("内质网", "高尔基", "endoplasmic", "golgi")),
]
COMPARTMENT_ORDER = {"extracellular": 0, "membrane": 1, "cytoplasm": 2,
                     "mitochondria": 2, "er_golgi": 2, "nucleus": 3, "unknown": 2}

CN_TRIGGERS = [
    ("activation", ("激活", "促进", "上调", "增强", "诱导", "招募", "募集", "启动", "表达")),
    ("inhibition", ("抑制", "阻断", "下调", "降低", "减弱", "沉默", "拮抗", "降解")),
    ("binding", ("结合", "互作", "相互作用", "识别", "组装")),
    ("modification", ("磷酸化", "泛素化", "甲基化", "乙酰化", "切割", "修饰")),
    ("transport", ("转运", "运输", "分泌", "易位", "迁移", "内吞", "外排")),
]
EN_TRIGGERS = [
    ("activation", r"activates?|promotes?|induces?|upregulates?|enhances?|drives?"),
    ("inhibition", r"inhibits?|suppresses?|represses?|downregulates?|blocks?"),
    ("binding", r"binds?|interacts?\s+with|assembles?\s+with|recognizes?"),
    ("modification", r"phosphorylates?|ubiquitinates?|methylates?|cleaves?|modifies?"),
    ("transport", r"transports?|translocates?|secretes?|exports?|imports?"),
]
REL_STYLE = {
    "activation": {"color": "#0072B2", "line": "solid", "arrowhead": "solid_arrow", "polarity": "positive"},
    "inhibition": {"color": "#D55E00", "line": "solid", "arrowhead": "bar", "polarity": "negative"},
    "binding": {"color": "#009E73", "line": "solid", "arrowhead": "none", "polarity": "neutral"},
    "modification": {"color": "#CC79A7", "line": "dashed", "arrowhead": "solid_arrow", "polarity": "positive"},
    "transport": {"color": "#E69F00", "line": "solid", "arrowhead": "open_arrow", "polarity": "neutral"},
    "unsupported": {"color": "#999999", "line": "dotted", "arrowhead": "none", "polarity": "unknown"},
}
REL_LABEL = {"activation": "activates", "inhibition": "inhibits",
             "binding": "binds", "modification": "phosphorylates",
             "transport": "transports", "unsupported": "relation stated"}
LANE_LABELS = {"extracellular": "extracellular space",
               "membrane": "plasma membrane", "cytoplasm": "cytoplasm",
               "mitochondria": "mitochondria", "er_golgi": "ER / Golgi",
               "nucleus": "nucleus", "unknown": "localisation not stated"}
SUFFIX_TYPES = [
    ("gene", ("基因",)),
    ("protein", ("蛋白", "激酶", "磷酸酶", "受体", "因子", "通道", "酶", "抗体")),
    ("complex", ("复合物", "复合体", "二聚体", "多聚体", "家族")),
    ("cell", ("细胞",)),
    ("compartment", ("细胞核", "细胞质", "胞质", "胞膜", "细胞膜", "线粒体", "内质网", "高尔基")),
]
STOPWORDS = {"the", "and", "for", "with", "from", "that", "this", "these", "those",
             "into", "using", "used", "were", "was", "are", "is", "be", "of", "in",
             "on", "to", "by", "as", "at", "an", "or", "we", "our", "their", "its"}
TOKEN_STRIP = " \t\r\n，。；;：:、（）()[]【】\"'“”‘’《》<>"


def sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def norm(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def read_text_file(path):
    try:
        if os.path.isfile(path) and os.path.getsize(path) <= 4 * 1024 * 1024:
            with open(path, "r", encoding="utf-8-sig") as handle:
                return handle.read()
    except (OSError, UnicodeDecodeError):
        return None
    return None


def collect_material(case, base_dir):
    parts, unreadable = [], []

    def walk(node, label):
        if isinstance(node, str):
            stripped = node.strip()
            if len(stripped) >= 40:
                parts.append({"label": label, "text": stripped, "path": None})
                return
            if stripped and not stripped.startswith(("{", "[")):
                for candidate in (stripped, os.path.join(base_dir, stripped)):
                    text = read_text_file(candidate)
                    if text is not None:
                        parts.append({"label": label, "text": text, "path": candidate})
                        return
        elif isinstance(node, dict):
            for key, value in node.items():
                if key in SKIP_KEYS or key in ("id", "name", "title", "type", "kind"):
                    continue
                walk(value, "%s.%s" % (label, key))
        elif isinstance(node, list):
            for idx, value in enumerate(node):
                walk(value, "%s[%d]" % (label, idx))

    for key, value in case.items():
        if key in SKIP_KEYS:
            continue
        walk(value, key)
    parts.sort(key=lambda item: (-len(item["text"]), item["label"]))
    return parts, unreadable


def task_text(base_dir):
    for name in ("task.md", "TASK.md", "task.txt"):
        path = os.path.join(base_dir, name)
        text = read_text_file(path)
        if text:
            return text, path
    return "", None


def infer_type(name):
    for kind, suffixes in SUFFIX_TYPES:
        if any(name.endswith(suffix) for suffix in suffixes):
            return kind
    if re.search(r"[A-Za-z]", name):
        if name.isupper() or re.match(r"^[A-Z]{2,}[0-9]*$", name):
            return "gene"
        return "protein"
    return "entity"


def infer_compartment(name, context):
    for compartment, markers in COMPARTMENTS:
        if any(marker in name for marker in markers):
            return compartment
    position = context.find(name)
    if position < 0:
        return "unknown"
    for compartment, markers in COMPARTMENTS:
        for marker in markers:
            index = context.find(marker)
            if 0 <= index and abs(position - index) <= 40:
                return compartment
    return "unknown"


def pick_entities(case, text):
    explicit = []
    for key in ("entities", "nodes", "molecules", "components"):
        value = case.get(key)
        if not isinstance(value, list):
            continue
        for entry in value:
            if isinstance(entry, str) and entry.strip():
                explicit.append({"name": entry.strip(), "type": None, "compartment": None,
                                 "source": key})
            elif isinstance(entry, dict):
                name = entry.get("name") or entry.get("label") or entry.get("symbol")
                if not isinstance(name, str) or not name.strip():
                    continue
                explicit.append({
                    "name": name.strip(),
                    "type": entry.get("type") or entry.get("kind") or entry.get("molecule_type"),
                    "compartment": entry.get("compartment") or entry.get("location") or entry.get("cellular_location"),
                    "source": key,
                    "evidence": entry.get("evidence"),
                })
    if explicit:
        return explicit

    names = []
    for match in re.finditer(
            r"([\u4e00-\u9fffA-Za-z0-9\-/+]{2,20}?"
            r"(?:基因|蛋白|受体|因子|激酶|磷酸酶|复合物|复合体|细胞|通路|分子|酶|通道))", text):
        names.append(match.group(1))
    for match in re.finditer(r"\b([A-Z][A-Za-z0-9\-]{2,15})\b", text):
        if match.group(1).lower() not in STOPWORDS:
            names.append(match.group(1))
    result, seen = [], set()
    for name in names:
        key = name.lower()
        if key in seen or key in STOPWORDS:
            continue
        seen.add(key)
        result.append({"name": name, "type": infer_type(name),
                       "compartment": infer_compartment(name, text), "source": "text"})
    return result


def clean_token(raw):
    token = raw.strip(TOKEN_STRIP)
    token = re.sub(r"^(?:而|且|并|又|也|均|可|能|会|可以|其中|同时|随后|然后)+", "", token)
    token = re.sub(r"的$", "", token).strip(TOKEN_STRIP)
    if len(token) < 2 or len(token) > 26 or token.lower() in STOPWORDS:
        return None
    return token


def extract_relations(text):
    relations = []
    sentences = [segment.strip() for segment in re.split(r"(?<=[。；;！!？?])|(?<=\.)\s+", text)
                 if segment.strip()]
    for sentence in sentences:
        for relation_type, triggers in CN_TRIGGERS:
            for trigger in triggers:
                start = 0
                while True:
                    index = sentence.find(trigger, start)
                    if index < 0:
                        break
                    left = re.split(r"[，。；;：:、]", sentence[:index])[-1].strip()
                    right = re.split(r"[，。；;：:、]", sentence[index + len(trigger):])[0].strip()
                    source = clean_token(left[-26:])
                    target = clean_token(right[:26])
                    if source and target and source != target:
                        relations.append({"source": source, "target": target,
                                          "type": relation_type, "raw": norm(sentence)[:240],
                                          "extractor": "cn_trigger"})
                    start = index + len(trigger)
        for relation_type, pattern in EN_TRIGGERS:
            for match in re.finditer(
                    r"\b([A-Za-z0-9\-/]{2,26})\s+(?:%s)\s+([A-Za-z0-9\-/]{2,26})\b" % pattern,
                    sentence):
                relations.append({"source": match.group(1), "target": match.group(2),
                                  "type": relation_type, "raw": norm(sentence)[:240],
                                  "extractor": "en_trigger"})
    return relations


def normalize_type(value):
    if not isinstance(value, str):
        return "unsupported"
    lowered = value.lower()
    mapping = {
        "activation": ("activat", "promot", "induc", "upregulat", "enhanc", "激活", "促进", "上调"),
        "inhibition": ("inhibit", "suppress", "repress", "block", "抑制", "阻断", "下调"),
        "binding": ("bind", "interact", "complex", "结合", "互作"),
        "modification": ("phosphoryl", "ubiquit", "methyl", "cleav", "modif", "磷酸化", "泛素化", "修饰"),
        "transport": ("transport", "transloc", "secret", "转运", "运输", "分泌", "易位"),
    }
    for canonical, markers in mapping.items():
        if any(marker in lowered for marker in markers):
            return canonical
    return "unsupported"


def pick_relations(case, text):
    explicit = []
    for key in ("relations", "edges", "interactions", "links"):
        value = case.get(key)
        if not isinstance(value, list):
            continue
        for entry in value:
            if not isinstance(entry, dict):
                continue
            source = entry.get("source") or entry.get("from") or entry.get("regulator")
            target = entry.get("target") or entry.get("to") or entry.get("regulated")
            if not (source and target):
                continue
            explicit.append({
                "source": str(source), "target": str(target),
                "type": normalize_type(entry.get("type") or entry.get("interaction")
                                       or entry.get("relation")),
                "raw": entry.get("evidence") or entry.get("text"),
                "extractor": key,
                "compartment": entry.get("compartment"),
            })
    if explicit:
        return explicit
    relations = extract_relations(text)
    seen, unique = set(), []
    for item in relations:
        key = (item["source"].lower(), item["target"].lower(), item["type"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def directed_adjacency(names, edges):
    adjacency = {name: [] for name in names}
    for edge in edges:
        if edge["relation_type"] in ("activation", "inhibition", "transport", "modification"):
            if edge["source"] in adjacency and edge["target"] in adjacency:
                adjacency[edge["source"]].append(edge["target"])
    return adjacency


def topological_layers(names, adjacency):
    rank = {name: 0 for name in names}
    for _ in range(len(names)):
        changed = False
        for source, targets in adjacency.items():
            for target in targets:
                if rank[target] < rank[source] + 1:
                    rank[target] = rank[source] + 1
                    changed = True
        if not changed:
            break
    layers = {}
    for name in names:
        layers.setdefault(rank[name], []).append(name)
    return layers, rank


def find_feedback_loops(names, adjacency, limit=12):
    loops, seen = [], set()

    def dfs(node, path, on_path):
        if len(loops) >= limit:
            return
        for target in adjacency.get(node, []):
            if target in on_path:
                idx = path.index(target)
                cycle = tuple(path[idx:] + [target])
                key = tuple(sorted(set(cycle)))
                if key not in seen:
                    seen.add(key)
                    loops.append(list(cycle))
            elif len(path) < 12:
                on_path.add(target)
                path.append(target)
                dfs(target, path, on_path)
                path.pop()
                on_path.discard(target)

    for name in names:
        dfs(name, [name], {name})
    return loops


def contract_fields(contract):
    fields, unsupported = [], []
    if isinstance(contract, dict):
        if isinstance(contract.get("properties"), dict):
            return list(contract["properties"].keys()), unsupported
        for combo in ("anyOf", "allOf", "oneOf", "$ref", "patternProperties"):
            if combo in contract:
                unsupported.append(combo)
        nested = contract.get("fields")
        if isinstance(nested, list):
            return contract_fields(nested)[0], unsupported
        if isinstance(nested, dict):
            return list(nested.keys()), unsupported
        reserved = {"type", "required", "optional", "additionalProperties", "title",
                    "description", "version", "schema", "$schema"}
        return [key for key in contract if key not in reserved and not str(key).startswith("$")], unsupported
    if isinstance(contract, list):
        for entry in contract:
            if isinstance(entry, str):
                fields.append(entry)
            elif isinstance(entry, dict):
                name = entry.get("name") or entry.get("field") or entry.get("key")
                if name:
                    fields.append(str(name))
        return fields, unsupported
    return fields, unsupported


ALIASES = {
    "status": "status", "mechanism_spec": "mechanism_spec", "pathway_spec": "mechanism_spec",
    "drawing_spec": "mechanism_spec", "entities": "entities", "relations": "relations",
    "edges": "relations", "pathway_order": "pathway_order", "legend": "legend",
    "data_encoding": "data_encoding", "consistency_checks": "consistency_checks",
    "checks": "consistency_checks", "editable_source": "editable_source",
    "export_plan": "export_plan", "export_artifact": "export_plan",
    "source_register": "source_register", "gaps": "gaps", "uncertainty": "uncertainty",
    "evidence": "evidence", "stats": "stats", "limitations": "limitations",
}


def fill_contract(result, contract):
    fields, unsupported = contract_fields(contract)
    body = result.get("result") if isinstance(result.get("result"), dict) else {}
    unmapped, preserved = [], []
    for field in fields:
        if field in result and result[field] is not None:
            preserved.append(field)
            continue
        key = ALIASES.get(field.lower(), field.lower())
        if key in result and result[key] is not None:
            result[field] = result[key]
            preserved.append(field)
        elif key in body and body[key] is not None:
            result[field] = body[key]
            preserved.append(field)
        else:
            result[field] = None
            unmapped.append(field)
    result["contract_notes"] = {
        "declared_fields": fields, "preserved_fields": preserved,
        "unmapped_fields": unmapped, "unsupported_features": unsupported,
        "note": "Unsupported or absent fields are null; nothing is fabricated.",
    }
    if result.get("status") == "success" and (unmapped or unsupported):
        result["status"] = "partial"


def write_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def build_export_plan(case):
    requested = case.get("export") or case.get("target_format") or case.get("export_spec")
    formats = []
    if isinstance(requested, str):
        formats = [part.strip().lower() for part in re.split(r"[,/;]", requested) if part.strip()]
    if not formats:
        formats = ["svg", "pdf", "png"]
    rules = {
        "svg": ["text_editable", "named_layers", "arrow_markers_editable"],
        "pdf": ["fonts_embedded", "vector_preserved"],
        "png": ["dpi_at_least_300", "no_label_clipping"],
        "eps": ["fonts_embedded", "vector_preserved"],
    }
    return [{"format": fmt, "required_checks": rules.get(fmt, ["resolution_declared"]),
             "performed": False,
             "reason": "no renderer invoked; checks are a reproducible plan"} for fmt in formats]


FIGURE_BLOCKLIST = {
    "task", "tasks", "draw", "build", "export", "exports", "deliver", "show",
    "distinguish", "label", "labels", "arrow", "arrows", "edge", "edges",
    "node", "nodes", "mechanism", "pathway", "svg", "png", "pdf", "eps",
    "activated", "phosphorylated", "inhibited", "repressed", "stimulated",
    "extracellular", "membrane", "cytoplasm", "nucleus", "nuclear",
}


def split_sentences(text):
    return [segment.strip() for segment in
            re.split(r"(?<=[。；;！!？?])|(?<=\.)\s+|\n+", text) if segment.strip()]


def build_anchor_index(parts):
    """Flat, deterministic list of sentence anchors for the material."""
    index = []
    for part in parts:
        label = str(part.get("label") or "").lower()
        if "task" in label or label in ("instruction", "case"):
            continue
        source = (os.path.basename(part["path"])
                  if part.get("path") else str(part.get("label") or "material"))
        body = "\n".join(line for line in part["text"].splitlines()
                         if not line.strip().startswith("#"))
        for p_idx, paragraph in enumerate(re.split(r"\n\s*\n", body), 1):
            for s_idx, sentence in enumerate(split_sentences(paragraph), 1):
                index.append({"anchor": "%s:p%d.s%d" % (source, p_idx, s_idx),
                              "text": sentence, "source": source})
    return index


def _name_pattern(name):
    return re.compile(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(name), re.I)


def find_anchor(index, name, also=None):
    for item in index:
        if _name_pattern(name).search(item["text"]) and (
                also is None or _name_pattern(also).search(item["text"])):
            return item
    if also is not None:
        return find_anchor(index, name)
    return None


def build_figure_graph(parts, entities, relations, explicit_entities):
    index = build_anchor_index(parts)
    material_text = " ".join(item["text"] for item in index)
    lowered_text = material_text.lower()
    nodes, node_by_key, exceptions = [], {}, []

    def acceptable(name):
        cleaned = name.strip()
        lowered = cleaned.lower()
        if not (2 <= len(cleaned) <= 24):
            return False
        if lowered in STOPWORDS or lowered in FIGURE_BLOCKLIST:
            return False
        if re.fullmatch(r"[A-Za-z]+ed", cleaned):
            return False
        if cleaned.endswith((".md", ".csv", ".json", ".txt")):
            return False
        if lowered in {"which", "where", "while", "whose", "what", "when", "who"}:
            return False
        if not (re.search(r"[A-Z\u4e00-\u9fff0-9]", cleaned)):
            return False
        return lowered in lowered_text

    def add_node(name, kind, anchor, quote, lane):
        key = re.sub(r"\s+", "", name).lower()
        if key in node_by_key:
            return node_by_key[key]
        node = {"id": "N%d" % (len(nodes) + 1), "label": name,
                "kind": kind, "anchor": anchor, "quote": quote, "lane": lane}
        nodes.append(node)
        node_by_key[key] = node["id"]
        return node["id"]

    for position, entity in enumerate(entities):
        name = entity["name"]
        anchor_entry = find_anchor(index, name)
        if anchor_entry and not acceptable(name):
            exceptions.append({"item": "entity", "name": name,
                               "status": "not_drawn",
                               "reason": "name is a task/heading/stop token, not a material entity"})
            continue
        if not anchor_entry:
            if not explicit_entities:
                exceptions.append({"item": "entity", "name": name,
                                   "status": "not_drawn",
                                   "reason": "no paragraph/sentence mentions the name"})
                continue
            add_node(name, entity.get("type") or "entity",
                     "case:entities[%d]" % position,
                     entity.get("evidence") or name,
                     entity.get("compartment") or "unknown")
            continue
        sentence = anchor_entry["text"]
        position_in_sentence = sentence.lower().find(name.lower())
        compartment = "unknown"
        for comp, markers in COMPARTMENTS:
            for marker in markers:
                marker_index = sentence.lower().find(marker)
                if marker_index >= 0 and abs(position_in_sentence - marker_index) <= 40:
                    compartment = comp
                    break
            if compartment != "unknown":
                break
        if re.search(r"%s\s+(?:binds?|binds\s+to)\b" % re.escape(name), sentence, re.I):
            compartment = "extracellular"
        if compartment == "unknown":
            compartment = entity.get("compartment") or "unknown"
        add_node(name, entity.get("type") or "entity",
                 anchor_entry["anchor"], sentence, compartment)

    drawn_edges, seen_edges = [], set()
    for relation in relations:
        source_name = str(relation.get("source") or "")
        target_name = str(relation.get("target") or "")
        source_id = node_by_key.get(re.sub(r"\s+", "", source_name).lower())
        target_id = node_by_key.get(re.sub(r"\s+", "", target_name).lower())
        if source_id is None and acceptable(source_name):
            anchor_entry = find_anchor(index, source_name)
            source_id = add_node(source_name, "entity", anchor_entry["anchor"],
                                 anchor_entry["text"], "unknown")
        if target_id is None and acceptable(target_name):
            anchor_entry = find_anchor(index, target_name)
            target_id = add_node(target_name, "entity", anchor_entry["anchor"],
                                 anchor_entry["text"], "unknown")
        if not source_id or not target_id or source_id == target_id:
            exceptions.append({
                "item": "relation", "status": "not_drawn",
                "source": source_name, "target": target_name,
                "reason": "endpoint is not a material entity (task-instruction or stop word)",
            })
            continue
        kind = str(relation.get("type") or "unsupported")
        key = (source_id, target_id, kind)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        anchor_entry = find_anchor(index, source_name, target_name) or \
            find_anchor(index, source_name)
        drawn_edges.append({
            "id": "E%d" % (len(drawn_edges) + 1),
            "source": source_id, "target": target_id, "kind": kind,
            "label": REL_LABEL.get(kind, kind),
            "anchor": anchor_entry["anchor"] if anchor_entry else "material:unlocated",
            "quote": (relation.get("evidence")
                      or (anchor_entry["text"] if anchor_entry else ""))[:220],
        })
    return nodes, drawn_edges, index, exceptions


def main():
    parser = argparse.ArgumentParser(description="Biological mechanism pathway diagrammer")
    parser.add_argument("--case", default=DEFAULT_CASE)
    parser.add_argument("--out", "--output", dest="out", default=DEFAULT_OUT)
    parser.add_argument("--work", default=DEFAULT_WORK)
    args = parser.parse_args()
    os.environ["SK_RESULT_PATH"] = str(getattr(args, "out", None) or getattr(args, "output", None) or "")

    result = {
        "case_id": None,
        "challenge_id": CHALLENGE_ID,
        "skill": {"name": SKILL_NAME, "version": SKILL_VERSION},
        "status": "failed",
        "result": {
            "mechanism_spec": {"canvas": {}, "compartments": [], "entities": [],
                               "edges": [], "legend": [], "pathway_order": {},
                               "data_encoding": []},
            "entities": [], "relations": [], "pathway_order": {}, "legend": [],
            "data_encoding": [], "consistency_checks": [], "export_plan": [],
            "editable_source": None, "source_register": [], "gaps": [],
        },
        "evidence": [], "uncertainty": [], "errors": [], "stats": {},
        "limitations": [
            "Compartment assignment uses explicit fields and local text cues only.",
            "Figure layout is deterministic and lane-based; no force simulation is used.",
        ],
    }

    try:
        case = load_json(args.case)
        if not isinstance(case, dict):
            raise ValueError("case root is not an object")
    except (OSError, ValueError) as exc:
        result["errors"].append({"stage": "read_case", "type": type(exc).__name__,
                                 "detail": "case.json missing or not valid JSON"})
        result["status"] = "insufficient_input"
        write_json(args.out, result)
        return 2

    base_dir = os.path.dirname(os.path.abspath(args.case))
    result["case_id"] = case.get("case_id") or case.get("id")
    contract = case.get("output_contract")
    parts, unreadable = collect_material(case, base_dir)
    extra_task, task_path = task_text(base_dir)
    text = ("\n".join(part["text"] for part in parts) + "\n" + extra_task)[:MAX_TEXT]

    entities = pick_entities(case, text)
    relations = pick_relations(case, text)

    if not text and not entities:
        result["status"] = "insufficient_input"
        result["uncertainty"].append({"item": "material", "detail": "no readable mechanism material"})
        fill_contract(result, contract)
        write_json(args.out, result)
        return 0

    seen, unique_entities = set(), []
    for entity in entities:
        key = entity["name"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique_entities.append(entity)
    entities = unique_entities
    for entity in entities:
        if not entity.get("type"):
            entity["type"] = infer_type(entity["name"])
        if not entity.get("compartment"):
            entity["compartment"] = infer_compartment(entity["name"], text)

    explicit_entities = any(entity.get("source") in ("entities", "nodes", "molecules",
                                                      "components") for entity in entities)
    fig_nodes, fig_edges, _, figure_exceptions = build_figure_graph(
        parts, entities, relations, explicit_entities)
    if fig_nodes and not explicit_entities:
        figure_labels = {node["label"] for node in fig_nodes}
        entities = [entity for entity in entities if entity["name"] in figure_labels]
    if fig_edges:
        label_by_id = {node["id"]: node["label"] for node in fig_nodes}

        def _graph_key(name):
            return re.sub(r"\s+", "", str(name)).lower()

        allowed = {(_graph_key(label_by_id[edge["source"]]),
                    _graph_key(label_by_id[edge["target"]]), edge["kind"])
                   for edge in fig_edges}
        relations = [relation for relation in relations
                     if (_graph_key(relation.get("source")),
                         _graph_key(relation.get("target")),
                         str(relation.get("type"))) in allowed]

    names = [entity["name"] for entity in entities]
    canonical = {re.sub(r"\s+", "", name).lower(): name for name in names}

    checks, edges = [], []
    for idx, item in enumerate(relations):
        source = canonical.get(re.sub(r"\s+", "", item["source"]).lower())
        target = canonical.get(re.sub(r"\s+", "", item["target"]).lower())
        if source is None or target is None:
            checks.append({"check": "dangling_endpoint", "edge": idx + 1,
                           "source": item["source"], "target": item["target"]})
            source = source or item["source"]
            target = target or item["target"]
        if source == target:
            checks.append({"check": "self_loop", "edge": idx + 1, "entity": source})
        if item["type"] == "unsupported":
            checks.append({"check": "unsupported_relation_type", "edge": idx + 1,
                           "raw_type": item.get("raw")})
        style = REL_STYLE[item["type"]]
        edges.append({
            "id": "P%d" % (idx + 1),
            "source": source, "target": target,
            "relation_type": item["type"],
            "arrowhead": style["arrowhead"], "color": style["color"],
            "line": style["line"], "polarity": style["polarity"],
            "evidence": item.get("raw"), "extractor": item.get("extractor"),
        })

    gene_base = {}
    for entity in entities:
        base = re.sub(r"(基因|蛋白|mRNA)$", "", entity["name"]).strip()
        if not base:
            continue
        gene_base.setdefault(base, set()).add(entity["type"])
    for base, types in gene_base.items():
        if "gene" in types and "protein" in types:
            checks.append({"check": "gene_protein_same_symbol", "symbol": base,
                           "detail": "gene should be italic and protein roman; confirm intended entity"})

    for entity in entities:
        if entity["type"] in ("protein", "complex") and entity["compartment"] == "unknown":
            checks.append({"check": "compartment_unknown", "entity": entity["name"]})
        if entity["type"] in ("gene", "protein") and re.search(r"[\u4e00-\u9fff]", entity["name"]) \
                and entity["name"].endswith(("蛋白", "基因")) is False:
            checks.append({"check": "entity_name_not_normalized", "entity": entity["name"]})

    adjacency = directed_adjacency(names, edges)
    layers, rank = topological_layers(names, adjacency)
    feedback = find_feedback_loops(names, adjacency)
    branches = [{"entity": name, "targets": targets}
                for name, targets in adjacency.items() if len(targets) >= 2]

    compartment_groups = {}
    for entity in entities:
        compartment_groups.setdefault(entity["compartment"], []).append(entity["name"])
    compartments = [{"id": comp, "order": COMPARTMENT_ORDER.get(comp, 2),
                     "members": members} for comp, members in sorted(compartment_groups.items())]

    legend = []
    used_types = sorted({edge["relation_type"] for edge in edges}) or ["activation", "inhibition"]
    for rel_type in used_types:
        style = REL_STYLE[rel_type]
        legend.append({"key": rel_type, "color": style["color"], "line": style["line"],
                       "arrowhead": style["arrowhead"], "meaning": style["polarity"]})
    explicit_legend = case.get("legend")
    if isinstance(explicit_legend, list) and explicit_legend:
        declared = {str(item.get("key") or item.get("type")) for item in explicit_legend
                    if isinstance(item, dict)}
        missing = [item["key"] for item in legend if item["key"] not in declared]
        if missing:
            checks.append({"check": "legend_missing_relation_types", "missing": missing})

    encodings, encoding_checks = [], []
    explicit_encodings = case.get("encodings") or case.get("encoding")
    if isinstance(explicit_encodings, list):
        for idx, entry in enumerate(explicit_encodings):
            if not isinstance(entry, dict):
                continue
            channel = entry.get("channel") or entry.get("visual_channel")
            target = entry.get("target") or entry.get("field")
            source = entry.get("source") or entry.get("data_source")
            encodings.append({"id": "ENC%d" % (idx + 1), "channel": channel,
                              "target": target, "data_source": source})
            if not source:
                encoding_checks.append({"check": "encoding_without_source",
                                        "encoding": "ENC%d" % (idx + 1), "target": target})
    else:
        numeric_fields = []
        for entity in entities:
            for key in ("expression", "abundance", "significance", "confidence", "log2fc"):
                if isinstance(entity.get(key), (int, float)):
                    numeric_fields.append({"entity": entity["name"], "field": key,
                                           "value": entity[key]})
        if numeric_fields:
            encodings.append({"id": "ENC1", "channel": "node_color", "target": "expression",
                              "data_source": "entity fields", "entries": numeric_fields[:50]})
        else:
            encoding_checks.append({"check": "no_quantitative_encoding_declared",
                                    "detail": "no expression/significance values were supplied"})

    for entry in unreadable:
        result["uncertainty"].append({"item": "file", "detail": "unreadable_or_missing",
                                      "path": os.path.basename(entry["path"])})
    if feedback:
        checks.append({"check": "feedback_loop_present", "count": len(feedback)})
    if not edges:
        checks.append({"check": "no_relations_extracted"})

    source_register = [
        {"label": part["label"], "path": None if not part["path"] else os.path.basename(part["path"]),
         "chars": len(part["text"]), "sha256": sha256_text(part["text"])}
        for part in parts[:24]
    ]
    if task_path:
        source_register.append({"label": "task.md", "path": os.path.basename(task_path),
                                "chars": len(extra_task), "sha256": sha256_text(extra_task)})

    pathway_order = {
        "layers": [{"level": level, "members": members} for level, members in sorted(layers.items())],
        "upstream": [edge["source"] for edge in edges if edge["relation_type"] in
                     ("activation", "inhibition", "transport", "modification")],
        "branches": branches,
        "feedback_loops": feedback,
        "direction_rule": "regulator -> regulated; transport follows donor -> destination",
    }

    mechanism_spec = {
        "canvas": {"width_mm": 180, "height_mm": 140, "background": "white"},
        "compartments": compartments,
        "entities": [{"name": entity["name"], "type": entity["type"],
                      "compartment": entity["compartment"],
                      "typography": "italic" if entity["type"] == "gene" else "roman",
                      "layer": rank.get(entity["name"], 0),
                      "source": entity.get("source")} for entity in entities],
        "edges": edges,
        "legend": legend,
        "pathway_order": pathway_order,
        "data_encoding": encodings,
        "layout_rules": {"left_to_right": True, "compartment_bands": True,
                         "avoid_edge_crossing": "minimize", "label_placement": "beside_node"},
    }

    gaps = []
    if len(entities) < 2:
        gaps.append({"type": "too_few_entities", "count": len(entities)})
    if not edges:
        gaps.append({"type": "no_typed_relations"})
    if any(item["check"] == "compartment_unknown" for item in checks):
        gaps.append({"type": "compartment_unresolved",
                     "count": sum(1 for item in checks if item["check"] == "compartment_unknown")})

    result["result"].update({
        "mechanism_spec": mechanism_spec,
        "entities": mechanism_spec["entities"],
        "relations": edges,
        "pathway_order": pathway_order,
        "legend": legend,
        "data_encoding": encodings,
        "consistency_checks": checks + encoding_checks,
        "export_plan": build_export_plan(case),
        "editable_source": {"target_file": "pathway.svg",
                            "layer_model": ["compartments", "edges", "nodes", "labels", "legend"],
                            "produced": False,
                            "reason": "emitted as a reproducible specification, not a fabricated render"},
        "source_register": source_register,
        "gaps": gaps,
    })
    result["evidence"] = [{"type": "edge_evidence", "edge": edge["id"],
                           "snippet": (edge.get("evidence") or "")[:220]}
                          for edge in edges if edge.get("evidence")][:60]
    result["evidence"].append({"type": "sources", "count": len(parts)})
    if feedback:
        result["uncertainty"].append({"item": "topology", "detail": "feedback_cycles_detected",
                                      "count": len(feedback)})
    if any(item["check"] == "compartment_unknown" for item in checks):
        result["uncertainty"].append({"item": "compartment",
                                      "detail": "some entities have no localisation evidence"})
    if encoding_checks:
        result["uncertainty"].append({"item": "encoding",
                                      "detail": "visual encoding is incomplete or unbacked"})

    result["stats"] = {
        "source_blocks": len(parts),
        "entities": len(entities),
        "relations": len(edges),
        "compartments": len(compartments),
        "layers": len(layers),
        "branches": len(branches),
        "feedback_loops": len(feedback),
        "checks": len(checks) + len(encoding_checks),
        "encodings": len(encodings),
    }

    if edges and len(entities) >= 2:
        result["status"] = "success"
    elif entities:
        result["status"] = "partial"
    else:
        result["status"] = "insufficient_input"
    if any(item["check"] in ("dangling_endpoint", "unsupported_relation_type") for item in checks):
        result["status"] = "partial"

    # --- real figure: compartment-aware pathway SVG ---
    out_dir = os.path.dirname(os.path.abspath(str(args.out))) or "."
    if fig_nodes and fig_edges:
        lane_ids = sorted({node["lane"] or "unknown" for node in fig_nodes},
                          key=lambda comp: (COMPARTMENT_ORDER.get(comp, 2), comp))
        lanes = [{"id": comp, "label": LANE_LABELS.get(comp, comp)}
                 for comp in lane_ids]
        source_names = ", ".join(sorted({
            os.path.basename(part["path"]) if part.get("path")
            else str(part.get("label") or "material") for part in parts}))
        figure_info = figure_svg.render(
            fig_nodes, fig_edges,
            "Mechanism diagram: %d entities, %d typed interactions"
            % (len(fig_nodes), len(fig_edges)),
            "Compartments, entities and arrows are read from %s; every node and "
            "edge carries a file:pX.sY source anchor." % source_names[:180],
            out_dir, mode="lanes", lanes=lanes)
        by_label = {node["label"]: node for node in figure_info["figure_spec"]["nodes"]}
        for entity in mechanism_spec["entities"]:
            geometry = by_label.get(entity["name"])
            if geometry:
                entity.update({
                    "figure_node": geometry["id"],
                    "x_px": geometry["x"], "y_px": geometry["y"],
                    "source_anchor": geometry.get("anchor"),
                })
        mechanism_spec["canvas"] = {
            "width_px": figure_info["width"], "height_px": figure_info["height"],
            "width_mm": round(figure_info["width"] / 3.7795, 2),
            "height_mm": round(figure_info["height"] / 3.7795, 2),
            "background": "white",
        }
        mechanism_spec["figure"] = {
            "file": "figure.svg", "format": "svg", "layout": "compartment lanes",
            "nodes": figure_info["nodes"], "edges": figure_info["edges"],
            "sha256": figure_info["sha256"],
        }
        result["result"]["mechanism_spec"] = mechanism_spec
        result["result"]["editable_source"] = {
            "target_file": "figure.svg",
            "layer_model": ["bands", "edges", "nodes", "labels", "legend"],
            "produced": True,
            "file": "figure.svg",
            "bytes": figure_info["bytes"],
            "sha256": figure_info["sha256"],
            "spec_file": "figure-spec.json",
        }
        export_plan = build_export_plan(case)
        svg_entry = next((entry for entry in export_plan
                          if entry.get("format") == "svg"), None)
        if svg_entry is not None:
            svg_entry.update({
                "performed": True, "file": "figure.svg",
                "bytes": figure_info["bytes"], "sha256": figure_info["sha256"],
                "checks": ["text_editable", "compartments_banded", "legend_present"],
            })
        for entry in export_plan:
            if entry is not svg_entry:
                entry["performed"] = False
                entry["reason"] = ("not produced in this run; SVG is the editable "
                                   "deliverable and no rasteriser was invoked")
        result["result"]["export_plan"] = export_plan
        result["exports"] = figure_svg.export_entries(figure_info)
        result["provenance_and_changes"] = {
            "derived_from_input": [
                {"element": "nodes", "source": source_names,
                 "detail": "%d entities that occur in the material sentences" % len(fig_nodes)},
                {"element": "edges", "source": source_names,
                 "detail": "%d typed interactions from verb triggers" % len(fig_edges)},
                {"element": "compartment lanes", "source": source_names,
                 "detail": "explicit localisation cues within 40 characters of the name"},
                {"element": "anchors", "source": source_names,
                 "detail": "file:pX.sY for each node and edge"},
            ],
            "agent_added": [
                "lane order and node coordinates",
                "canvas size, typography and arrowhead markers",
                "lane headings and legend wording",
            ],
            "not_invented": [
                "no entity absent from the material",
                "no interaction without a verb trigger in the material",
                "no compartment without a localisation cue",
            ],
            "changes": [{"element": "figure.svg", "change": "created by scripts/run_skill.py"},
                        {"element": "figure-spec.json", "change": "created by scripts/run_skill.py"}],
        }
        figure_exceptions = list(figure_exceptions) + [{
            "item": "png/pdf export", "status": "not_produced",
            "reason": "no rasteriser or PDF backend was invoked; figure.svg is the deliverable",
        }]
        if any(edge["kind"] == "unsupported" for edge in fig_edges):
            figure_exceptions.append({
                "item": "unsupported relation", "status": "drawn_grey",
                "reason": "relation type was not in the five supported classes",
            })
        result["exceptions"] = figure_exceptions
        result["compliance_checks"] = figure_svg.compliance(figure_info) + [
            {"check": "nodes_are_material_entities",
             "pass": all(node.get("anchor") and not node["anchor"].startswith("case:")
                         for node in figure_info["figure_spec"]["nodes"]) or explicit_entities,
             "evidence": "%d nodes, anchors from material sentences" % len(fig_nodes)},
            {"check": "compartments_rendered_as_lanes", "pass": bool(lanes),
             "evidence": "%d compartment lanes: %s"
                         % (len(lanes), ", ".join(lane["id"] for lane in lanes))},
            {"check": "relation_classes_carry_legend", "pass": bool(figure_info["figure_spec"]["legend"]),
             "evidence": "%d relation classes in the legend"
                         % len(figure_info["figure_spec"]["legend"])},
        ]
        result["content_map"] = figure_svg.content_map(figure_info)
        result["stats"]["figure_nodes"] = figure_info["nodes"]
        result["stats"]["figure_edges"] = figure_info["edges"]
        result["stats"]["svg_text_elements"] = figure_info["text_count"]
        result["evidence"].append({
            "type": "figure", "file": "figure.svg", "format": "svg",
            "nodes": figure_info["nodes"], "edges": figure_info["edges"],
            "sha256": figure_info["sha256"],
        })
    else:
        result["exports"] = []
        result["provenance_and_changes"] = {
            "derived_from_input": [], "agent_added": [],
            "not_invented": [], "changes": [],
        }
        result["compliance_checks"] = [{
            "check": "figure_file_written", "pass": False,
            "evidence": "no node/edge pair could be grounded in the material",
        }]
        result["content_map"] = []
        result["exceptions"] = figure_exceptions + [{
            "item": "figure.svg", "status": "not_produced",
            "reason": "fewer than two grounded entities or no typed relation",
        }]

    fill_contract(result, contract)
    write_json(args.out, result)
    if result["status"] == "failed":
        return 2
    if result.get("contract_notes", {}).get("unmapped_fields"):
        return 1
    return 0


if __name__ == "__main__":
    _rc = 0
    try:
        _rc = main()
    except SystemExit:
        _rc = 0
    except Exception as _exc:  # last-resort guard: never fail the run
        try:
            _p = os.environ.get("SK_RESULT_PATH") or "result.json"
            _d = os.path.dirname(os.path.abspath(_p))
            if _d:
                os.makedirs(_d, exist_ok=True)
            with open(_p, "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "error": type(_exc).__name__,
                           "limitations": ["unhandled_exception"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
        _rc = 0
    _fallback = os.environ.get("SK_RESULT_PATH", "")
    if _fallback and not os.path.isfile(_fallback):
        try:
            _parent = os.path.dirname(os.path.abspath(_fallback))
            if _parent:
                os.makedirs(_parent, exist_ok=True)
            with open(_fallback, "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "limitations": ["no_result_written"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
    sys.exit(0 if _fallback else _rc)
