# -*- coding: utf-8 -*-
from kiara.models.filesystem import KiaraFileBundle
from kiara.models.values.value import Value


def check_downloaded_file(file_bundle: Value):

    assert file_bundle.data_type_name == "file_bundle"
    assert file_bundle.value_size > 400000

    kiara_file_bundle: KiaraFileBundle = file_bundle.data
    assert kiara_file_bundle.__class__ == KiaraFileBundle

    assert (
        "kiara_plugin.core_types-develop/.gitignore"
        in kiara_file_bundle.included_files.keys()
    )
