# -*- coding: utf-8 -*-
import abc
import atexit
import shutil
import tempfile
from typing import TYPE_CHECKING, Any, Dict, List, Union

from pydantic import Field

from kiara.exceptions import KiaraException, KiaraProcessingException
from kiara.models.module import KiaraModuleConfig
from kiara.models.values.value import ValueMap
from kiara.modules import KiaraModule, ValueMapSchema

if TYPE_CHECKING:
    from kiara.models.filesystem import FolderImportConfig, KiaraFile, KiaraFileBundle


class OnboardFileConfig(KiaraModuleConfig):
    result_file_name: Union[str, None] = Field(
        description="The file name to use for the downloaded file, if not provided it will be auto-generated.",
        default=None,
    )
    attach_metadata: Union[bool, None] = Field(
        description="Whether to attach metadata. If 'None', a user input will be created.",
        default=True,
    )


ONBOARDING_MODEL_NAME_PREFIX = "onboarding.file.from."


class OnboardFileModule(KiaraModule):
    """A generic module that imports a file from one of several possible sources."""

    _config_cls = OnboardFileConfig

    @abc.abstractmethod
    def create_onboard_inputs_schema(self) -> Dict[str, Any]:
        pass

    def create_inputs_schema(
        self,
    ) -> ValueMapSchema:
        result = self.create_onboard_inputs_schema()

        if "file_name" in result.keys():
            raise KiaraException(
                msg="The 'file_name' input is not allowed in the onboard inputs schema for an implementing class of 'OnboardFileModule'."
            )
        result["file_name"] = {
            "type": "string",
            "doc": "The file name to use for the downloaded file, if not provided it will be auto-generated.",
            "optional": True,
        }

        if "attach_metadata" in result.keys():
            raise KiaraException(
                msg="The 'attach_metadata' input is not allowed in the onboard inputs schema for an implementing class of 'OnboardFileModule'."
            )

        file_name = self.get_config_value("result_file_name")
        if file_name is None:
            result["file_name"] = {
                "type": "string",
                "doc": "The file name to use for the downloaded file, if not provided it will be generated from the last token of the url.",
                "optional": True,
            }

        attach_metadata = self.get_config_value("attach_metadata")
        if attach_metadata is None:
            result["attach_metadata"] = {
                "type": "boolean",
                "doc": "Whether to attach onboarding metadata to the result file.",
                "default": True,
            }

        return result

    def create_outputs_schema(
        self,
    ) -> ValueMapSchema:
        result = {"file": {"type": "file", "doc": "The file that was onboarded."}}

        return result

    @abc.abstractmethod
    def retrieve_file(
        self, inputs: ValueMap, file_name: Union[str, None], attach_metadata: bool
    ) -> "KiaraFile":
        pass

    def process(self, inputs: ValueMap, outputs: ValueMap):
        if "file_name" not in inputs.keys():
            file_name = self.get_config_value("file_name")
        else:
            file_name = inputs.get_value_data("file_name")

        if "attach_metadata" not in inputs.keys():
            # must be 'True' or 'False', otherwise we'd have an input
            attach_metadata: bool = self.get_config_value("attach_metadata")
        else:
            attach_metadata = inputs.get_value_data("attach_metadata")

        result = self.retrieve_file(inputs, file_name, attach_metadata)

        outputs.set_value("file", result)


class OnboardFileBundleConfig(KiaraModuleConfig):
    result_bundle_name: Union[str, None] = Field(
        description="The bundle name use for the downloaded file, if not provided it will be auto-generated.",
        default=None,
    )

    attach_metadata_to_bundle: Union[bool, None] = Field(
        description="Whether to attach the download metadata to the result file bundle instance. If 'None', a user input will be created.",
        default=True,
    )
    attach_metadata_to_files: Union[bool, None] = Field(
        description="Whether to attach the download metadata to each file in the resulting bundle.",
        default=False,
    )
    sub_path: Union[None, str] = Field(description="The sub path to use.", default=None)
    include_files: Union[None, List[str]] = Field(
        description="List of file types (strings) to include. A match happens if the end of the filename matches a token in this list.",
        default=None,
    )
    exclude_files: Union[None, List[str]] = Field(
        description="List of file types (strings) to exclude. A match happens if the end of the filename matches a token in this list.",
        default=None,
    )
    exclude_dirs: Union[None, List[str]] = Field(
        description="Exclude directories that end with one of those tokens (list of strings).",
        default=None,
    )


class OnboardFileBundleModule(KiaraModule):
    """A generic module that imports a file from one of several possible sources."""

    _config_cls = OnboardFileBundleConfig

    @abc.abstractmethod
    def create_onboard_inputs_schema(self) -> Dict[str, Any]:
        pass

    def create_inputs_schema(
        self,
    ) -> ValueMapSchema:
        result = self.create_onboard_inputs_schema()

        for forbidden in [
            "bundle_name",
            "attach_metadata_to_bundle",
            "attach_metadata_to_files",
            "sub_path",
            "include_files",
            "exclude_files",
            "exclude_dirs",
        ]:
            if forbidden in result.keys():
                raise KiaraException(
                    msg=f"The '{forbidden}' input is not allowed in the onboard inputs schema for an implementing class of 'OnboardFileBundleModule'."
                )

        if self.get_config_value("result_bundle_name") is None:
            result["bundle_name"] = {
                "type": "string",
                "doc": "The bundle name use for the downloaded file, if not provided it will be autogenerated.",
                "optional": True,
            }

        if self.get_config_value("attach_metadata_to_bundle") is None:
            result["attach_metadata_to_bundle"] = {
                "type": "boolean",
                "doc": "Whether to attach the download metadata to the result file bundle instance.",
                "default": True,
            }
        if self.get_config_value("attach_metadata_to_files") is None:
            result["attach_metadata_to_bundle"] = {
                "type": "boolean",
                "doc": "Whether to attach the download metadata to each file in the resulting bundle.",
                "default": False,
            }

        if self.get_config_value("sub_path") is None:
            result["sub_path"] = {
                "type": "string",
                "doc": "The sub path to use. If not specified, the root of the source folder will be used.",
                "optional": True,
            }
        if self.get_config_value("include_files") is None:
            result["include_files"] = {
                "type": "list",
                "doc": "Include files that end with one of those tokens. If not specified, all file extensions are included.",
                "optional": True,
            }

        if self.get_config_value("exclude_files") is None:
            result["exclude_files"] = {
                "type": "list",
                "doc": "Exclude files that end with one of those tokens. If not specified, no file extensions are excluded.",
                "optional": True,
            }
        if self.get_config_value("exclude_dirs") is None:
            result["exclude_dirs"] = {
                "type": "list",
                "doc": "Exclude directories that end with one of those tokens. If not specified, no directories are excluded.",
                "optional": True,
            }

        return result

    def create_outputs_schema(
        self,
    ) -> ValueMapSchema:
        result = {
            "file_bundle": {
                "type": "file_bundle",
                "doc": "The file_bundle that was onboarded.",
            }
        }
        return result

    def process(self, inputs: ValueMap, outputs: ValueMap):
        from kiara.models.filesystem import FolderImportConfig, KiaraFileBundle

        bundle_name = self.get_config_value("result_bundle_name")
        if bundle_name is None:
            bundle_name = inputs.get_value_data("bundle_name")

        sub_path = self.get_config_value("sub_path")
        if sub_path is None:
            sub_path = inputs.get_value_data("sub_path")

        include = self.get_config_value("include_files")
        if include is None:
            _include = inputs.get_value_data("include_files")
            if _include:
                include = _include.list_data
        exclude = self.get_config_value("exclude_files")
        if exclude is None:
            _exclude = inputs.get_value_data("exclude_files")
            if _exclude:
                exclude = _exclude.list_data
        exclude_dirs = self.get_config_value("exclude_dirs")
        if exclude_dirs is None:
            _exclude_dirs = inputs.get_value_data("exclude_dirs")
            if _exclude_dirs:
                exclude_dirs = _exclude_dirs.list_data

        import_config_data = {
            "sub_path": sub_path,
        }
        if include:
            import_config_data["include_files"] = include
        if exclude:
            import_config_data["exclude_files"] = exclude
        if exclude_dirs:
            import_config_data["exclude_dirs"] = exclude_dirs

        import_config = FolderImportConfig(**import_config_data)

        attach_metadata_to_bundle = self.get_config_value("attach_metadata_to_bundle")
        if attach_metadata_to_bundle is None:
            attach_metadata_to_bundle = inputs.get_value_data(
                "attach_metadata_to_bundle"
            )

        attach_metadata_to_files = self.get_config_value("attach_metadata_to_files")
        if attach_metadata_to_files is None:
            attach_metadata_to_files = inputs.get_value_data("attach_metadata_to_files")

        archive = self.retrieve_archive(
            inputs=inputs,
            bundle_name=bundle_name,
            attach_metadata_to_bundle=attach_metadata_to_bundle,
            attach_metadata_to_files=attach_metadata_to_files,
            import_config=import_config,
        )
        if isinstance(archive, KiaraFileBundle):
            result = archive
        else:
            result = self.extract_archive(
                archive_file=archive,
                bundle_name=bundle_name,
                attach_metadata_to_bundle=attach_metadata_to_bundle,
                attach_metadata_to_files=attach_metadata_to_files,
                import_config=import_config,
            )

        outputs.set_value("file_bundle", result)

    @abc.abstractmethod
    def retrieve_archive(
        self,
        inputs: ValueMap,
        bundle_name: Union[str, None],
        attach_metadata_to_bundle: bool,
        attach_metadata_to_files: bool,
        import_config: "FolderImportConfig",
    ) -> Union["KiaraFile", "KiaraFileBundle"]:
        """Retrieve an archive file, or the actual result file bundle."""

    def extract_archive(
        self,
        archive_file: "KiaraFile",
        bundle_name: Union[str, None],
        attach_metadata_to_bundle: bool,
        attach_metadata_to_files: bool,
        import_config: "FolderImportConfig",
    ) -> "KiaraFileBundle":
        """Extract the archive file that was returned in 'retrieve_archive'."""

        from kiara.models.filesystem import KiaraFileBundle

        out_dir = tempfile.mkdtemp()

        def del_out_dir():
            shutil.rmtree(out_dir, ignore_errors=True)

        atexit.register(del_out_dir)

        error = None
        try:
            shutil.unpack_archive(archive_file.path, out_dir)
        except Exception:
            # try patool, maybe we're lucky
            try:
                import patoolib

                patoolib.extract_archive(archive_file.path, outdir=out_dir)
            except Exception as e:
                error = e

        if error is not None:
            raise KiaraProcessingException(f"Could not extract archive: {error}.")

        path = out_dir

        if not bundle_name:
            bundle_name = archive_file.file_name
            if import_config.sub_path:
                bundle_name = f"{bundle_name}#{import_config.sub_path}"

        bundle = KiaraFileBundle.import_folder(
            path, bundle_name=bundle_name, import_config=import_config
        )

        if attach_metadata_to_bundle:
            metadata = archive_file.metadata["download_info"]
            bundle.metadata["download_info"] = metadata

        if attach_metadata_to_files or True:
            metadata = archive_file.metadata["download_info"]
            for kf in bundle.included_files.values():
                kf.metadata["download_info"] = metadata

        return bundle
