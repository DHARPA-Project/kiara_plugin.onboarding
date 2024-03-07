# -*- coding: utf-8 -*-
from typing import TYPE_CHECKING, Any, Dict, Union

from kiara.exceptions import KiaraException
from kiara.models.values.value import ValueMap
from kiara_plugin.onboarding.modules import OnboardFileBundleModule, OnboardFileModule

if TYPE_CHECKING:
    from kiara.models.filesystem import FolderImportConfig, KiaraFile, KiaraFileBundle


class DownloadZenodoFileModule(OnboardFileModule):
    """Download a single file from a github repo."""

    _module_type_name = "download.file.from.zenodo"

    def create_onboard_inputs_schema(self) -> Dict[str, Any]:

        result: Dict[str, Dict[str, Any]] = {
            "doi": {"type": "string", "doc": "The DOI."},
            "path": {
                "type": "string",
                "doc": "The path to the file/file name within the dataset.",
                "optional": True,
            },
        }
        return result

    def retrieve_file(
        self, inputs: ValueMap, file_name: Union[str, None], attach_metadata: bool
    ) -> Any:

        import pyzenodo3

        from kiara_plugin.onboarding.utils.download import download_file

        doi = inputs.get_value_data("doi")
        file_path = inputs.get_value_data("path")

        if "/zenodo." not in doi:
            doi = f"10.5281/zenodo.{doi}"

        zen = pyzenodo3.Zenodo()
        record = zen.find_record_by_doi(doi)

        match = None
        for _available_file in record.data["files"]:
            if file_path == _available_file["key"]:
                match = _available_file
                break

        if not match:
            msg = "Available files:\n"
            for key in record.data["files"]:
                msg += f"  - {key['key']}\n"
            raise KiaraException(
                msg=f"Can't find file '{file_path}' in Zenodo record. {msg}"
            )

        url = match["links"]["self"]
        checksum = match["checksum"][4:]

        file_name = file_path.split("/")[-1]

        result_file: KiaraFile
        result_file, result_checksum = download_file(  # type: ignore
            url=url,
            file_name=file_name,
            attach_metadata=attach_metadata,
            return_md5_hash=True,
        )

        if checksum != result_checksum:
            raise KiaraException(
                msg=f"Can't download file '{file_name}' from zenodo, invalid checksum: {checksum} != {checksum}"
            )

        if attach_metadata:
            result_file.metadata["zenodo_record_data"] = record.data

        return result_file


class DownloadZenodoFileBundleModule(OnboardFileBundleModule):
    """Download a file bundle from a remote github repository.

    If 'sub_path' is not specified, the whole repo will be used.

    """

    _module_type_name = "download.file_bundle.from.zenodo"

    def create_onboard_inputs_schema(self) -> Dict[str, Any]:
        result: Dict[str, Dict[str, Any]] = {
            "doi": {"type": "string", "doc": "The DOI."},
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

        import pyzenodo3

        from kiara.models.filesystem import KiaraFile, KiaraFileBundle
        from kiara_plugin.onboarding.utils.download import download_file

        doi = inputs.get_value_data("doi")

        if "/zenodo." not in doi:
            doi = f"10.5281/zenodo.{doi}"

        zen = pyzenodo3.Zenodo()
        record = zen.find_record_by_doi(doi)

        base_path = KiaraFileBundle.create_tmp_dir()

        for _available_file in record.data["files"]:
            match = _available_file

            url = match["links"]["self"]
            checksum = match["checksum"][4:]

            file_path = _available_file["key"]
            full_path = base_path / file_path

            file_name = file_path.split("/")[-1]

            # TODO: filter here already, so we don't need to download files we don't want

            result_file: KiaraFile
            result_file, result_checksum = download_file(  # type: ignore
                url=url,
                target=full_path.as_posix(),
                file_name=file_name,
                attach_metadata=True,
                return_md5_hash=True,
            )

            if checksum != result_checksum:
                raise KiaraException(
                    msg=f"Can't download file '{file_name}' from zenodo, invalid checksum: {checksum} != {result_checksum}"
                )

        if not bundle_name:
            bundle_name = doi
        result = KiaraFileBundle.import_folder(
            source=base_path.as_posix(),
            bundle_name=bundle_name,
            import_config=import_config,
        )
        if attach_metadata_to_bundle:
            result.metadata["zenodo_record_data"] = record.data

        if attach_metadata_to_files:
            for file in result.included_files.values():
                file.metadata["zenodo_record_data"] = record.data

        return result
