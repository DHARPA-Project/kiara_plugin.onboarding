# -*- coding: utf-8 -*-
from kiara.models.filesystem import KiaraFile
from kiara.models.values.value import Value


def check_downloaded_file(file: Value):
    assert file.data_type_name == "file"
    assert file.value_size > 2000

    kiara_file: KiaraFile = file.data
    assert kiara_file.__class__ == KiaraFile

    assert "# kiara" in kiara_file.read_text()
