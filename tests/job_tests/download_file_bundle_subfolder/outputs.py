# -*- coding: utf-8 -*-
import os

from kiara.models.filesystem import KiaraFileBundle
from kiara.models.values.value import Value


def check_downloaded_file(file_bundle: Value):
    assert file_bundle.data_type_name == "file_bundle", (
        f"Expected a file_bundle value, got: {file_bundle.data_type_name}"
    )
    assert file_bundle.value_size > 144000, (
        f"Expected a file_bundle value with size > 144000, got: {file_bundle.value_size}"
    )

    kiara_file_bundle: KiaraFileBundle = file_bundle.data
    assert kiara_file_bundle.__class__ == KiaraFileBundle, (
        f"Expected a KiaraFileBundle object, got: {kiara_file_bundle.__class__}"
    )

    assert (
        f"kiara_plugin{os.path.sep}core_types{os.path.sep}defaults.py"
        in kiara_file_bundle.included_files.keys()
    ), (
        f"Expected 'kiara_plugin{os.path.sep}core_types{os.path.sep}defaults.py' in included files, got: {kiara_file_bundle.included_files.keys()}"
    )
