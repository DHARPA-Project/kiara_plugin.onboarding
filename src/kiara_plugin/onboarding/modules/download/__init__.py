# -*- coding: utf-8 -*-
import atexit
import os
import shutil
import tempfile
from typing import Any, Dict, Union

from pydantic import Field

from kiara.exceptions import KiaraProcessingException
from kiara.models.module import KiaraModuleConfig
from kiara.models.values.value import ValueMap
from kiara.modules import KiaraModule, ValueMapSchema


class DownloadFileConfig(KiaraModuleConfig):
    attach_metadata: bool = Field(
        description="Whether to attach the download metadata to the result file.",
        default=True,
    )


class DownloadFileModule(KiaraModule):
    """Download a single file from a remote location.

    The result of this operation is a single value of type 'file' (basically an array of raw bytes + some light metadata), which can then be used in other modules to create more meaningful data structures.
    """

    _module_type_name = "download.file"
    _config_cls = DownloadFileConfig

    def create_inputs_schema(self) -> ValueMapSchema:

        result: Dict[str, Dict[str, Any]] = {
            "url": {"type": "string", "doc": "The url of the file to download."},
            "file_name": {
                "type": "string",
                "doc": "The file name to use for the downloaded file, if not provided it will be generated from the last token of the url.",
                "optional": True,
            },
        }
        return result

    def create_outputs_schema(
        self,
    ) -> ValueMapSchema:

        result: Dict[str, Dict[str, Any]] = {
            "file": {
                "type": "file",
                "doc": "The downloaded file.",
            }
        }

        return result

    def process(self, inputs: ValueMap, outputs: ValueMap):

        from kiara_plugin.onboarding.utils.download import download_file

        url = inputs.get_value_data("url")
        file_name = inputs.get_value_data("file_name")

        result_file = download_file(
            url=url,
            file_name=file_name,
            attach_metadata=self.get_config_value("attach_metadata"),
        )

        outputs.set_value("file", result_file)


class DownloadFileBundleConfig(KiaraModuleConfig):
    attach_metadata_to_bundle: bool = Field(
        description="Whether to attach the download metadata to the result file bundle instance.",
        default=True,
    )
    attach_metadata_to_files: bool = Field(
        description="Whether to attach the download metadata to each file in the resulting bundle.",
        default=False,
    )


class DownloadFileBundleModule(KiaraModule):
    """Download a file bundle from a remote location.

    This is basically just a convenience module that incorporates unpacking of the downloaded file into a folder structure, and then wrapping it into a *kiara* `file_bundle` data type.

    If the `sub_path` input is set, the whole data is downloaded anyway, but before wrapping into a `file_bundle` value, the files not in the sub-path are ignored (and thus not available later on). Make sure you
    decided whether this is ok for your use-case, if not, rather filter the `file_bundle` later in an
    extra step (for example using the `file_bundle.pick.sub_folder` operation).
    """

    _module_type_name = "download.file_bundle"
    _config_cls = DownloadFileBundleConfig

    def create_inputs_schema(self) -> ValueMapSchema:

        result: Dict[str, Dict[str, Any]] = {
            "url": {
                "type": "string",
                "doc": "The url of an archive/zip file to download.",
            },
            "sub_path": {
                "type": "string",
                "doc": "A relative path to select only a sub-folder from the archive.",
                "optional": True,
            },
        }

        return result

    def create_outputs_schema(
        self,
    ) -> ValueMapSchema:

        result: Dict[str, Dict[str, Any]] = {
            "file_bundle": {
                "type": "file_bundle",
                "doc": "The downloaded file bundle.",
            }
        }

        return result

    def process(self, inputs: ValueMap, outputs: ValueMap):

        from urllib.parse import urlparse

        from kiara.models.filesystem import KiaraFile, KiaraFileBundle
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

        sub_path: Union[None, str] = inputs.get_value_data("sub_path")
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        atexit.register(tmp_file.close)

        kiara_file: KiaraFile
        file_hash: int

        kiara_file, file_hash = download_file(
            url, target=tmp_file.name, attach_metadata=True, return_md5_hash=True
        )

        assert kiara_file.path == tmp_file.name

        out_dir = tempfile.mkdtemp()

        def del_out_dir():
            shutil.rmtree(out_dir, ignore_errors=True)

        atexit.register(del_out_dir)

        error = None
        try:
            shutil.unpack_archive(tmp_file.name, out_dir)
        except Exception:
            # try patool, maybe we're lucky
            try:
                import patoolib

                patoolib.extract_archive(tmp_file.name, outdir=out_dir)
            except Exception as e:
                error = e

        if error is not None:
            raise KiaraProcessingException(f"Could not extract archive: {error}.")

        path = out_dir
        if sub_path:
            path = os.path.join(out_dir, sub_path)
        bundle = KiaraFileBundle.import_folder(path)

        attach_metadata_to_bundle = self.get_config_value("attach_metadata_to_bundle")
        if attach_metadata_to_bundle:
            metadata = kiara_file.metadata["download_info"]
            bundle.metadata["download_info"] = metadata

        attach_metadata_to_files = self.get_config_value("attach_metadata_to_files")
        if attach_metadata_to_files or True:
            metadata = kiara_file.metadata["download_info"]
            for kf in bundle.included_files.values():
                kf.metadata["download_info"] = metadata

        outputs.set_value("file_bundle", bundle)
