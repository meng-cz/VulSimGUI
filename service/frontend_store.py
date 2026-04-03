from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass


_NAME_GUARD = r"A-Za-z0-9_"


@dataclass
class FrontendConfigItem:
    name: str
    value: str
    comment: str = ""

    @property
    def realvalue(self) -> str:
        text = (self.value or "").strip()
        return text if text.isdigit() else ""


@dataclass
class FrontendBundleItem:
    name: str
    comment: str
    definition: str
    tags: str = ""


@dataclass
class FrontendDebugPointItem:
    name: str
    expr: str
    comment: str = ""
    trigger: str = ""
    kind: str = "wave"


class FrontendStore:
    """
    Frontend-only local data source.
    It keeps the UI usable before the real backend is ready.
    """

    def __init__(self, project_name: str = "frontend_demo", seed_demo: bool = True):
        self.project_name = project_name
        self._configs: dict[str, FrontendConfigItem] = {}
        self._bundles: dict[str, FrontendBundleItem] = {}
        self._modules: dict[str, dict] = {}
        self._debug_points: dict[str, FrontendDebugPointItem] = {}
        if seed_demo:
            self.seed_defaults()

    def reset(self, project_name: str | None = None) -> None:
        self.project_name = (project_name or "frontend_demo").strip() or "frontend_demo"
        self._configs.clear()
        self._bundles.clear()
        self._modules.clear()
        self._debug_points.clear()
        self.seed_defaults()

    def seed_defaults(self) -> None:
        for item in [
            FrontendConfigItem("ADDR_W", "32", "地址宽度"),
            FrontendConfigItem("DATA_W", "64", "数据宽度"),
            FrontendConfigItem("BURST_LEN", "16", "突发长度"),
            FrontendConfigItem("CACHE_BYTES", "DATA_W * BURST_LEN", "缓存大小表达式"),
        ]:
            self._configs[item.name] = item

        bundle_definition = json.dumps(
            {
                "members": [
                    {
                        "name": "addr",
                        "comment": "地址",
                        "type": "",
                        "value": "0",
                        "uint_length": "ADDR_W",
                        "dims": [],
                    },
                    {
                        "name": "data",
                        "comment": "数据",
                        "type": "",
                        "value": "0",
                        "uint_length": "DATA_W",
                        "dims": [],
                    },
                ],
                "enum_members": [],
                "is_alias": False,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        self._bundles["AXI_Lite_Req"] = FrontendBundleItem(
            name="AXI_Lite_Req",
            comment="AXI-Lite 请求线束示例",
            definition=bundle_definition,
            tags="frontend-demo",
        )

        self._modules = {
            "Core_Logic": {
                "name": "Core_Logic",
                "comment": "核心逻辑模块",
                "submodules": [
                    {"inst": "CPU_Cluster_A", "module": "CPU", "comment": ""},
                    {"inst": "Memory_Bus_64", "module": "Bus64", "comment": ""},
                ],
                "local_cfgs": [],
                "local_harnesses": [],
                "rpcs": [],
                "pipe_ports": [],
                "pipes": [],
                "storages": [],
                "reqsvc_conns": [],
                "instpipe_conns": [],
                "block_conns": [],
                "orders": [],
                "clock_blocks": [],
                "service_blocks": [],
                "subreq_blocks": [],
                "helper_code": [],
            },
            "CPU": {
                "name": "CPU",
                "comment": "CPU 子模块",
                "submodules": [],
                "local_cfgs": [],
                "local_harnesses": [],
                "rpcs": [],
                "pipe_ports": [],
                "pipes": [],
                "storages": [],
                "reqsvc_conns": [],
                "instpipe_conns": [],
                "block_conns": [],
                "orders": [],
                "clock_blocks": [],
                "service_blocks": [],
                "subreq_blocks": [],
                "helper_code": [],
            },
            "Bus64": {
                "name": "Bus64",
                "comment": "总线子模块",
                "submodules": [],
                "local_cfgs": [],
                "local_harnesses": [],
                "rpcs": [],
                "pipe_ports": [],
                "pipes": [],
                "storages": [],
                "reqsvc_conns": [],
                "instpipe_conns": [],
                "block_conns": [],
                "orders": [],
                "clock_blocks": [],
                "service_blocks": [],
                "subreq_blocks": [],
                "helper_code": [],
            },
        }

        self._debug_points = {
            "cpu_pc_trace": FrontendDebugPointItem(
                name="cpu_pc_trace",
                expr="CPU_Cluster_A.pc",
                comment="观察 CPU 当前 PC 变化",
                trigger="posedge(clk)",
                kind="wave",
            ),
            "bus_req_valid": FrontendDebugPointItem(
                name="bus_req_valid",
                expr="Memory_Bus_64.req_valid",
                comment="总线请求有效信号检查点",
                trigger="always",
                kind="wave",
            ),
        }

    def list_configs(self) -> list[dict]:
        return [
            {
                "name": item.name,
                "value": item.value,
                "comment": item.comment,
                "realvalue": item.realvalue,
            }
            for item in sorted(self._configs.values(), key=lambda x: x.name.lower())
        ]

    def import_configs(self, config_data_list: list[dict]) -> None:
        self._configs.clear()
        for cfg in config_data_list or []:
            name = (cfg.get("name") or "").strip()
            if not name:
                continue
            value = cfg.get("value")
            if value is None:
                value = cfg.get("expr", "")
            self._configs[name] = FrontendConfigItem(
                name=name,
                value=str(value or ""),
                comment=str(cfg.get("comment", "") or ""),
            )

    def add_config(self, name: str, value: str, comment: str) -> None:
        if name in self._configs:
            raise ValueError(f"配置项“{name}”已存在。")
        self._configs[name] = FrontendConfigItem(name=name, value=value, comment=comment)

    def update_config(self, name: str, value: str) -> None:
        item = self._require_config(name)
        item.value = value

    def comment_config(self, name: str, comment: str) -> None:
        item = self._require_config(name)
        item.comment = comment

    def rename_config(self, old_name: str, new_name: str, value: str, comment: str) -> None:
        item = self._require_config(old_name)
        if old_name != new_name and new_name in self._configs:
            raise ValueError(f"配置项“{new_name}”已存在。")

        self._configs.pop(old_name, None)
        item.name = new_name
        item.value = value
        item.comment = comment
        self._configs[new_name] = item

    def remove_configs(self, names: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
        remove_set = {n for n in names if n}
        refs = self._build_forward_refs()
        reverse = self._build_reverse_refs(refs)
        bundle_refs = self._build_bundle_config_reverse_refs()

        success: list[str] = []
        failed: list[tuple[str, str]] = []

        for name in names:
            if name not in self._configs:
                failed.append((name, "配置项不存在。"))
                continue

            external_refs = sorted(x for x in reverse.get(name, set()) if x not in remove_set)
            bundle_ref_names = sorted(x for x in bundle_refs.get(name, set()) if x not in remove_set)
            if external_refs or bundle_ref_names:
                display_refs = external_refs + [f"{bundle_name}（线束）" for bundle_name in bundle_ref_names]
                failed.append((name, f"配置项仍被引用：{', '.join(display_refs)}"))
                continue

            self._configs.pop(name, None)
            success.append(name)

        return success, failed

    def list_config_refs(self, name: str, reverse: bool = False) -> dict:
        self._require_config(name)
        refs = self._build_forward_refs()
        graph = self._build_reverse_refs(refs) if reverse else refs
        bundle_refs = self._build_bundle_config_reverse_refs() if reverse else {}

        visited: set[str] = set()
        ordered: list[tuple[str, str]] = []
        stack = list(graph.get(name, set()))

        while stack:
            current = stack.pop()
            if current in visited or current == name or current not in self._configs:
                continue
            visited.add(current)
            ordered.append(("配置", current))
            stack.extend(sorted(graph.get(current, set()), reverse=True))

        if reverse:
            for bundle_name in sorted(bundle_refs.get(name, set())):
                ordered.append(("线束", bundle_name))

        ordered.sort(key=lambda item: (item[0] != "配置", item[1].lower()))
        return {
            "names": [item_name for _, item_name in ordered],
            "kinds": [kind for kind, _ in ordered],
            "childs": [self._listref_child_text(kind, item_name, graph) for kind, item_name in ordered],
            "values": [self._listref_value_text(kind, item_name) for kind, item_name in ordered],
            "realvalues": [self._listref_realvalue_text(kind, item_name) for kind, item_name in ordered],
        }

    def list_bundles(self) -> list[dict]:
        return [
            {
                "name": item.name,
                "comment": item.comment,
                "tags": item.tags,
                "definition": item.definition,
            }
            for item in sorted(self._bundles.values(), key=lambda x: x.name.lower())
        ]

    def import_bundles(self, bundle_data_list: list[dict]) -> None:
        self._bundles.clear()
        for bundle in bundle_data_list or []:
            name = (bundle.get("name") or "").strip()
            if not name:
                continue
            definition = (bundle.get("definition") or "").strip()
            if not definition:
                definition = self._bundle_definition_from_ui_data(bundle)
            self._bundles[name] = FrontendBundleItem(
                name=name,
                comment=str(bundle.get("comment", "") or ""),
                definition=definition,
                tags=str(bundle.get("tags", "") or ""),
            )

    def add_bundle(self, name: str, comment: str, definition: str, tags: str = "") -> None:
        if name in self._bundles:
            raise ValueError(f"线束“{name}”已存在。")
        self._bundles[name] = FrontendBundleItem(name=name, comment=comment, definition=definition, tags=tags)

    def update_bundle(self, old_name: str, new_name: str, comment: str, definition: str, tags: str = "") -> None:
        item = self._require_bundle(old_name)
        if old_name != new_name and new_name in self._bundles:
            raise ValueError(f"线束“{new_name}”已存在。")

        self._bundles.pop(old_name, None)
        item.name = new_name
        item.comment = comment
        item.definition = definition
        item.tags = tags
        self._bundles[new_name] = item

    def remove_bundles(self, names: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
        success: list[str] = []
        failed: list[tuple[str, str]] = []

        for name in names:
            if name not in self._bundles:
                failed.append((name, "线束不存在。"))
                continue
            self._bundles.pop(name, None)
            success.append(name)

        return success, failed

    def list_modules(self) -> dict[str, dict]:
        return copy.deepcopy(self._modules)

    def list_debug_points(self) -> list[dict]:
        return [
            {
                "name": item.name,
                "expr": item.expr,
                "comment": item.comment,
                "trigger": item.trigger,
                "kind": item.kind,
            }
            for item in sorted(self._debug_points.values(), key=lambda x: x.name.lower())
        ]

    def import_modules(self, modules: dict[str, dict] | list[dict]) -> None:
        if isinstance(modules, dict):
            self._modules = copy.deepcopy(modules)
            return

        loaded: dict[str, dict] = {}
        for module_data in modules or []:
            name = (module_data.get("name") or "").strip()
            if name:
                loaded[name] = copy.deepcopy(module_data)
        self._modules = loaded

    def import_debug_points(self, debug_points: list[dict]) -> None:
        self._debug_points.clear()
        for row in debug_points or []:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            self._debug_points[name] = FrontendDebugPointItem(
                name=name,
                expr=str(row.get("expr", "") or ""),
                comment=str(row.get("comment", "") or ""),
                trigger=str(row.get("trigger", "") or ""),
                kind=str(row.get("kind", "wave") or "wave"),
            )

    def add_debug_point(self, data: dict) -> None:
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("调试检查点名称不能为空。")
        if name in self._debug_points:
            raise ValueError(f"调试检查点“{name}”已存在。")
        self._debug_points[name] = FrontendDebugPointItem(
            name=name,
            expr=str(data.get("expr", "") or ""),
            comment=str(data.get("comment", "") or ""),
            trigger=str(data.get("trigger", "") or ""),
            kind=str(data.get("kind", "wave") or "wave"),
        )

    def update_debug_point(self, old_name: str, data: dict) -> None:
        item = self._debug_points.get(old_name)
        if item is None:
            raise ValueError(f"调试检查点“{old_name}”不存在。")

        new_name = (data.get("name") or old_name).strip()
        if not new_name:
            raise ValueError("调试检查点名称不能为空。")
        if new_name != old_name and new_name in self._debug_points:
            raise ValueError(f"调试检查点“{new_name}”已存在。")

        self._debug_points.pop(old_name, None)
        item.name = new_name
        item.expr = str(data.get("expr", "") or "")
        item.comment = str(data.get("comment", "") or "")
        item.trigger = str(data.get("trigger", "") or "")
        item.kind = str(data.get("kind", "wave") or "wave")
        self._debug_points[new_name] = item

    def remove_debug_points(self, names: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
        success: list[str] = []
        failed: list[tuple[str, str]] = []
        for name in names or []:
            if name not in self._debug_points:
                failed.append((name, "调试检查点不存在。"))
                continue
            self._debug_points.pop(name, None)
            success.append(name)
        return success, failed

    def get_config_detail(self, name: str) -> dict:
        item = self._require_config(name)
        refs = self._build_forward_refs()
        reverse = self._build_reverse_refs(refs)
        bundle_refs = self._build_bundle_config_reverse_refs()

        return {
            "name": item.name,
            "comment": item.comment,
            "expr": item.value,
            "realvalue": item.realvalue,
            "depends_on_tree": self._build_config_tree(name, refs, {name}),
            "required_by_tree": self._build_config_tree(name, reverse, {name}),
            "bundle_refs": [self._make_bundle_ref_node(bundle_name) for bundle_name in sorted(bundle_refs.get(name, set()))],
        }

    def get_bundle_detail(self, name: str) -> dict:
        item = self._require_bundle(name)
        definition = self._parse_bundle_definition(item.definition)
        bundle_refs = self._build_bundle_forward_refs()
        reverse_refs = self._build_bundle_reverse_refs(bundle_refs)
        config_refs = self._build_bundle_config_refs()

        members = []
        for member in definition.get("members", []) or []:
            dims = member.get("dims", []) or []
            members.append({
                "name": str(member.get("name", "") or ""),
                "type": str(member.get("type", "") or ""),
                "uint_length": str(member.get("uint_length", "") or ""),
                "comment": str(member.get("comment", "") or ""),
                "value": str(member.get("value", "") or ""),
                "dims": dims,
            })

        enums = []
        for enum_member in definition.get("enum_members", []) or []:
            enums.append({
                "name": str(enum_member.get("name", "") or ""),
                "comment": str(enum_member.get("comment", "") or ""),
                "value": str(enum_member.get("value", "") or ""),
            })

        alias_target = ""
        if definition.get("is_alias") and members:
            alias_target = str(members[0].get("type", "") or "")

        return {
            "name": item.name,
            "comment": item.comment,
            "tags": item.tags,
            "definition": item.definition,
            "is_alias": bool(definition.get("is_alias")),
            "alias_target": alias_target,
            "members": members,
            "enums": enums,
            "depends_on_tree": self._build_bundle_tree(name, bundle_refs, {name}),
            "required_by_tree": self._build_bundle_tree(name, reverse_refs, {name}),
            "config_refs": [self._make_config_ref_node(config_name) for config_name in sorted(config_refs.get(name, set()))],
        }

    def _require_config(self, name: str) -> FrontendConfigItem:
        item = self._configs.get(name)
        if item is None:
            raise ValueError(f"配置项“{name}”不存在。")
        return item

    def _require_bundle(self, name: str) -> FrontendBundleItem:
        item = self._bundles.get(name)
        if item is None:
            raise ValueError(f"线束“{name}”不存在。")
        return item

    def _listref_child_text(self, kind: str, name: str, graph: dict[str, set[str]]) -> str:
        if kind == "配置":
            return ", ".join(sorted(graph.get(name, set())))
        bundle_graph = self._build_bundle_config_refs()
        return ", ".join(sorted(bundle_graph.get(name, set())))

    def _listref_value_text(self, kind: str, name: str) -> str:
        if kind == "配置":
            return self._configs[name].value
        return self._bundles[name].comment

    def _listref_realvalue_text(self, kind: str, name: str) -> str:
        if kind == "配置":
            return self._configs[name].realvalue
        return ""

    def _build_forward_refs(self) -> dict[str, set[str]]:
        refs: dict[str, set[str]] = {name: set() for name in self._configs}
        names = sorted(self._configs.keys(), key=len, reverse=True)

        for name, item in self._configs.items():
            refs[name] = self._extract_config_refs_from_text(item.value or "", exclude=name, candidates=names)

        return refs

    def _build_reverse_refs(self, refs: dict[str, set[str]]) -> dict[str, set[str]]:
        reverse: dict[str, set[str]] = {name: set() for name in self._configs}
        for name, children in refs.items():
            for child in children:
                if child in reverse:
                    reverse[child].add(name)
        return reverse

    def _build_bundle_config_refs(self) -> dict[str, set[str]]:
        refs: dict[str, set[str]] = {name: set() for name in self._bundles}
        candidates = sorted(self._configs.keys(), key=len, reverse=True)

        for name, item in self._bundles.items():
            definition = self._parse_bundle_definition(item.definition)
            found: set[str] = set()

            for member in definition.get("members", []) or []:
                found.update(self._extract_config_refs_from_text(member.get("uint_length", ""), candidates=candidates))
                found.update(self._extract_config_refs_from_text(member.get("value", ""), candidates=candidates))
                for dim in member.get("dims", []) or []:
                    found.update(self._extract_config_refs_from_text(dim, candidates=candidates))

            for enum_member in definition.get("enum_members", []) or []:
                found.update(self._extract_config_refs_from_text(enum_member.get("value", ""), candidates=candidates))

            refs[name] = found

        return refs

    def _build_bundle_config_reverse_refs(self) -> dict[str, set[str]]:
        reverse: dict[str, set[str]] = {name: set() for name in self._configs}
        for bundle_name, config_refs in self._build_bundle_config_refs().items():
            for config_name in config_refs:
                if config_name in reverse:
                    reverse[config_name].add(bundle_name)
        return reverse

    def _build_bundle_forward_refs(self) -> dict[str, set[str]]:
        refs: dict[str, set[str]] = {name: set() for name in self._bundles}
        for name, item in self._bundles.items():
            definition = self._parse_bundle_definition(item.definition)
            found: set[str] = set()
            for member in definition.get("members", []) or []:
                target_type = str(member.get("type", "") or "").strip()
                if target_type and target_type in self._bundles and target_type != name:
                    found.add(target_type)
            refs[name] = found
        return refs

    def _build_bundle_reverse_refs(self, refs: dict[str, set[str]]) -> dict[str, set[str]]:
        reverse: dict[str, set[str]] = {name: set() for name in self._bundles}
        for name, children in refs.items():
            for child in children:
                if child in reverse:
                    reverse[child].add(name)
        return reverse

    def _extract_config_refs_from_text(self, text, exclude: str | None = None,
                                       candidates: list[str] | None = None) -> set[str]:
        expr = str(text or "")
        names = candidates or sorted(self._configs.keys(), key=len, reverse=True)
        found: set[str] = set()
        for candidate in names:
            if exclude and candidate == exclude:
                continue
            pattern = rf"(?<![{_NAME_GUARD}]){re.escape(candidate)}(?![{_NAME_GUARD}])"
            if re.search(pattern, expr):
                found.add(candidate)
        return found

    def _build_config_tree(self, name: str, graph: dict[str, set[str]], path: set[str]) -> list[dict]:
        nodes: list[dict] = []
        for child_name in sorted(graph.get(name, set())):
            if child_name not in self._configs:
                continue
            node = self._make_config_ref_node(child_name)
            if child_name not in path:
                node["children"] = self._build_config_tree(child_name, graph, path | {child_name})
            nodes.append(node)
        return nodes

    def _build_bundle_tree(self, name: str, graph: dict[str, set[str]], path: set[str]) -> list[dict]:
        nodes: list[dict] = []
        for child_name in sorted(graph.get(name, set())):
            if child_name not in self._bundles:
                continue
            node = self._make_bundle_ref_node(child_name)
            if child_name not in path:
                node["children"] = self._build_bundle_tree(child_name, graph, path | {child_name})
            nodes.append(node)
        return nodes

    def _make_config_ref_node(self, name: str) -> dict:
        item = self._require_config(name)
        return {
            "kind": "config",
            "name": item.name,
            "comment": item.comment,
            "expr": item.value,
            "realvalue": item.realvalue,
            "children": [],
        }

    def _make_bundle_ref_node(self, name: str) -> dict:
        item = self._require_bundle(name)
        definition = self._parse_bundle_definition(item.definition)
        summary = self._bundle_summary_from_definition(definition)
        return {
            "kind": "harness",
            "name": item.name,
            "comment": item.comment,
            "summary": summary,
            "children": [],
        }

    def _bundle_summary_text(self, detail: dict) -> str:
        if detail.get("is_alias"):
            target = detail.get("alias_target", "") or "（未指定）"
            return f"别名 -> {target}"
        enums = detail.get("enums", []) or []
        if enums:
            return f"枚举定义，共 {len(enums)} 项"
        members = detail.get("members", []) or []
        return f"成员定义，共 {len(members)} 项"

    def _bundle_summary_from_definition(self, definition: dict) -> str:
        if definition.get("is_alias"):
            members = definition.get("members", []) or []
            target = ""
            if members:
                target = str(members[0].get("type", "") or "")
            return f"别名 -> {target or '（未指定）'}"

        enums = definition.get("enum_members", []) or []
        if enums:
            return f"枚举定义，共 {len(enums)} 项"

        members = definition.get("members", []) or []
        return f"成员定义，共 {len(members)} 项"

    def _parse_bundle_definition(self, definition_json: str | None) -> dict:
        if not definition_json:
            return {"members": [], "enum_members": [], "is_alias": False}
        try:
            obj = json.loads(definition_json)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        return {"members": [], "enum_members": [], "is_alias": False}

    def _bundle_definition_from_ui_data(self, bundle: dict) -> str:
        members_out = []
        for member in bundle.get("members", []) or []:
            member_type = str(member.get("type", "") or "").strip()
            uint_length = "" if member_type else str(member.get("int_len", "") or "").strip()
            members_out.append({
                "name": str(member.get("name", "") or ""),
                "comment": str(member.get("comment", "") or ""),
                "type": member_type,
                "value": str(member.get("default", "") or ""),
                "uint_length": uint_length,
                "dims": self._normalize_dims(member.get("dims", [])),
            })

        enums_out = []
        for enum_member in bundle.get("enums", []) or []:
            enums_out.append({
                "name": str(enum_member.get("name", "") or ""),
                "comment": str(enum_member.get("comment", "") or ""),
                "value": str(enum_member.get("value", "") or ""),
            })

        return json.dumps(
            {
                "members": members_out if not enums_out else [],
                "enum_members": enums_out,
                "is_alias": bool(bundle.get("alias", False)),
            },
            ensure_ascii=False,
        )

    def _normalize_dims(self, dims_value) -> list:
        if dims_value is None:
            return []
        if isinstance(dims_value, list):
            return [self._normalize_dim_item(item) for item in dims_value if str(item).strip() != ""]

        text = str(dims_value).strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1].strip()
        if not text:
            return []
        return [self._normalize_dim_item(item) for item in re.split(r"[,\s]+", text) if item.strip()]

    def _normalize_dim_item(self, value):
        text = str(value).strip()
        if re.fullmatch(r"\d+", text):
            return int(text)
        return text
