"""Generate one API-reference page per eBay service at docs build time.

Run by mkdocs-gen-files: each page renders the sync resource class (all typed
operations) plus that service's Pydantic models via mkdocstrings. Pages are
excluded from the search index — thousands of generated symbols would drown
out the hand-written docs; browsers' in-page find works fine on a per-service
page.
"""

from __future__ import annotations

import sys
from pathlib import Path

import mkdocs_gen_files

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bidkit.generated import resources  # noqa: E402

PAGE_HEADER = """---
search:
  exclude: true
---

# {title} — `client.{accessor}`

Version `{version}` · base path `{base_path}` · async twin: the same methods on
`AsyncEbayClient`, awaited.

## Operations

::: bidkit.generated.resources.{class_name}
    options:
      show_root_heading: false
      show_source: false
      show_signature_annotations: true
      separate_signature: true
      heading_level: 3

## Models

::: bidkit.generated.models.{module}
    options:
      show_root_heading: false
      show_source: false
      show_if_no_docstring: true
      separate_signature: true
      summary: false
      heading_level: 3
      filters: ["!^_"]
"""


def sync_resource_classes() -> list[type]:
    classes = []
    for name in dir(resources):
        obj = getattr(resources, name)
        if (
            isinstance(obj, type)
            and name.endswith("Resource")
            and not name.startswith("Async")
            and getattr(obj, "service", None)
        ):
            classes.append(obj)
    return sorted(classes, key=lambda cls: cls.service["key"])


def accessor_for(key: str) -> str:
    """client.<group>.<attr> path, mirroring the generator's namespace layout."""
    post_order = {"cancellation", "case", "inquiry", "return"}
    if key in post_order:
        attr = "return_" if key == "return" else key
        return f"post_order.{attr}"
    group, _, rest = key.partition("_")
    return f"{group}.{rest}" if rest else key


nav_lines = ["# Generated reference", ""]
for cls in sync_resource_classes():
    service = cls.service
    key = service["key"]
    module = "return_" if key == "return" else key
    page = f"reference/generated/{key}.md"
    with mkdocs_gen_files.open(page, "w") as handle:
        handle.write(
            PAGE_HEADER.format(
                title=service["title"],
                accessor=accessor_for(key),
                version=service["version"],
                base_path=service["base_path"],
                class_name=cls.__name__,
                module=module,
            )
        )
    nav_lines.append(f"- [{service['title']}]({key}.md)")

with mkdocs_gen_files.open("reference/generated/index.md", "w") as handle:
    handle.write(
        "---\nsearch:\n  exclude: true\n---\n\n# Generated reference\n\n"
        "Full per-service reference — every typed operation and Pydantic model, "
        "generated from eBay's OpenAPI contracts.\n\n" + "\n".join(nav_lines[2:]) + "\n"
    )
