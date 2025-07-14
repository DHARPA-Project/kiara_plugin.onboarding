# -*- coding: utf-8 -*-
import atexit
import os
import tempfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple, Type, Union

from pydantic import BaseModel, Field

from kiara.exceptions import KiaraException
from kiara.models.filesystem import FolderImportConfig, KiaraFile, KiaraFileBundle
from kiara.utils.dates import get_current_time_incl_timezone
from kiara.utils.files import unpack_archive
from kiara.utils.json import orjson_dumps
from kiara_plugin.onboarding.models import OnboardDataModel


class DownloadMetadata(BaseModel):
    url: str = Field(description="The url of the download request.")
    response_headers: List[Dict[str, str]] = Field(
        description="The response headers of the download request."
    )
    request_time: datetime = Field(description="The time the request was made.")
    download_time_in_seconds: float = Field(
        description="How long the download took in seconds."
    )


class DownloadBundleMetadata(DownloadMetadata):
    import_config: FolderImportConfig = Field(
        description="The import configuration that was used to import the files from the source bundle."
    )


@lru_cache()
def get_onboard_model_cls(
    onboard_type: Union[str, None],
) -> Union[None, Type[OnboardDataModel]]:
    if not onboard_type:
        return None

    from kiara.registries.models import ModelRegistry

    model_registry = ModelRegistry.instance()
    model_cls = model_registry.get_model_cls(onboard_type, OnboardDataModel)
    return model_cls  # type: ignore


def download_file(
    url: str,
    target: Union[str, None] = None,
    file_name: Union[str, None] = None,
    attach_metadata: bool = True,
    return_md5_hash: bool = False,
) -> Union[KiaraFile, Tuple[KiaraFile, str]]:
    import hashlib

    import httpx

    if not file_name:
        # TODO: make this smarter, using content-disposition headers if available
        file_name = url.split("/")[-1]

    if not target:
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_name)

        def rm_tmp_file():
            tmp_file.close()
            os.unlink(tmp_file.name)

        atexit.register(rm_tmp_file)

        _target = Path(tmp_file.name)
    else:
        _target = Path(target)
        _target.parent.mkdir(parents=True, exist_ok=True)

    if return_md5_hash:
        hash_md5 = hashlib.md5()  # noqa

    history = []

    request_time = get_current_time_incl_timezone()

    with open(_target, "wb") as f:
        with httpx.stream("GET", url, follow_redirects=True) as r:
            if r.status_code < 200 or r.status_code >= 399:
                raise KiaraException(
                    f"Could not download file from {url}: status code {r.status_code}."
                )
            history.append(dict(r.headers))
            for h in r.history:
                history.append(dict(h.headers))
            for data in r.iter_bytes():
                if return_md5_hash:
                    hash_md5.update(data)
                f.write(data)

    result_file = KiaraFile.load_file(_target.as_posix(), file_name)
    now_time = get_current_time_incl_timezone()
    delta = (now_time - request_time).total_seconds()
    if attach_metadata:
        metadata = {
            "url": url,
            "response_headers": history,
            "request_time": request_time,
            "download_time_in_seconds": delta,
        }
        _metadata: DownloadMetadata = DownloadMetadata(**metadata)
        result_file.metadata["download_info"] = _metadata.model_dump()
        result_file.metadata_schemas["download_info"] = orjson_dumps(
            DownloadMetadata.model_json_schema()
        )

    if return_md5_hash:
        return result_file, hash_md5.hexdigest()
    else:
        return result_file


def download_file_bundle(
    url: str,
    attach_metadata: bool = True,
    import_config: Union[FolderImportConfig, None] = None,
) -> KiaraFileBundle:
    import shutil
    from datetime import datetime
    from urllib.parse import urlparse

    import httpx
    import pytz

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

    history = []
    # datetime.utcnow().replace(tzinfo=pytz.utc)
    with open(tmp_file.name, "wb") as f:
        with httpx.stream("GET", url, follow_redirects=True) as r:
            history.append(dict(r.headers))
            for h in r.history:
                history.append(dict(h.headers))
            for data in r.iter_bytes():
                f.write(data)

    out_dir = tempfile.mkdtemp()

    def del_out_dir():
        shutil.rmtree(out_dir, ignore_errors=True)

    atexit.register(del_out_dir)

    # error = None
    # try:
    #     shutil.unpack_archive(tmp_file.name, out_dir)
    # except Exception:
    #     # try patool, maybe we're lucky
    #     try:
    #         import patoolib
    #
    #         patoolib.extract_archive(tmp_file.name, outdir=out_dir)
    #     except Exception as e:
    #         error = e
    #
    # if error is not None:
    #     raise KiaraException(msg=f"Could not extract archive: {error}.")

    unpack_archive(tmp_file.name, out_dir)
    bundle = KiaraFileBundle.import_folder(out_dir, import_config=import_config)

    if import_config is None:
        ic_dict = {}
    elif isinstance(import_config, FolderImportConfig):
        ic_dict = import_config.dict()
    else:
        ic_dict = import_config
    if attach_metadata:
        metadata = {
            "url": url,
            "response_headers": history,
            "request_time": datetime.utcnow().replace(tzinfo=pytz.utc).isoformat(),
            "import_config": ic_dict,
        }
        _metadata = DownloadBundleMetadata(**metadata)
        bundle.metadata["download_info"] = _metadata.model_dump()
        bundle.metadata_schemas["download_info"] = DownloadMetadata.schema_json()

    return bundle


def find_matching_onboard_models(
    uri: str, for_bundle: bool = False
) -> Mapping[Type[OnboardDataModel], Tuple[bool, str]]:
    from kiara.registries.models import ModelRegistry

    model_registry = ModelRegistry.instance()
    onboard_models = model_registry.get_models_of_type(
        OnboardDataModel
    ).item_infos.values()

    result = {}
    onboard_model: Type[OnboardDataModel]
    for onboard_model in onboard_models:  # type: ignore
        python_cls: Type[OnboardDataModel] = onboard_model.python_class.get_class()  # type: ignore
        if for_bundle:
            result[python_cls] = python_cls.accepts_bundle_uri(uri)
        else:
            result[python_cls] = python_cls.accepts_uri(uri)

    return result


def onboard_file(
    source: str,
    file_name: Union[str, None] = None,
    onboard_type: Union[str, None] = None,
    attach_metadata: bool = True,
) -> KiaraFile:
    if not onboard_type:
        model_clsses = find_matching_onboard_models(source)
        matches = [k for k, v in model_clsses.items() if v[0]]
        if not matches:
            raise KiaraException(
                msg=f"Can't onboard file from '{source}': no onboard models found that accept this source type."
            )
        elif len(matches) > 1:
            msg = "Valid onboarding types for this uri:\n\n"
            for k, v in model_clsses.items():
                if not v[0]:
                    continue
                msg += f"  - {k._kiara_model_id}: {v[1]}\n"
            raise KiaraException(
                msg=f"Can't onboard file from '{source}': multiple onboard models found that accept this source type.\n\n{msg}"
            )

        model_cls: Type[OnboardDataModel] = matches[0]

    else:
        model_cls = get_onboard_model_cls(onboard_type=onboard_type)  # type: ignore
        if not model_cls:
            raise KiaraException(
                msg=f"Can't onboard file from '{source}' using onboard type '{onboard_type}': no onboard model found with this name."
            )  # type: ignore

        valid, msg = model_cls.accepts_uri(source)
        if not valid:
            raise KiaraException(
                msg=f"Can't onboard file from '{source}' using onboard type '{model_cls._kiara_model_id}': {msg}"
            )  # type: ignore

    if not model_cls.get_config_fields():
        model = model_cls()
    else:
        raise NotImplementedError()

    result = model.retrieve(
        uri=source, file_name=file_name, attach_metadata=attach_metadata
    )
    if not result:
        raise KiaraException(
            msg=f"Can't onboard file from '{source}' using onboard type '{model_cls._kiara_model_id}': no result data retrieved. This is most likely a bug."
        )  # type: ignore

    if isinstance(result, str):
        data = KiaraFile.load_file(result, file_name=file_name)
    elif not isinstance(result, KiaraFile):
        raise KiaraException(
            "Can't onboard file: onboard model returned data that is not a file. This is most likely a bug."
        )
    else:
        data = result

    return data


def onboard_file_bundle(
    source: str,
    import_config: Union[FolderImportConfig, None],
    onboard_type: Union[str, None] = None,
    attach_metadata: bool = True,
) -> KiaraFileBundle:
    if not onboard_type:
        model_clsses = find_matching_onboard_models(uri=source, for_bundle=True)
        matches = [k for k, v in model_clsses.items() if v[0]]
        if not matches:
            raise KiaraException(
                msg=f"Can't onboard file from '{source}': no onboard models found that accept this source type."
            )
        elif len(matches) > 1:
            msg = "Valid onboarding types for this uri:\n\n"
            for k, v in model_clsses.items():
                if not v[0]:
                    continue
                msg += f"  - {k._kiara_model_id}: {v[1]}\n"
            raise KiaraException(
                msg=f"Can't onboard file from '{source}': multiple onboard models found that accept this source type.\n\n{msg}"
            )

        model_cls: Type[OnboardDataModel] = matches[0]

    else:
        model_cls = get_onboard_model_cls(onboard_type=onboard_type)  # type: ignore
        if not model_cls:
            raise KiaraException(
                msg=f"Can't onboard file from '{source}' using onboard type '{onboard_type}': no onboard model found with this name."
            )  # type: ignore
        valid, msg = model_cls.accepts_bundle_uri(source)
        if not valid:
            raise KiaraException(
                msg=f"Can't onboard file from '{source}' using onboard type '{model_cls._kiara_model_id}': {msg}"
            )  # type: ignore

    if not model_cls.get_config_fields():
        model = model_cls()
    else:
        raise NotImplementedError()

    if not import_config:
        import_config = FolderImportConfig()

    try:
        result: Union[None, KiaraFileBundle] = model.retrieve_bundle(
            uri=source, import_config=import_config, attach_metadata=attach_metadata
        )

        if not result:
            raise KiaraException(
                msg=f"Can't onboard file bundle from '{source}' using onboard type '{model_cls._kiara_model_id}': no result data retrieved. This is most likely a bug."
            )  # type: ignore

        if isinstance(result, str):
            result = KiaraFileBundle.import_folder(source=result)

    except NotImplementedError:
        result = None

    if not result:
        result_file = model.retrieve(
            uri=source, file_name=None, attach_metadata=attach_metadata
        )
        if not result_file:
            raise KiaraException(
                msg=f"Can't onboard file bundle from '{source}' using onboard type '{model_cls._kiara_model_id}': no result data retrieved. This is most likely a bug."
            )  # type: ignore

        if isinstance(result, str):
            imported_bundle_file = KiaraFile.load_file(result_file)  # type: ignore
        elif not isinstance(result_file, KiaraFile):
            raise KiaraException(
                "Can't onboard file: onboard model returned data that is not a file. This is most likely a bug."
            )
        else:
            imported_bundle_file = result_file

        imported_bundle = KiaraFileBundle.from_archive_file(
            imported_bundle_file, import_config=import_config
        )
    else:
        imported_bundle = result

    return imported_bundle


def download_zenodo_file_bundle(
    doi: str,
    version: Union[None, str],
    attach_metadata_to_bundle: bool,
    attach_metadata_to_files: bool,
    bundle_name: Union[str, None] = None,
    import_config: Union[None, Mapping[str, Any], FolderImportConfig] = None,
) -> KiaraFileBundle:
    import pyzenodo3

    from kiara.models.filesystem import KiaraFile, KiaraFileBundle

    if "/zenodo." not in doi:
        doi = f"10.5281/zenodo.{doi}"

    zen = pyzenodo3.Zenodo()

    if version:
        raise NotImplementedError("Downloading versioned records is not yet supported.")

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
