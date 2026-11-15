"""Sphinx configuration for django-tasks-temporal."""

import os
import sys
from importlib.metadata import version as package_version

# autodoc imports the package from the source tree, without installing it.
sys.path.insert(0, os.path.abspath("../src"))

project = "django-tasks-temporal"
author = "Alexander Lukens"
copyright = "2026, Alexander Lukens"

release = package_version("django-tasks-temporal")
version = ".".join(release.split(".")[:2])

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
]

autodoc_member_order = "bysource"
autodoc_typehints = "description"

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_use_admonition_for_examples = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "django": (
        "https://docs.djangoproject.com/en/stable/",
        "https://docs.djangoproject.com/en/stable/_objects/",
    ),
    "temporalio": ("https://python.temporal.io", None),
}

html_theme = "furo"
html_title = "django-tasks-temporal"

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
