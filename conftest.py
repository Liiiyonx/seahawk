"""Root pytest configuration.

Keeps test collection inside the real source trees (backend/ edge/ ml/
scripts/). The repo root also holds derived copies and working archives
(zipped-submission review copies, staging builds, scratch dirs) that must
never be collected: their duplicated modules break collection with import
mismatches, and running tests inside them would test stale copies.

``collect_ignore_glob`` is used instead of pytest.ini ``norecursedirs`` so
the patterns stay ASCII-safe (ini files go through locale decoding on
Chinese Windows) and can cover the non-ASCII archive directory names.
"""

collect_ignore_glob = [
    "verify_zip_*",
    "old_zip_review",
    "old_zip_review/*",
    "submission_build",
    "submission_build/*",
    "_work",
    "_work/*",
    ".work",
    ".work/*",
    "tmp",
    "tmp/*",
    "restyle_work",
    "restyle_work/*",
    "unused_package_copies",
    "unused_package_copies/*",
    "review_render",
    "review_contact_sheets",
    "deliverables",
    "dist",
    "dist/*",
    "artifacts",
    "artifacts/*",
    "*存档*",
    "*存档*/*",
    "项目文档",
    "项目文档/*",
]
