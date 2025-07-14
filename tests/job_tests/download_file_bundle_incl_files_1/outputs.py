# -*- coding: utf-8 -*-
import os

from kiara.models.filesystem import KiaraFileBundle
from kiara.models.values.value import Value


def check_downloaded_files(file_bundle: Value):
    assert file_bundle.data_type_name == "file_bundle", (
        f"Expected a file_bundle value, got: {file_bundle.data_type_name}"
    )
    assert file_bundle.value_size < 400000, (
        f"Expected a file_bundle value with size < 400000, got: {file_bundle.value_size}"
    )

    assert file_bundle.value_size > 20000, (
        f"Expected a file_bundle value with size < 20000, got: {file_bundle.value_size}"
    )

    kiara_file_bundle: KiaraFileBundle = file_bundle.data
    assert kiara_file_bundle.__class__ == KiaraFileBundle, (
        f"Expected a KiaraFileBundle object, got: {kiara_file_bundle.__class__}"
    )

    assert (
        f"kiara_plugin.core_types-main{os.path.sep}.gitignore"
        not in kiara_file_bundle.included_files.keys()
    ), (
        f"Expected 'kiara_plugin.core_types-main{os.path.sep}.gitignore' in included files"
    )

    assert (
        f"kiara_plugin.core_types-develop{os.path.sep}.cruft.json"
        in kiara_file_bundle.included_files.keys()
    ), (
        f"Expected 'kiara_plugin.core_types-develop{os.path.sep}.cruft.json' in included files"
    )
