# -*- coding: utf-8 -*-
from typing import TYPE_CHECKING, Any, Dict, Union

from kiara.models.values.value import ValueMap
from kiara_plugin.onboarding.modules import OnboardFileBundleModule, OnboardFileModule

if TYPE_CHECKING:
    from kiara.models.filesystem import FolderImportConfig, KiaraFile, KiaraFileBundle


class DownloadGithubFileModule(OnboardFileModule):
    """Download a single file from a github repo."""

    _module_type_name = "download.file.from.github"

    def create_onboard_inputs_schema(self) -> Dict[str, Any]:
        result: Dict[str, Dict[str, Any]] = {
            "user": {"type": "string", "doc": "The username/org-name."},
            "repo": {"type": "string", "doc": "The repository name."},
            "branch": {
                "type": "string",
                "doc": "The branch (or tag) name. If not specified, the 'main' branch name will be used.",
                "default": "main",
            },
            "path": {
                "type": "string",
                "doc": "The path to the file in the repository. Make sure not to specify a directory here, only a file path.",
            },
        }
        return result

    def retrieve_file(
        self, inputs: ValueMap, file_name: Union[str, None], attach_metadata: bool
    ) -> Any:
        from kiara_plugin.onboarding.utils.download import download_file

        user = inputs.get_value_data("user")
        repo = inputs.get_value_data("repo")
        branch = inputs.get_value_data("branch")
        sub_path = inputs.get_value_data("path")

        url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{sub_path}"

        result_file: KiaraFile = download_file(  # type: ignore
            url=url, file_name=file_name, attach_metadata=attach_metadata
        )
        return result_file


class DownloadGithbFileBundleModule(OnboardFileBundleModule):
    """Download a file bundle from a remote github repository.

    If 'sub_path' is not specified, the whole repo will be used.

    """

    _module_type_name = "download.file_bundle.from.github"

    def create_onboard_inputs_schema(self) -> Dict[str, Any]:
        result: Dict[str, Dict[str, Any]] = {
            "user": {"type": "string", "doc": "The username/org-name."},
            "repo": {"type": "string", "doc": "The repository name."},
            "branch": {
                "type": "string",
                "doc": "The branch (or tag) name. If not specified, the default branch will be used.",
                "optional": True,
            },
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
        from kiara_plugin.onboarding.utils.download import download_file

        user = inputs.get_value_data("user")
        repo = inputs.get_value_data("repo")
        branch = inputs.get_value_data("branch")
        if not branch:
            branch = "main"

        url = f"https://github.com/{user}/{repo}/archive/refs/heads/{branch}.zip"

        file_name = f"{repo}-{branch}.zip"
        result_file: KiaraFile = download_file(  # type: ignore
            url=url, file_name=file_name, attach_metadata=True, return_md5_hash=False
        )
        return result_file
