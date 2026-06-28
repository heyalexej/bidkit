#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import keyword
import re
import subprocess
import textwrap
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import orjson

HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}
SUCCESS_STATUSES = ("200", "201", "202", "204", "206")
BINARY_RESPONSE_CONTENT_TYPES = {
    "application/gzip",
    "application/octet-stream",
    "application/pdf",
    "application/zip",
    "text/tab-separated-values",
}
TEXT_RESPONSE_CONTENT_TYPES = {"application/xml", "text/plain", "text/xml"}
RESPONSE_CONTENT_TYPES = (
    "application/json",
    *sorted(BINARY_RESPONSE_CONTENT_TYPES),
    *sorted(TEXT_RESPONSE_CONTENT_TYPES),
)
MARKETPLACE_HEADER = "X-EBAY-C-MARKETPLACE-ID"
POST_ORDER_SERVICES = {"cancellation", "case", "inquiry", "return"}
POST_ORDER_QUERY_PARAMS = {
    ("case", "search"): [
        ("case_type_filter", "string"),
        ("case_status_filter", "string"),
        ("order_id", "string"),
        ("item_id", "string"),
        ("transaction_id", "string"),
        ("buyer_login_name", "string"),
        ("limit", "integer"),
        ("offset", "integer"),
    ],
    ("inquiry", "search"): [
        ("inquiry_status_filter", "string"),
        ("order_id", "string"),
        ("item_id", "string"),
        ("transaction_id", "string"),
        ("buyer_login_name", "string"),
        ("limit", "integer"),
        ("offset", "integer"),
    ],
    ("return", "search"): [
        ("order_id", "string"),
        ("item_id", "string"),
        ("transaction_id", "string"),
        ("buyer_login_name", "string"),
        ("state", "string"),
        ("status", "string"),
        ("limit", "integer"),
        ("offset", "integer"),
    ],
}
MISSING_MULTIPART_REQUEST_BODIES = {
    ("commerce_media", "createImageFromFile"): (("image", True),),
    ("commerce_media", "uploadDocument"): (("file", True),),
    (
        "commerce_media",
        "uploadPostOrderDocument",
    ): (
        ("file", True),
        ("documentUsageType", False),
        ("entityType", False),
        ("entityId", False),
    ),
    ("sell_fulfillment", "uploadEvidenceFile"): (("file", True),),
}
MISSING_BINARY_REQUEST_BODIES = {
    ("commerce_media", "uploadVideo"): "application/octet-stream",
}
BASE_MODEL_NAMES = {
    "construct",
    "copy",
    "dict",
    "from_orm",
    "json",
    "model_computed_fields",
    "model_config",
    "model_construct",
    "model_copy",
    "model_dump",
    "model_dump_json",
    "model_extra",
    "model_fields",
    "model_fields_set",
    "model_json_schema",
    "model_parametrized_name",
    "model_post_init",
    "model_rebuild",
    "model_validate",
    "model_validate_json",
    "parse_file",
    "parse_obj",
    "parse_raw",
    "schema",
    "schema_json",
    "update_forward_refs",
    "validate",
}


@dataclass(frozen=True)
class Service:
    spec_path: Path
    key: str
    module_name: str
    group: str
    attr: str
    class_name: str
    async_class_name: str
    model_alias: str
    base_path: str
    subdomain: str
    title: str
    version: str
    spec: dict[str, Any]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec-dir", type=Path, default=Path("specs/ebay"))
    parser.add_argument("--package-dir", type=Path, default=Path("src/ebay_sdk"))
    args = parser.parse_args()

    spec_dir = args.spec_dir.resolve()
    package_dir = args.package_dir.resolve()
    generated_dir = package_dir / "generated"
    models_dir = generated_dir / "models"
    normalized_specs_dir = generated_dir / "specs"
    models_dir.mkdir(parents=True, exist_ok=True)
    normalized_specs_dir.mkdir(parents=True, exist_ok=True)

    for old in normalized_specs_dir.glob("*.json"):
        old.unlink()

    for path in sorted(spec_dir.glob("*.json")):
        spec = preprocess_spec(path.stem, orjson.loads(path.read_bytes()))
        normalized_path = normalized_specs_dir / path.name
        normalized_path.write_bytes(orjson.dumps(spec, option=orjson.OPT_INDENT_2))
        print(f"Preprocessed {path.name}", flush=True)

    services = [load_service(path) for path in sorted(normalized_specs_dir.glob("*.json"))]
    print(f"Generating {len(services)} services from {spec_dir}", flush=True)

    for old in models_dir.glob("*.py"):
        old.unlink()

    (generated_dir / "__init__.py").write_text('"""Generated OpenAPI clients and models."""\n')
    (models_dir / "__init__.py").write_text('"""Generated Pydantic model modules."""\n')

    for service in services:
        write_model_module(models_dir, service)
        print(f"Generated models for {service.key}", flush=True)

    write_resources(generated_dir / "resources.py", services)
    print(f"Generated resources for {len(services)} services", flush=True)


def load_service(path: Path) -> Service:
    spec = orjson.loads(path.read_bytes())
    key = service_key(path.stem)
    module_name = safe_identifier(key)
    group, attr = group_attr(key)
    class_name = pascal_case(key) + "Resource"
    async_class_name = "Async" + class_name
    server = (spec.get("servers") or [{}])[0]
    url = server.get("url", "https://api.ebay.com")
    subdomain_match = re.search(r"https://([a-z0-9-]+)\.", url)
    base_path = (
        server.get("variables", {})
        .get("basePath", {})
        .get("default")
    )
    if not base_path:
        base_path = "/" + "/".join(part for part in path_parts_from_paths(spec)[:3])
    return Service(
        spec_path=path,
        key=key,
        module_name=module_name,
        group=group,
        attr=attr,
        class_name=class_name,
        async_class_name=async_class_name,
        model_alias=module_name + "_models",
        base_path=base_path,
        subdomain=subdomain_match.group(1) if subdomain_match else "api",
        title=spec.get("info", {}).get("title", key),
        version=spec.get("info", {}).get("version", ""),
        spec=spec,
    )


def preprocess_spec(stem: str, spec: dict[str, Any]) -> dict[str, Any]:
    key = service_key(stem)
    patched = copy.deepcopy(spec)
    schemas = patched.setdefault("components", {}).setdefault("schemas", {})

    if key == "sell_inventory":
        patch_sell_inventory_spec(patched)
    elif key == "case":
        patch_case_spec(patched, schemas)
    elif key == "inquiry":
        patch_inquiry_spec(patched, schemas)
    elif key == "return":
        patch_return_spec(patched, schemas)

    normalize_component_schemas(schemas)
    patch_missing_multipart_request_bodies(key, patched)
    patch_missing_binary_request_bodies(key, patched)

    return patched


def normalize_component_schemas(schemas: dict[str, Any]) -> None:
    normalize_scalar_enum_types(schemas)
    remove_boolean_schema_required_flags(schemas)
    move_misplaced_schema_descriptions(schemas)


def normalize_scalar_enum_types(node: Any) -> None:
    if isinstance(node, dict):
        enum_values = node.get("enum")
        if (
            isinstance(enum_values, list)
            and enum_values
            and node.get("type") in {None, "object"}
            and not any(
                key in node
                for key in ("$ref", "properties", "items", "allOf", "anyOf", "oneOf")
            )
        ):
            inferred = infer_enum_type(enum_values)
            if inferred:
                node["type"] = inferred
                if any(value is None for value in enum_values):
                    node["nullable"] = True
        for value in node.values():
            normalize_scalar_enum_types(value)
    elif isinstance(node, list):
        for item in node:
            normalize_scalar_enum_types(item)


def infer_enum_type(values: list[Any]) -> str | None:
    non_null = [value for value in values if value is not None]
    if not non_null:
        return None
    if all(isinstance(value, str) for value in non_null):
        return "string"
    if all(isinstance(value, bool) for value in non_null):
        return "boolean"
    if all(isinstance(value, int) and not isinstance(value, bool) for value in non_null):
        return "integer"
    if all(isinstance(value, int | float) and not isinstance(value, bool) for value in non_null):
        return "number"
    return None


def remove_boolean_schema_required_flags(node: Any) -> None:
    if isinstance(node, dict):
        if isinstance(node.get("required"), bool):
            node.pop("required")
        for value in node.values():
            remove_boolean_schema_required_flags(value)
    elif isinstance(node, list):
        for item in node:
            remove_boolean_schema_required_flags(item)


def move_misplaced_schema_descriptions(schemas: dict[str, Any]) -> None:
    for schema in schemas.values():
        if not isinstance(schema, dict):
            continue
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            continue
        description = properties.get("description")
        if isinstance(description, str):
            schema.setdefault("description", description)
            properties.pop("description")
            required = schema.get("required")
            if isinstance(required, list):
                schema["required"] = [item for item in required if item != "description"]


def patch_missing_multipart_request_bodies(key: str, spec: dict[str, Any]) -> None:
    for path_item in spec.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            fields = MISSING_MULTIPART_REQUEST_BODIES.get(
                (key, operation.get("operationId")),
            )
            if not fields or operation.get("requestBody"):
                continue
            operation["requestBody"] = multipart_request_body(fields)


def patch_missing_binary_request_bodies(key: str, spec: dict[str, Any]) -> None:
    for path_item in spec.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            content_type = MISSING_BINARY_REQUEST_BODIES.get(
                (key, operation.get("operationId")),
            )
            if not content_type or operation.get("requestBody"):
                continue
            operation["requestBody"] = binary_request_body(content_type)


def multipart_request_body(fields: tuple[tuple[str, bool], ...]) -> dict[str, Any]:
    properties = {
        name: (
            {"type": "string", "format": "binary"}
            if is_file
            else {"type": "string"}
        )
        for name, is_file in fields
    }
    return {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "properties": properties,
                    "required": [name for name, _is_file in fields],
                },
            },
        },
    }


def binary_request_body(content_type: str) -> dict[str, Any]:
    return {
        "required": True,
        "content": {
            content_type: {
                "schema": {
                    "type": "string",
                    "format": "binary",
                },
            },
        },
    }


def patch_sell_inventory_spec(spec: dict[str, Any]) -> None:
    schemas = spec.setdefault("components", {}).setdefault("schemas", {})
    aspects_schema = {
        "type": "object",
        "additionalProperties": {
            "type": "array",
            "items": {"type": "string"},
        },
    }
    for schema_name in ("Product", "InventoryItemGroup"):
        properties = schemas.get(schema_name, {}).setdefault("properties", {})
        if "aspects" in properties:
            description = properties["aspects"].get("description")
            properties["aspects"] = {**aspects_schema}
            if description:
                properties["aspects"]["description"] = description

    offer_get = spec.get("paths", {}).get("/offer", {}).get("get", {})
    for param in offer_get.get("parameters", []):
        if param.get("in") == "query" and param.get("name") == "sku":
            param["required"] = True


def patch_case_spec(spec: dict[str, Any], schemas: dict[str, Any]) -> None:
    add_common_post_order_schemas(schemas)
    schemas.update({
        "CaseSummary": object_schema({
            "itemId": integer_schema(),
            "transactionId": integer_schema(),
            "caseId": integer_schema(),
            "buyer": string_schema(),
            "seller": string_schema(),
            "caseStatusEnum": string_schema(),
            "claimAmount": ref_schema("PostOrderAmount"),
            "respondByDate": ref_schema("PostOrderDateTime"),
            "creationDate": ref_schema("PostOrderDateTime"),
            "lastModifiedDate": ref_schema("PostOrderDateTime"),
        }),
        "CaseSearchResponse": object_schema({
            "members": array_schema(ref_schema("CaseSummary")),
            "totalNumberOfCases": integer_schema(),
            "paginationOutput": ref_schema("PaginationOutput"),
        }),
        "CaseHistoryDetails": object_schema({
            "history": array_schema(ref_schema("PostOrderHistoryEntry")),
            "buyerrequested": string_schema(),
            "shipmentTrackingDetails": any_object_schema(),
        }),
        "CaseDetail": object_schema({
            "caseId": string_schema(),
            "caseType": string_schema(),
            "itemId": string_schema(),
            "transactionId": string_schema(),
            "returnId": string_schema(),
            "claimAmount": ref_schema("PostOrderAmount"),
            "shippingFee": ref_schema("PostOrderAmount"),
            "caseQuantity": integer_schema(),
            "initiator": string_schema(),
            "creationDate": ref_schema("PostOrderDateTime"),
            "lastModifiedDate": ref_schema("PostOrderDateTime"),
            "sellerClosureReason": string_schema(),
            "buyerClosureReason": string_schema(),
            "caseDetails": any_object_schema(),
            "actionDeadlines": any_object_schema(),
            "appealDetails": any_object_schema(),
            "buyer": string_schema(),
            "seller": string_schema(),
            "buyerOutcome": string_schema(),
            "sellerOutcome": string_schema(),
            "nextSteps": array_schema({}),
            "caseContentOnHold": boolean_schema(),
            "status": string_schema(),
            "fsnadnoSellerFault": boolean_schema(),
            "caseHistoryDetails": ref_schema("CaseHistoryDetails"),
        }),
    })
    add_post_order_search_params(spec, "/casemanagement/search", "case")
    set_json_response(spec, "/casemanagement/search", "get", "CaseSearchResponse")
    set_json_response(spec, "/casemanagement/{caseId}", "get", "CaseDetail")


def patch_inquiry_spec(spec: dict[str, Any], schemas: dict[str, Any]) -> None:
    add_common_post_order_schemas(schemas)
    schemas.update({
        "InquirySummary": object_schema({
            "itemId": integer_schema(),
            "transactionId": integer_schema(),
            "inquiryId": integer_schema(),
            "buyer": string_schema(),
            "seller": string_schema(),
            "inquiryStatusEnum": string_schema(),
            "claimAmount": ref_schema("PostOrderAmount"),
            "respondByDate": ref_schema("PostOrderDateTime"),
            "creationDate": ref_schema("PostOrderDateTime"),
            "lastModifiedDate": ref_schema("PostOrderDateTime"),
        }),
        "InquirySearchResponse": object_schema({
            "members": array_schema(ref_schema("InquirySummary")),
            "totalNumberOfInquiries": integer_schema(),
            "paginationOutput": ref_schema("PaginationOutput"),
            "countSummary": array_schema(ref_schema("CountSummary")),
        }),
        "InquiryHistoryDetails": object_schema({
            "history": array_schema(ref_schema("PostOrderHistoryEntry")),
            "additionalInfo": string_schema(),
            "buyerrequested": string_schema(),
            "shipmentTrackingDetails": any_object_schema(),
        }),
        "InquiryDetail": object_schema({
            "inquiryId": string_schema(),
            "itemId": string_schema(),
            "transactionId": string_schema(),
            "claimAmount": ref_schema("PostOrderAmount"),
            "shippingCost": ref_schema("PostOrderAmount"),
            "inquiryQuantity": integer_schema(),
            "initiator": string_schema(),
            "sellerMakeItRightByDate": ref_schema("PostOrderDateTime"),
            "creationReason": string_schema(),
            "buyer": string_schema(),
            "seller": string_schema(),
            "inquiryContentOnHold": boolean_schema(),
            "inquiryDetails": any_object_schema(),
            "inquiryHistoryDetails": ref_schema("InquiryHistoryDetails"),
            "state": string_schema(),
            "itemDetails": any_object_schema(),
            "status": string_schema(),
        }),
    })
    add_post_order_search_params(spec, "/inquiry/search", "inquiry")
    set_json_response(spec, "/inquiry/search", "get", "InquirySearchResponse")
    set_json_response(spec, "/inquiry/{inquiryId}", "get", "InquiryDetail")


def patch_return_spec(spec: dict[str, Any], schemas: dict[str, Any]) -> None:
    add_common_post_order_schemas(schemas)
    schemas.update({
        "ReturnSummary": object_schema({
            "returnId": string_schema(),
            "orderId": string_schema(),
            "buyerLoginName": string_schema(),
            "sellerLoginName": string_schema(),
            "currentType": string_schema(),
            "state": string_schema(),
            "status": string_schema(),
            "creationInfo": any_object_schema(),
        }),
        "ReturnSearchResponse": object_schema({
            "members": array_schema(ref_schema("ReturnSummary")),
            "total": integer_schema(),
            "paginationOutput": ref_schema("PaginationOutput"),
            "countSummary": array_schema(ref_schema("CountSummary")),
        }),
        "ReturnDetail": object_schema({
            "summary": ref_schema("ReturnSummary"),
        }),
        "ReturnPreferences": object_schema({
            "rmaRequired": boolean_schema(),
            "advanceRulesEnabled": boolean_schema(),
        }),
    })
    add_post_order_search_params(spec, "/return/search", "return")
    set_json_response(spec, "/return/search", "get", "ReturnSearchResponse")
    set_json_response(spec, "/return/{returnId}", "get", "ReturnDetail")
    set_json_response(spec, "/return/preference", "get", "ReturnPreferences")


def add_common_post_order_schemas(schemas: dict[str, Any]) -> None:
    schemas.update({
        "PostOrderAmount": object_schema({
            "value": number_schema(),
            "currency": string_schema(),
            "convertedFromCurrency": string_schema(),
            "convertedFromValue": number_schema(),
            "exchangeRate": string_schema(),
        }),
        "PostOrderDateTime": object_schema({
            "value": string_schema(),
            "formattedValue": string_schema(),
        }),
        "PaginationOutput": object_schema({
            "offset": integer_schema(),
            "limit": integer_schema(),
            "totalPages": integer_schema(),
            "totalEntries": integer_schema(),
        }),
        "CountSummary": object_schema({
            "count": integer_schema(),
            "type": string_schema(),
        }),
        "PostOrderHistoryEntry": object_schema({
            "date": ref_schema("PostOrderDateTime"),
            "action": string_schema(),
            "actor": string_schema(),
            "description": string_schema(),
        }),
    })


def add_post_order_search_params(spec: dict[str, Any], path: str, kind: str) -> None:
    operation = spec.get("paths", {}).get(path, {}).get("get", {})
    operation.setdefault("parameters", [])
    existing = {
        (param.get("in"), param.get("name"))
        for param in operation["parameters"]
    }
    for name, schema_type_name in POST_ORDER_QUERY_PARAMS[(kind, "search")]:
        key = ("query", name)
        if key in existing:
            continue
        operation["parameters"].append({
            "name": name,
            "in": "query",
            "required": False,
            "schema": {"type": schema_type_name},
        })


def set_json_response(spec: dict[str, Any], path: str, method: str, schema_name: str) -> None:
    operation = spec.get("paths", {}).get(path, {}).get(method, {})
    response = operation.setdefault("responses", {}).setdefault("200", {"description": "OK"})
    response["content"] = {
        "application/json": {
            "schema": ref_schema(schema_name),
        },
    }


def object_schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
    }


def ref_schema(name: str) -> dict[str, Any]:
    return {"$ref": f"#/components/schemas/{name}"}


def array_schema(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


def string_schema() -> dict[str, Any]:
    return {"type": "string"}


def integer_schema() -> dict[str, Any]:
    return {"type": "integer"}


def number_schema() -> dict[str, Any]:
    return {"type": "number"}


def boolean_schema() -> dict[str, Any]:
    return {"type": "boolean"}


def any_object_schema() -> dict[str, Any]:
    return {"type": "object", "additionalProperties": True}


def service_key(stem: str) -> str:
    if stem == "sell_account_v1_oas3":
        return "sell_account_v1"
    if stem == "sell_account_v2_oas3":
        return "sell_account_v2"
    stem = re.sub(r"_oas3$", "", stem)
    return re.sub(r"_v\d+(?:_beta)?$", "", stem)


def group_attr(key: str) -> tuple[str, str]:
    if key == "sell_account_v1":
        return "sell", "account"
    if key == "sell_account_v2":
        return "sell", "account_v2"
    if key in POST_ORDER_SERVICES:
        return "post_order", safe_identifier(key)
    for group in ("buy", "commerce", "developer", "sell"):
        prefix = group + "_"
        if key.startswith(prefix):
            return group, safe_identifier(key.removeprefix(prefix))
    return "misc", safe_identifier(key)


def path_parts_from_paths(spec: dict[str, Any]) -> list[str]:
    first = next(iter(spec.get("paths", {"/": {}})))
    return [part for part in first.split("/") if part and not part.startswith("{")]


def write_model_module(models_dir: Path, service: Service) -> None:
    output = models_dir / f"{service.module_name}.py"
    schemas = service.spec.get("components", {}).get("schemas", {})
    if not schemas:
        output.write_text(
            "# ruff: noqa\n"
            "from __future__ import annotations\n\n"
            "from typing import Any\n\n"
            "from ebay_sdk.models import EbayModel\n",
        )
        return

    command = [
        "datamodel-codegen",
        "--input",
        str(service.spec_path),
        "--input-file-type",
        "openapi",
        "--output",
        str(output),
        "--output-model-type",
        "pydantic_v2.BaseModel",
        "--base-class",
        "ebay_sdk.models.EbayModel",
        "--target-python-version",
        "3.11",
        "--snake-case-field",
        "--use-standard-collections",
        "--use-union-operator",
        "--force-optional",
        "--disable-timestamp",
    ]
    subprocess.run(command, check=True)
    generated = output.read_text()
    if "# ruff: noqa" not in generated.splitlines()[:3]:
        output.write_text("# ruff: noqa\n" + generated)


def write_resources(path: Path, services: list[Service]) -> None:
    lines = [
        "# ruff: noqa",
        "from __future__ import annotations",
        "",
        "from collections.abc import Mapping",
        "from contextlib import AbstractAsyncContextManager, AbstractContextManager",
        "from typing import Any, Literal, overload",
        "",
        "import httpx",
        "",
        "from ebay_sdk.resource import AsyncBaseResource, BaseResource",
        "",
    ]
    for service in services:
        lines.append(f"from .models import {service.module_name} as {service.model_alias}")
    lines.extend(["", ""])

    for service in services:
        lines.extend(resource_class(service, async_resource=False))
        lines.extend(resource_class(service, async_resource=True))

    lines.extend(namespace_installers(services))
    path.write_text("\n".join(lines).rstrip() + "\n")


def resource_class(service: Service, *, async_resource: bool) -> list[str]:
    cls = service.async_class_name if async_resource else service.class_name
    base = "AsyncBaseResource" if async_resource else "BaseResource"
    prefix = "async " if async_resource else ""
    await_prefix = "await " if async_resource else ""
    lines = [
        f"class {cls}({base}):",
        "    service = {",
        f"        'key': {service.key!r},",
        f"        'title': {service.title!r},",
        f"        'version': {service.version!r},",
        f"        'base_path': {service.base_path!r},",
        f"        'subdomain': {service.subdomain!r},",
    ]
    if service.key in POST_ORDER_SERVICES:
        lines.append("        'auth_scheme': 'TOKEN',")
    lines.extend([
        "    }",
        "",
    ])

    operations = list(iter_operations(service.spec))
    if not operations:
        lines.append("    pass")
        lines.extend(["", ""])
        return lines

    seen_names: set[str] = set()
    for operation in operations:
        method_lines, method_name = render_method(
            service,
            operation,
            prefix=prefix,
            await_prefix=await_prefix,
        )
        if method_name in seen_names:
            continue
        seen_names.add(method_name)
        lines.extend(indent(method_lines, 4))
        lines.append("")
    lines.append("")
    return lines


def iter_operations(spec: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for path, path_item in spec.get("paths", {}).items():
        shared_params = path_item.get("parameters", [])
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS:
                continue
            yield {
                "path": path,
                "method": method.upper(),
                "operation": operation,
                "parameters": [*shared_params, *operation.get("parameters", [])],
            }


def render_method(
    service: Service,
    operation_info: dict[str, Any],
    *,
    prefix: str,
    await_prefix: str,
) -> tuple[list[str], str]:
    operation = operation_info["operation"]
    operation_id = operation.get("operationId") or fallback_operation_id(operation_info)
    method_name = safe_identifier(snake_case(operation_id))
    parameters = dedupe_parameters(operation_info["parameters"])
    parameters = with_optional_marketplace_header(parameters)
    request_body = body_parameter(service, operation)
    response_model = response_model_expr(service, operation, operation_info["method"])
    if request_body and request_body["kind"] == "multipart":
        parameters = [
            param for param in parameters
            if not (
                param.get("in") == "header"
                and param.get("name", "").lower() == "content-type"
            )
        ]
    if request_body and request_body["kind"] == "binary" and request_body.get("content_type"):
        parameters = [
            param for param in parameters
            if not (
                param.get("in") == "header"
                and param.get("name", "").lower() == "content-type"
            )
        ]

    path_params = [param for param in parameters if param.get("in") == "path"]
    other_params = [param for param in parameters if param.get("in") != "path"]
    required_other = [param for param in other_params if param.get("required")]
    optional_other = [param for param in other_params if not param.get("required")]

    positional = [param_def(param, service=service, required=True) for param in path_params]
    keyword_required = [
        param_def(param, service=service, required=True)
        for param in required_other
    ]
    keyword_optional = [
        param_def(param, service=service, required=False)
        for param in optional_other
    ]

    body_arg: str | None = None
    files_arg: str | None = None
    if request_body:
        if request_body["kind"] == "multipart":
            files_arg = (
                "files: Mapping[str, Any]"
                if request_body["required"]
                else "files: Mapping[str, Any] | None = None"
            )
        else:
            body_type = request_body["type"]
            body_arg = "body: " + body_type
            if not request_body["required"]:
                body_arg += " | None = None"

    if body_arg and request_body and request_body["required"]:
        keyword_required.insert(0, body_arg)
    elif body_arg:
        keyword_optional.insert(0, body_arg)
    if files_arg and request_body and request_body["required"]:
        keyword_required.insert(0, files_arg)
    elif files_arg:
        keyword_optional.insert(0, files_arg)

    return_type = return_type_expr(response_model)
    signature_parts = method_signature_parts(
        positional=positional,
        keyword_required=keyword_required,
        keyword_optional=keyword_optional,
        raw_response="raw_response: bool = False",
    )
    raw_false_signature_parts = method_signature_parts(
        positional=positional,
        keyword_required=keyword_required,
        keyword_optional=keyword_optional,
        raw_response="raw_response: Literal[False] = False",
    )
    raw_true_signature_parts = method_signature_parts(
        positional=positional,
        keyword_required=keyword_required,
        keyword_optional=keyword_optional,
        raw_response="raw_response: Literal[True]",
    )

    lines = [
        "@overload",
        f"{prefix}def {method_name}({', '.join(raw_false_signature_parts)}) -> {return_type}: ...",
        "@overload",
        f"{prefix}def {method_name}({', '.join(raw_true_signature_parts)}) -> httpx.Response: ...",
        (
            f"{prefix}def {method_name}({', '.join(signature_parts)}) "
            f"-> {return_type} | httpx.Response:"
        ),
    ]
    summary = clean_doc(operation.get("summary") or operation.get("description") or "")
    if summary:
        lines.extend(doc_lines(summary))

    lines.append(f"    return {await_prefix}self._request(")
    lines.append(f"        {operation_id!r},")
    lines.append(f"        {operation_info['method']!r},")
    lines.append(f"        {operation_info['path']!r},")

    lines.append(f"        path_params={mapping_literal(path_params)},")
    query_params = [param for param in other_params if param.get("in") == "query"]
    header_params = [param for param in other_params if param.get("in") == "header"]
    lines.append(f"        params={mapping_literal(query_params)},")
    headers = mapping_literal(header_params)
    header_names = {param["name"].lower() for param in header_params}
    if (
        request_body
        and request_body.get("content_type")
        and request_body["kind"] != "multipart"
        and "content-type" not in header_names
    ):
        if headers == "{}":
            headers = "{}"
        headers = merge_header_literal(headers, {"Content-Type": request_body["content_type"]})
    lines.append(f"        headers={headers},")
    if request_body and request_body["kind"] == "multipart":
        lines.append("        files=files,")
    elif request_body:
        lines.append("        body=body,")
    lines.append(f"        response_model={response_model},")
    lines.append("        raw_response=raw_response,")
    lines.append("    )")
    if response_model == "bytes":
        lines.append("")
        lines.extend(
            render_stream_method(
                method_name=method_name,
                operation_id=operation_id,
                operation_info=operation_info,
                positional=positional,
                keyword_required=keyword_required,
                keyword_optional=keyword_optional,
                path_params=path_params,
                query_params=query_params,
                header_params=header_params,
                request_body=request_body,
                async_resource=bool(prefix),
            )
        )
    return lines, method_name


def render_stream_method(
    *,
    method_name: str,
    operation_id: str,
    operation_info: dict[str, Any],
    positional: list[str],
    keyword_required: list[str],
    keyword_optional: list[str],
    path_params: list[dict[str, Any]],
    query_params: list[dict[str, Any]],
    header_params: list[dict[str, Any]],
    request_body: dict[str, Any] | None,
    async_resource: bool,
) -> list[str]:
    signature_parts = method_signature_parts(
        positional=positional,
        keyword_required=keyword_required,
        keyword_optional=keyword_optional,
        raw_response=None,
    )
    context_manager = "AbstractAsyncContextManager" if async_resource else "AbstractContextManager"
    lines = [
        (
            f"def stream_{method_name}({', '.join(signature_parts)}) "
            f"-> {context_manager}[httpx.Response]:"
        ),
        "    return self._stream(",
        f"        {operation_id!r},",
        f"        {operation_info['method']!r},",
        f"        {operation_info['path']!r},",
        f"        path_params={mapping_literal(path_params)},",
        f"        params={mapping_literal(query_params)},",
        f"        headers={mapping_literal(header_params)},",
    ]
    if request_body and request_body["kind"] == "multipart":
        lines.append("        files=files,")
    elif request_body:
        lines.append("        body=body,")
    lines.append("    )")
    return lines


def method_signature_parts(
    *,
    positional: list[str],
    keyword_required: list[str],
    keyword_optional: list[str],
    raw_response: str | None,
) -> list[str]:
    parts = ["self", *positional]
    keyword_parts = [*keyword_required, *keyword_optional]
    if raw_response is not None:
        keyword_parts.append(raw_response)
    if keyword_parts:
        parts.append("*")
        parts.extend(keyword_parts)
    return parts


def dedupe_parameters(parameters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for param in parameters:
        key = (param.get("in", ""), param.get("name", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(param)
    return result


def with_optional_marketplace_header(parameters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    found = False
    for param in parameters:
        if (
            param.get("in") == "header"
            and str(param.get("name", "")).lower() == MARKETPLACE_HEADER.lower()
        ):
            patched = copy.deepcopy(param)
            patched["required"] = False
            patched["schema"] = {"type": "string"}
            result.append(patched)
            found = True
        else:
            result.append(param)

    if not found:
        result.append({
            "name": MARKETPLACE_HEADER,
            "in": "header",
            "required": False,
            "schema": {"type": "string"},
        })
    return result


def body_parameter(service: Service, operation: dict[str, Any]) -> dict[str, Any] | None:
    request_body = operation.get("requestBody")
    if not request_body:
        return None
    content = request_body.get("content", {})
    content_type = preferred_content_type(content)
    schema = content.get(content_type, {}).get("schema", {}) if content_type else {}
    required = bool(request_body.get("required"))
    if content_type == "multipart/form-data":
        return {
            "kind": "multipart",
            "required": required,
            "content_type": content_type,
            "type": "Mapping[str, Any]",
        }
    if content_type == "application/octet-stream":
        return {
            "kind": "binary",
            "required": required,
            "content_type": content_type,
            "type": "bytes | bytearray | memoryview",
        }
    return {
        "kind": "json",
        "required": required,
        "content_type": content_type or "application/json",
        "type": request_body_type(schema, service),
    }


def preferred_content_type(content: dict[str, Any]) -> str | None:
    for content_type in (
        "application/json",
        "multipart/form-data",
        "application/octet-stream",
        "application/xml",
        "text/xml",
    ):
        if content_type in content:
            return content_type
    return next(iter(content), None)


def request_body_type(schema: dict[str, Any], service: Service) -> str:
    ref = ref_name(schema)
    if ref:
        return f"{service.model_alias}.{pascal_case(ref)}"
    if schema.get("type") == "array":
        item_ref = ref_name(schema.get("items", {}))
        if item_ref:
            return f"list[{service.model_alias}.{pascal_case(item_ref)}]"
        return "list[Any]"
    return "Any | Mapping[str, Any]"


def response_model_expr(service: Service, operation: dict[str, Any], method: str = "get") -> str:
    responses = operation.get("responses", {})
    for status in SUCCESS_STATUSES:
        response = responses.get(status)
        if not response:
            continue
        content = response.get("content", {})
        if content:
            return response_type_from_content(content, service)
        # Success status with no documented body. 204 is genuinely empty. Otherwise eBay often
        # omits the schema for GETs that still return JSON (e.g. post-order), so type those `Any`
        # rather than the false `None`; write verbs without a body stay `None`.
        if status != "204" and method.lower() == "get":
            return "Any"
        return "None"
    if default_response := responses.get("default"):
        return response_type_from_content(default_response.get("content", {}), service)
    return "None"


def return_type_expr(response_model: str) -> str:
    return response_model


def response_type_from_content(content: dict[str, Any], service: Service) -> str:
    if not content:
        return "None"

    for content_type in RESPONSE_CONTENT_TYPES:
        if content_type in content:
            return response_type_for_media(content_type, content[content_type], service)

    content_type, media_type = next(iter(content.items()))
    return response_type_for_media(content_type, media_type, service)


def response_type_for_media(
    content_type: str,
    media_type: dict[str, Any],
    service: Service,
) -> str:
    if content_type in BINARY_RESPONSE_CONTENT_TYPES:
        return "bytes"
    if content_type in TEXT_RESPONSE_CONTENT_TYPES:
        return "str"

    schema = media_type.get("schema")
    if not schema:
        return "Any"
    return response_type(schema, service)


def response_type(schema: dict[str, Any], service: Service) -> str:
    ref = ref_name(schema)
    if ref:
        return f"{service.model_alias}.{pascal_case(ref)}"
    if schema.get("type") == "array":
        item_type = response_type(schema.get("items", {}), service)
        return f"list[{item_type}]" if item_type != "Any" else "list[Any]"
    if schema.get("type") in {"string", "integer", "number", "boolean"}:
        return schema_type(schema, {})
    if schema.get("type") == "object":
        return schema_type(schema, {})
    return "Any"


def param_def(param: dict[str, Any], *, service: Service, required: bool) -> str:
    name = safe_identifier(snake_case(param["name"]))
    type_expr = schema_type(param.get("schema", {}), component_name_map(service))
    if required:
        return f"{name}: {type_expr}"
    return f"{name}: {type_expr} | None = None"


def component_name_map(service: Service) -> dict[str, str]:
    return {
        name: f"{service.model_alias}.{pascal_case(name)}"
        for name in service.spec.get("components", {}).get("schemas", {})
    }


def mapping_literal(params: list[dict[str, Any]]) -> str:
    if not params:
        return "{}"
    parts = []
    for param in params:
        wire_name = param["name"]
        variable = safe_identifier(snake_case(wire_name))
        parts.append(f"{wire_name!r}: {variable}")
    return "{" + ", ".join(parts) + "}"


def merge_header_literal(existing: str, extra: dict[str, str]) -> str:
    if existing == "{}":
        return repr(extra)
    extra_items = ", ".join(f"{key!r}: {value!r}" for key, value in extra.items())
    return existing[:-1] + ", " + extra_items + "}"


def schema_type(schema: dict[str, Any], name_map: dict[str, str]) -> str:
    ref = ref_name(schema)
    if ref:
        return name_map.get(ref, pascal_case(ref))
    enum = schema.get("enum")
    if enum and len(enum) <= 80 and all(
        isinstance(item, str | int | float | bool) for item in enum
    ):
        return "Literal[" + ", ".join(repr(item) for item in enum) + "]"
    schema_type_name = schema.get("type")
    schema_format = schema.get("format")
    if schema_type_name == "string":
        if schema_format == "date-time":
            return "datetime"
        if schema_format == "date":
            return "date"
        if schema_format == "binary":
            return "bytes"
        return "str"
    if schema_type_name == "integer":
        return "int"
    if schema_type_name == "number":
        return "float"
    if schema_type_name == "boolean":
        return "bool"
    if schema_type_name == "array":
        return f"list[{schema_type(schema.get('items', {}), name_map)}]"
    if schema_type_name == "object":
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            return f"dict[str, {schema_type(additional, name_map)}]"
        return "dict[str, Any]"
    return "Any"


def ref_name(schema: dict[str, Any]) -> str | None:
    ref = schema.get("$ref")
    if not ref:
        return None
    return ref.rsplit("/", 1)[-1]


def namespace_installers(services: list[Service]) -> list[str]:
    by_group: dict[str, list[Service]] = defaultdict(list)
    for service in services:
        by_group[service.group].append(service)

    lines: list[str] = []
    for group in sorted(by_group):
        lines.extend(namespace_class(group, by_group[group], async_names=False))
        lines.extend(namespace_class(group, by_group[group], async_names=True))

    lines.extend([
        "def install_sync_namespaces(client: Any) -> None:",
    ])
    lines.extend(installer_body(by_group, async_names=False))
    lines.extend([
        "",
        "",
        "def install_async_namespaces(client: Any) -> None:",
    ])
    lines.extend(installer_body(by_group, async_names=True))
    return lines


def installer_body(by_group: dict[str, list[Service]], *, async_names: bool) -> list[str]:
    lines = []
    for group in sorted(by_group):
        group_attr_name = safe_identifier(group)
        cls = namespace_class_name(group, async_names=async_names)
        lines.append(f"    client.{group_attr_name} = {cls}(client)")
    if not lines:
        lines.append("    pass")
    return lines


def namespace_class(group: str, services: list[Service], *, async_names: bool) -> list[str]:
    cls = namespace_class_name(group, async_names=async_names)
    lines = [f"class {cls}:"]
    for service in sorted(services, key=lambda item: item.attr):
        resource_cls = service.async_class_name if async_names else service.class_name
        lines.append(f"    {service.attr}: {resource_cls}")
    lines.extend(["", "    def __init__(self, client: Any) -> None:"])
    for service in sorted(services, key=lambda item: item.attr):
        resource_cls = service.async_class_name if async_names else service.class_name
        lines.append(f"        self.{service.attr} = {resource_cls}(client)")
    lines.extend(["", ""])
    return lines


def namespace_class_name(group: str, *, async_names: bool) -> str:
    prefix = "Async" if async_names else ""
    return prefix + pascal_case(group) + "Namespace"


def fallback_operation_id(operation_info: dict[str, Any]) -> str:
    parts = [operation_info["method"].lower(), *path_parts_from_string(operation_info["path"])]
    return "_".join(parts)


def path_parts_from_string(path: str) -> list[str]:
    return [re.sub(r"[{}]", "", part) for part in path.split("/") if part]


def snake_case(value: str) -> str:
    value = value.replace("-", "_").replace(".", "_")
    value = re.sub(r"[^0-9A-Za-z_]+", "_", value)
    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_").lower() or "value"


def pascal_case(value: str) -> str:
    parts = re.split(r"[^0-9A-Za-z]+", snake_case(value))
    result = "".join(part[:1].upper() + part[1:] for part in parts if part)
    if not result or result[0].isdigit():
        result = "Model" + result
    return result


def safe_identifier(value: str) -> str:
    value = snake_case(value)
    if value[0].isdigit():
        value = "_" + value
    if keyword.iskeyword(value) or value in BASE_MODEL_NAMES:
        value += "_"
    return value


def clean_doc(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def doc_lines(summary: str, width: int = 92) -> list[str]:
    """Render a cleaned summary as wrapped, triple-quoted docstring source lines."""

    def esc(text: str) -> str:
        # Neutralise backslashes and embedded triple-quotes for a """...""" literal.
        return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')

    wrapped = textwrap.wrap(summary, width=width) or [summary]
    if len(wrapped) == 1 and not wrapped[0].endswith('"'):
        return [f'    """{esc(wrapped[0])}"""']
    lines = [f'    """{esc(wrapped[0])}']
    lines.extend(f"    {esc(line)}" for line in wrapped[1:])
    lines.append('    """')
    return lines


def indent(lines: Iterable[str], spaces: int) -> list[str]:
    prefix = " " * spaces
    return [prefix + line if line else "" for line in lines]


if __name__ == "__main__":
    main()
