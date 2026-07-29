# -*- coding: utf-8 -*-
"""OpenAPI 2.0 (Swagger) → 3.0 转换器 (ti4-OPENAPI).

背景:
  - flasgger 0.9.7.1 内部只产 OpenAPI 2.0 spec (因 view_func docstring YAML
    模板是 2.0 格式, 改了会破坏现有 /apispec_1.json 兼容性)
  - 业界 2024+ 主流工具链 (Stoplight / Redoc / openapi-generator) 倾向 3.0
  - 本模块提供轻量级 2.0→3.0 转换, 不引外部库 (避免供应链与体积)
  - 输出规范 OpenAPI 3.0.3 (https://spec.openapis.org/oas/v3.0.3)

关键映射 (Swagger 2.0 → OpenAPI 3.0):
  - swagger: 2.0                              → openapi: 3.0.3
  - host + basePath + schemes                 → servers: [{url, description}]
  - definitions: {...}                        → components.schemas: {...}
  - securityDefinitions: {...}                → components.securitySchemes: {...}
  - parameters: [{in: body, schema: ...}]     → requestBody: {required, content: {application/json: {schema}}}
  - responses: {200: {schema: ...}}           → responses: {200: {content: {application/json: {schema}}}}
  - responses: {200: {description: ...}}      → responses: {200: {description: ...}} (无 schema 时保持)
  - 顶层 security / tags / info / paths       → 保留 (3.0 兼容)

业务场景 (OrangeServer):
  - 路由 docstring 只含 description + tags + responses (200/401/500)
  - 无 parameters (表单参数走 csrf token, 不在 OpenAPI 暴露)
  - 无 securityDefinitions (cookie session + CSRF 由 flasgger 之外的中间件处理)
  - 所以本转换器对 OrangeServer 业务是 100% 兼容, 同时通用 2.0 也能转
"""
import copy
from typing import Any, Dict, List, Tuple


# OpenAPI 3.0 规范版本 (固定)
OPENAPI_3_VERSION = "3.0.3"

# 业务响应码 → HTTP 状态码映射 (OpenAPI responses 用字符串 key)
_RESPONSE_KEYS_KEEP_STR = True  # '200' / '401' / '500' 保持字符串形式


def _build_servers(spec2: Dict[str, Any]) -> List[Dict[str, str]]:
    """从 swagger 2.0 的 host + basePath + schemes 构造 OpenAPI 3.0 servers.

    优先级: schemes[0] + host + basePath → url
    若缺 host 但有 basePath, 用相对 URL (OpenAPI 3.0 支持 relative URL, 由客户端解析)
      - 多个 schemes: 产多条 server, 让 client 选
      - 无 schemes: 默认 https 一条
    """
    host = (spec2.get("host") or "").strip()
    base_path = (spec2.get("basePath") or "/").strip() or "/"
    schemes = spec2.get("schemes") or []
    servers: List[Dict[str, str]] = []
    if host:
        # 绝对 URL: scheme://host{basePath}
        for scheme in (schemes or ["https"]):
            url = f"{scheme}://{host}{base_path}"
            servers.append({"url": url, "description": f"{scheme} protocol"})
    else:
        # 无 host: 产相对 URL, OpenAPI 3.0 支持 (RFC 3986 relative reference)
        # OrangeServer 业务用 Nginx 反代, host 动态决定, relative URL 最合适
        url = base_path if base_path.startswith("/") else "/" + base_path
        servers.append({"url": url, "description": "relative URL (server-agnostic)"})
    if not servers:
        servers.append({"url": "/", "description": "default"})
    return servers


def _rewrite_refs(obj):
    """递归把所有 $ref 从 2.0 路径 (#/definitions/X) 改写到 3.0 路径 (#/components/schemas/X).

    2.0 spec 引用路径:
      - #/definitions/X    → #/components/schemas/X
      - #/parameters/X     → #/components/parameters/X
      - #/responses/X      → #/components/responses/X

    3.0 规范要求引用统一放 components/ 下, 不重写会引用失效.
    仅改 ref 路径字符串, 不动 schema 其它结构.
    """
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            if k == '$ref' and isinstance(v, str):
                # #/definitions/Foo → #/components/schemas/Foo
                if v.startswith('#/definitions/'):
                    v = '#/components/schemas/' + v[len('#/definitions/'):]
                elif v.startswith('#/parameters/'):
                    v = '#/components/parameters/' + v[len('#/parameters/'):]
                elif v.startswith('#/responses/'):
                    v = '#/components/responses/' + v[len('#/responses/'):]
                new[k] = v
            else:
                new[k] = _rewrite_refs(v)
        return new
    if isinstance(obj, list):
        return [_rewrite_refs(x) for x in obj]
    return obj


def _convert_responses(responses2: Dict[str, Any]) -> Dict[str, Any]:
    """转换单个路径项的 responses 字段.

    Swagger 2.0 格式: {200: {description, schema?}, 401: {description}, ...}
    OpenAPI 3.0 格式: {200: {description, content?: {application/json: {schema}}}, ...}

    若响应含 schema, 包到 content.application/json.schema; 否则保持 description.
    """
    if not responses2:
        return {}
    responses3: Dict[str, Any] = {}
    for code, resp in responses2.items():
        if not isinstance(resp, dict):
            responses3[str(code)] = resp
            continue
        resp3: Dict[str, Any] = {}
        if "description" in resp:
            resp3["description"] = resp["description"]
        if "schema" in resp:
            # 2.0 schema → 3.0 content.application/json.schema
            resp3["content"] = {
                "application/json": {
                    "schema": resp["schema"],
                }
            }
        # headers / examples 在 OrangeServer 业务不用, 跳过
        for k in ("headers", "examples"):
            if k in resp:
                resp3[k] = resp[k]
        responses3[str(code)] = resp3
    return responses3


def _convert_parameters(params: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """分离 parameters 中的 body/formData vs path/query/header.

    返回: (非 body 参数列表, requestBody dict 或 {})
    Swagger 2.0 中 in: body 的参数需转 3.0 的 requestBody.
    in: formData 也合并到 requestBody (application/x-www-form-urlencoded).
    """
    if not params:
        return [], {}
    keep: List[Dict[str, Any]] = []
    body_params: List[Dict[str, Any]] = []
    form_params: List[Dict[str, Any]] = []
    for p in params:
        if not isinstance(p, dict):
            keep.append(p)
            continue
        loc = p.get("in")
        if loc == "body":
            body_params.append(p)
        elif loc == "formData":
            form_params.append(p)
        else:
            # path / query / header — 3.0 字段名微调, 主体兼容
            p3 = dict(p)
            # required 字段在 3.0 仍兼容
            keep.append(p3)
    request_body: Dict[str, Any] = {}
    if body_params:
        # 多 body 合并: 取第一个的 schema 作 root, 后续做 properties
        if len(body_params) == 1:
            schema = body_params[0].get("schema", {})
            required = bool(body_params[0].get("required", False))
        else:
            # 合并 schema: properties 合并
            properties: Dict[str, Any] = {}
            required_list: List[str] = []
            for bp in body_params:
                name = bp.get("name", "")
                if not name:
                    continue
                bp_schema = bp.get("schema", {})
                if "$ref" in bp_schema:
                    properties[name] = bp_schema
                elif "type" in bp_schema:
                    properties[name] = {k: v for k, v in bp_schema.items() if k != "name"}
                if bp.get("required"):
                    required_list.append(name)
            schema = {"type": "object", "properties": properties}
            if required_list:
                schema["required"] = required_list
            required = True
        request_body = {
            "required": required,
            "content": {
                "application/json": {
                    "schema": schema,
                }
            }
        }
    elif form_params:
        # formData: x-www-form-urlencoded
        properties: Dict[str, Any] = {}
        required_list: List[str] = []
        for fp in form_params:
            name = fp.get("name", "")
            if not name:
                continue
            properties[name] = {k: v for k, v in fp.items() if k not in ("name", "in")}
            if fp.get("required"):
                required_list.append(name)
        schema = {"type": "object", "properties": properties}
        if required_list:
            schema["required"] = required_list
        request_body = {
            "required": bool(required_list),
            "content": {
                "application/x-www-form-urlencoded": {
                    "schema": schema,
                }
            }
        }
    return keep, request_body


def _convert_path_item(path_item2: Dict[str, Any]) -> Dict[str, Any]:
    """转换单个路径项 (e.g. {'/x': {get: {...}, post: {...}, parameters: [...]}})."""
    if not isinstance(path_item2, dict):
        return path_item2
    item3: Dict[str, Any] = {}
    # 顶层 parameters (path-level) 先转换
    if "parameters" in path_item2:
        keep, req_body = _convert_parameters(path_item2["parameters"])
        if keep:
            item3["parameters"] = keep
        if req_body:
            item3["requestBody"] = req_body
    # 各个 HTTP 方法
    for method, op in path_item2.items():
        if method in ("parameters",):
            continue
        if method.lower() not in ("get", "post", "put", "delete", "patch", "head", "options"):
            # 可能是 summary/description 等顶层字段, 保留
            item3[method] = op
            continue
        if not isinstance(op, dict):
            item3[method] = op
            continue
        op3: Dict[str, Any] = dict(op)
        # parameters
        if "parameters" in op3:
            keep, req_body = _convert_parameters(op3["parameters"])
            if keep:
                op3["parameters"] = keep
            else:
                op3.pop("parameters", None)
            if req_body:
                op3["requestBody"] = req_body
        # responses
        if "responses" in op3:
            op3["responses"] = _convert_responses(op3["responses"])
        # consumes/produces 在 3.0 中移到 requestBody.content / responses.content, 删除顶层
        op3.pop("consumes", None)
        op3.pop("produces", None)
        item3[method] = op3
    return item3


def convert_swagger2_to_openapi3(spec2: Dict[str, Any]) -> Dict[str, Any]:
    """主入口: 把 OpenAPI 2.0 (Swagger) spec dict 转 OpenAPI 3.0 dict.

    Args:
        spec2: OpenAPI 2.0 spec dict (含 'swagger': '2.0' 字段)

    Returns:
        OpenAPI 3.0 spec dict (含 'openapi': '3.0.3' 字段)

    不可变: 输入 spec2 不会被修改 (内部 deep copy)
    """
    if not isinstance(spec2, dict):
        raise TypeError(f"spec2 must be dict, got {type(spec2).__name__}")
    spec2 = copy.deepcopy(spec2)
    spec3: Dict[str, Any] = {}

    # 1. openapi 版本
    spec3["openapi"] = OPENAPI_3_VERSION

    # 2. info (保持不变, 3.0 兼容)
    if "info" in spec2:
        spec3["info"] = spec2["info"]

    # 3. servers (从 host + basePath + schemes)
    spec3["servers"] = _build_servers(spec2)

    # 4. paths (每个 path item 转 3.0)
    if "paths" in spec2 and isinstance(spec2["paths"], dict):
        paths3: Dict[str, Any] = {}
        for path, item in spec2["paths"].items():
            paths3[path] = _convert_path_item(item)
        spec3["paths"] = paths3

    # 5. components (从 definitions + securityDefinitions)
    components: Dict[str, Any] = {}
    if "definitions" in spec2 and isinstance(spec2["definitions"], dict):
        components["schemas"] = spec2["definitions"]
    if "securityDefinitions" in spec2 and isinstance(spec2["securityDefinitions"], dict):
        components["securitySchemes"] = spec2["securityDefinitions"]
    if "parameters" in spec2 and isinstance(spec2["parameters"], dict):
        # 2.0 顶层 parameters 定义 (可复用) → 3.0 components.parameters
        components["parameters"] = spec2["parameters"]
    if "responses" in spec2 and isinstance(spec2["responses"], dict):
        # 2.0 顶层 responses 定义 (可复用) → 3.0 components.responses
        components["responses"] = spec2["responses"]
    if components:
        spec3["components"] = components

    # 6. 顶层 security (3.0 兼容, 直接保留)
    if "security" in spec2:
        spec3["security"] = spec2["security"]

    # 7. tags (保持)
    if "tags" in spec2:
        spec3["tags"] = spec2["tags"]

    # 8. externalDocs (保持)
    if "externalDocs" in spec2:
        spec3["externalDocs"] = spec2["externalDocs"]

    # 9. 重写 $ref 路径: 2.0 的 #/definitions/X 在 3.0 应为 #/components/schemas/X
    #   递归处理 (含 paths/components/responses/parameters/requestBody/...)
    spec3 = _rewrite_refs(spec3)

    return spec3


def is_openapi3(spec: Dict[str, Any]) -> bool:
    """判断 spec 是否是 OpenAPI 3.0.x."""
    if not isinstance(spec, dict):
        return False
    version = spec.get("openapi", "")
    return isinstance(version, str) and version.startswith("3.")


def is_swagger2(spec: Dict[str, Any]) -> bool:
    """判断 spec 是否是 Swagger 2.0 / OpenAPI 2.0."""
    if not isinstance(spec, dict):
        return False
    return spec.get("swagger") == "2.0"
