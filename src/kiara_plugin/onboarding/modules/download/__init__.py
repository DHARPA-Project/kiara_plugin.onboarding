# -*- coding: utf-8 -*-
import atexit
import os
import tempfile
from typing import TYPE_CHECKING, Any, Dict, Union

from kiara.models.values.value import ValueMap
from kiara_plugin.onboarding.modules import OnboardFileBundleModule, OnboardFileModule

if TYPE_CHECKING:
    from kiara.models.filesystem import FolderImportConfig, KiaraFile, KiaraFileBundle


class DownloadFileModule(OnboardFileModule):
    """Download a single file from a remote location.

    The result of this operation is a single value of type 'file' (basically an array of raw bytes + some light metadata), which can then be used in other modules to create more meaningful data structures.
    """

    _module_type_name = "download.file"

    def create_onboard_inputs_schema(self) -> Dict[str, Any]:
        result: Dict[str, Dict[str, Any]] = {
            "url": {"type": "string", "doc": "The url of the file to download."},
        }
        return result

    def retrieve_file(
        self, inputs: ValueMap, file_name: Union[str, None], attach_metadata: bool
    ) -> Any:
        from kiara_plugin.onboarding.utils.download import download_file

        url = inputs.get_value_data("url")

        result_file = download_file(
            url=url,
            file_name=file_name,
            attach_metadata=attach_metadata,
        )
        return result_file


class DownloadFileBundleModule(OnboardFileBundleModule):
    """Download a file bundle from a remote location.

    This is basically just a convenience module that incorporates unpacking of the downloaded file into a folder structure, and then wrapping it into a *kiara* `file_bundle` data type.

    If the `sub_path` input is set, the whole data is downloaded anyway, but before wrapping into a `file_bundle` value, the files not in the sub-path are ignored (and thus not available later on). Make sure you
    decided whether this is ok for your use-case, if not, rather filter the `file_bundle` later in an
    extra step (for example using the `file_bundle.pick.sub_folder` operation).
    """

    _module_type_name = "download.file_bundle"

    def create_onboard_inputs_schema(self) -> Dict[str, Any]:
        result: Dict[str, Dict[str, Any]] = {
            "url": {
                "type": "string",
                "doc": "The url of an archive/zip file to download.",
            }
        }

        return result

    def retrieve_archive(
        self,
        inputs: ValueMap,
        bundle_name: Union[str, None],
        attach_metadata_to_bundle: bool,
        attach_metadata_to_files: bool,
        import_config: "FolderImportConfig",
    ) -> Union["KiaraFile", "KiaraFileBundle"]:
        from urllib.parse import urlparse

        from kiara.models.filesystem import KiaraFile
        from kiara_plugin.onboarding.utils.download import download_file

        url = inputs.get_value_data("url")
        suffix = None
        try:
            parsed_url = urlparse(url)
            _, suffix = os.path.splitext(parsed_url.path)
        except Exception:
            pass
        if not suffix:
            suffix = ""

        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)

        def rm_tmp_file():
            tmp_file.close()
            os.unlink(tmp_file.name)

        atexit.register(rm_tmp_file)
        kiara_file: KiaraFile

        kiara_file = download_file(  # type: ignore
            url, target=tmp_file.name, attach_metadata=True, return_md5_hash=False
        )

        assert kiara_file.path == tmp_file.name

        return kiara_file
