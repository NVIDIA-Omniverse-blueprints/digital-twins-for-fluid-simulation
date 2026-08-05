# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import hashlib
import json
import os
import uuid
import zipfile
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path

import numpy as np

import carb.tokens
from carb.settings import get_settings
from omni.cae.core import cache, usd_utils
from omni.cae.viz.execution_context import ExecutionContext
from omni.cae.viz.operator import operator
from omni.cae.schema import viz as cae_viz
from pxr import Usd, UsdUtils
from tritonclient.http import InferInput, InferRequestedOutput, InferenceServerException
from tritonclient.http.aio import InferenceServerClient
from tritonclient.utils import np_to_triton_dtype
from usdrt import Usd as UsdRT

from .results import publish_results

logger = getLogger(__name__)
_NANOVDB_OUTPUT_PREFIX = "nvdb_"


@operator()
class InferenceOperator:
    prim_type: str = "Prim"
    api_schemas: set[str] = {"RtwtInferenceAPI"}
    optional_api_schemas: set[str] = {"RtwtInferenceCacheAPI"}

    def __init__(self):
        settings = get_settings()
        self._triton_http_url = settings.get_as_string("/exts/omni.rtwt.inference/triton_http_url") or "localhost:8080"
        self._triton_timeout = settings.get_as_int("/exts/omni.rtwt.inference/triton_timeout_s") or 600
        self._triton_batch_size = settings.get_as_int("/exts/omni.rtwt.inference/triton_batch_size") or 128_000
        self._triton_stencil_size = settings.get_as_int("/exts/omni.rtwt.inference/triton_stencil_size") or 1

        self._offline_mode = settings.get_as_bool("/exts/omni.rtwt.inference/offline_mode")
        self._generate_if_missing = settings.get_as_bool("/exts/omni.rtwt.inference/generate_if_missing")

        # Triton model name + the AppState API-schema name(s) that key the cache. Both are
        # workflow vocabulary supplied by the specialization; core defaults are
        # "rtwt" and an empty list.
        self._model_name = settings.get_as_string("/exts/omni.rtwt.inference/model_name") or "rtwt"
        self._app_state_api_schemas = list(
            settings.get("/exts/omni.rtwt.inference/app_state_api_schemas") or []
        )

        raw_dir = settings.get_as_string("/exts/omni.rtwt.inference/offline_cache_dir") or ""
        # Normalize lexically (os.path.normpath) rather than via Path.resolve():
        # the latter follows symlinks before applying `..`, which for tokens like
        # ${app}/../rtwt lands in the symlink target's parent instead of the
        # intended sibling directory.
        self._offline_cache_dir: Path | None = (
            Path(os.path.normpath(carb.tokens.get_tokens_interface().resolve(raw_dir))) if raw_dir else None
        )

    async def exec(self, prim: Usd.Prim, device: str, context: ExecutionContext):
        if prim.HasAPI(cae_viz.DatasetVoxelizationAPI, "domain"):
            raise RuntimeError("DatasetVoxelizationAPI is not supported by InferenceOperator")

        use_cache = usd_utils.get_attribute(prim, "omni:rtwt:inference_cache:useCache", quiet=True) or False
        pre_caching = usd_utils.get_attribute(prim, "omni:rtwt:inference_cache:preCaching", quiet=True) or False
        requested_outputs = self._get_requested_outputs(prim)

        await self._do_inference(prim, use_cache, pre_caching, requested_outputs)

    def _get_requested_outputs(self, prim: Usd.Prim) -> list[str]:
        """Return outputs with a complete wire-output to OmniSci field mapping."""
        outputs = [
            f"{instance}"
            for instance in usd_utils.get_instances(prim, "RtwtResultFieldSelectionAPI")
            if (
                relationship := prim.GetRelationship(
                    f"omni:rtwt:result_field_selection:{instance}:target"
                )
            )
            and relationship.GetForwardedTargets()
            and usd_utils.get_attribute(
                prim, f"omni:rtwt:result_field_selection:{instance}:fieldName", quiet=True
            )
        ]
        if not outputs:
            logger.error("No complete RtwtResultFieldSelectionAPI mappings found on %s", prim.GetPath())
        else:
            logger.debug("Requesting outputs %s for %s", outputs, prim.GetPath())
        return outputs

    def _make_cache_key(self, prim: Usd.Prim, requested_outputs: list[str]) -> str:
        """Build a cache key from the configured app-state schema attribute values.

        Uses usdrt to locate the prim(s) carrying the configured AppState API
        schema(s) so the key is cheap to compute (no ExportToString) and changes
        precisely when inference inputs change. The schema name(s) come from the
        carb setting.
        """
        stage = prim.GetStage()
        stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
        stage_rt = UsdRT.Stage.Attach(stage_id)

        h = hashlib.sha256()
        h.update(str(prim.GetPath()).encode())

        for api in self._app_state_api_schemas:
            app_state_paths = stage_rt.GetPrimsWithAppliedAPIName(api)
            if not app_state_paths:
                logger.warning("_make_cache_key: no prim with %s found", api)
                continue
            app_state_prim = stage.GetPrimAtPath(str(app_state_paths[0]))
            if app_state_prim and app_state_prim.IsValid():
                defn = Usd.SchemaRegistry().FindAppliedAPIPrimDefinition(api)
                attr_names = sorted(defn.GetPropertyNames()) if defn else []
                for attr_name in attr_names:
                    if not defn.GetAttributeDefinition(attr_name):
                        # Skip properties that aren't attributes, e.g. relationships like the result field selection targets.
                        continue
                    val = app_state_prim.GetAttribute(attr_name).Get()
                    h.update(str(val).encode())

        for name in sorted(requested_outputs):
            h.update(name.encode())
        return h.hexdigest()[:16]

    def _get_cached_outputs(self, cache_key: str, requested_outputs: list[str]) -> dict[str, np.ndarray] | None:
        """Return cached numpy arrays for all requested outputs, or None on any miss."""
        result: dict[str, np.ndarray] = {}
        for output_name in [*requested_outputs, "EXTENT_MIN", "EXTENT_MAX"]:
            data = cache.get(f"omni.rtwt.inference:inputs:{cache_key}:{output_name}")
            if data is None:
                return None
            result[output_name] = data
        return result

    def _put_cached_outputs(self, prim: Usd.Prim, cache_key: str, outputs: dict[str, np.ndarray]) -> None:
        """Store triton output arrays in cache, evicted when the inference prim is deleted."""
        prim_watch = cache.PrimWatch(prim, on="delete")
        for output_name, np_array in outputs.items():
            cache.put_ex(
                f"omni.rtwt.inference:inputs:{cache_key}:{output_name}",
                np_array,
                prims=[prim_watch],
                force=True,
            )

    async def _do_inference(
        self, prim: Usd.Prim, use_cache: bool, pre_caching: bool, requested_outputs: list[str]
    ) -> None:
        prim_path = str(prim.GetPath())

        # Result-set override (comparison view): when set, show a specific baked .npz from the offline
        # cache instead of the AppState-derived live result. Disk-load-or-fail — NEVER falls through to
        # the cache-key path or Triton. The override file may carry only a subset of the requested
        # outputs (e.g. the diff has just the two scalar deltas); we tag whatever subset it contains.
        override = usd_utils.get_attribute(prim, "omni:rtwt:inference:resultSetOverride", quiet=True) or ""
        if override:
            loaded = self._read_disk_cache_file(override, requested_outputs)
            if loaded is None:
                logger.error(
                    "resultSetOverride=%r not found/loadable in offline_cache_dir; skipping (prim=%s)",
                    override, prim_path,
                )
                return
            outputs, present = loaded
            logger.info("resultSetOverride HIT %r (prim=%s, outputs=%s)", override, prim_path, present)
            if not pre_caching:
                self._store_results_from_arrays(prim, outputs, present)
            return

        cache_key = self._make_cache_key(prim, requested_outputs)
        if use_cache:
            cached_outputs = self._get_cached_outputs(cache_key, requested_outputs)
            if cached_outputs is not None:
                logger.info("Cache HIT (prim=%s)", prim_path)
                if not pre_caching:
                    self._store_results_from_arrays(prim, cached_outputs, requested_outputs)
                return
            logger.info("Cache MISS — forwarding to rtwt (prim=%s)", prim_path)

        if self._offline_mode:
            if self._offline_cache_dir is None:
                logger.error(
                    "offline_mode=true but offline_cache_dir is unset; skipping inference (prim=%s)", prim_path
                )
                return
            disk_outputs = self._read_disk_cache(cache_key, requested_outputs)
            if disk_outputs is not None:
                logger.info("Offline cache HIT (prim=%s)", prim_path)
                if not pre_caching:
                    self._store_results_from_arrays(prim, disk_outputs, requested_outputs)
                self._put_cached_outputs(prim, cache_key, disk_outputs)
                return
            if not self._generate_if_missing:
                logger.error(
                    "Offline cache miss and generate_if_missing=false; skipping inference (prim=%s)", prim_path
                )
                return
            logger.info("Offline cache MISS — forwarding to rtwt (prim=%s)", prim_path)

        usd_string = prim.GetStage().GetRootLayer().ExportToString()
        request_id = str(uuid.uuid1())
        client = InferenceServerClient(url=self._triton_http_url, verbose=False)
        try:
            response = await client.infer(
                model_name=self._model_name,
                inputs=self._create_inputs(usd_string, prim_path),
                outputs=self._create_outputs(requested_outputs),
                request_id=request_id,
                timeout=self._triton_timeout,
            )
            if err := response.as_numpy("ERROR_MESSAGE")[0].decode("utf-8"):
                logger.error("Inference server returned error: %s", err)
            else:
                numpy_outputs = {name: response.as_numpy(name) for name in [*requested_outputs, "EXTENT_MIN", "EXTENT_MAX"]}
                if not pre_caching:
                    self._store_results_from_arrays(prim, numpy_outputs, requested_outputs)
                self._put_cached_outputs(prim, cache_key, numpy_outputs)
                if self._offline_mode:
                    self._write_disk_cache(cache_key, numpy_outputs, prim, requested_outputs)
                logger.info("Inference successful (prim=%s, outputs=%s, pre_caching=%s)", prim_path, requested_outputs, pre_caching)
        except InferenceServerException as e:
            logger.error("Inference request failed: %s", e)
        except OSError as e:
            logger.error("OS error during inference: %s", e)
        finally:
            await client.close()

    def _disk_cache_path(self, cache_key: str) -> Path:
        assert self._offline_cache_dir is not None
        return self._offline_cache_dir / f"{cache_key}.npz"

    def _read_disk_cache(self, cache_key: str, requested_outputs: list[str]) -> dict[str, np.ndarray] | None:
        path = self._disk_cache_path(cache_key)
        if not path.is_file():
            return None
        try:
            with np.load(path) as npz:
                result: dict[str, np.ndarray] = {}
                for name in [*requested_outputs, "EXTENT_MIN", "EXTENT_MAX"]:
                    if name not in npz.files:
                        logger.warning("Offline cache entry at %s missing key %r; ignoring", path, name)
                        return None
                    result[name] = npz[name]
                return result
        except (OSError, zipfile.BadZipFile, ValueError) as e:
            logger.warning("Corrupt offline cache entry at %s (%s); ignoring", path, e)
            return None

    def _read_disk_cache_file(
        self, filename: str, requested_outputs: list[str]
    ) -> tuple[dict[str, np.ndarray], list[str]] | None:
        """Load a specific result-set ``.npz`` by filename from ``offline_cache_dir`` (comparison override).

        Unlike ``_read_disk_cache`` (keyed by the AppState hash and requiring every requested output),
        this loads an explicitly-named file and tolerates a SUBSET of the requested outputs — a diff
        result set carries only the scalar deltas. Returns ``(outputs, present_outputs)`` or ``None`` if
        the file is missing/corrupt or lacks the extent members.
        """
        if self._offline_cache_dir is None:
            return None
        path = self._offline_cache_dir / filename
        if not path.is_file():
            return None
        try:
            with np.load(path) as npz:
                present = [name for name in requested_outputs if name in npz.files]
                result: dict[str, np.ndarray] = {name: npz[name] for name in present}
                for ext in ("EXTENT_MIN", "EXTENT_MAX"):
                    if ext not in npz.files:
                        logger.warning("Override result set %s missing %r; ignoring", path, ext)
                        return None
                    result[ext] = npz[ext]
                return result, present
        except (OSError, zipfile.BadZipFile, ValueError) as e:
            logger.warning("Corrupt override result set at %s (%s); ignoring", path, e)
            return None

    def _write_disk_cache(
        self, cache_key: str, outputs: dict[str, np.ndarray], prim: Usd.Prim, requested_outputs: list[str]
    ) -> None:
        prim_path = str(prim.GetPath())
        path = self._disk_cache_path(cache_key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            with tmp.open("wb") as f:
                np.savez(f, **outputs)
            tmp.replace(path)
            sidecar = path.with_suffix(".json")
            sidecar.write_text(json.dumps(self._sidecar_payload(prim, requested_outputs), indent=2))
        except OSError as e:
            logger.error("Failed to write offline cache entry for %s: %s", prim_path, e)
            return
        logger.info("Wrote offline cache entry (prim=%s, key=%s)", prim_path, cache_key)

    def _sidecar_payload(self, prim: Usd.Prim, requested_outputs: list[str]) -> dict:
        stage = prim.GetStage()
        stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
        stage_rt = UsdRT.Stage.Attach(stage_id)
        app_state: dict[str, str] = {}
        for api in self._app_state_api_schemas:
            paths = stage_rt.GetPrimsWithAppliedAPIName(api)
            if not paths:
                continue
            app_state_prim = stage.GetPrimAtPath(str(paths[0]))
            defn = Usd.SchemaRegistry().FindAppliedAPIPrimDefinition(api)
            if app_state_prim and app_state_prim.IsValid() and defn:
                for name in sorted(defn.GetPropertyNames()):
                    if not defn.GetAttributeDefinition(name):
                        continue
                    app_state[name] = str(app_state_prim.GetAttribute(name).Get())
        return {
            "prim_path": str(prim.GetPath()),
            "requested_outputs": sorted(requested_outputs),
            "app_state": app_state,
            "created": datetime.now(timezone.utc).isoformat(),
        }

    def _store_results_from_arrays(self, prim: Usd.Prim, outputs: dict[str, np.ndarray], requested_outputs: list[str]) -> None:
        logger.info("Storing results for %s: %s", prim.GetPath(), requested_outputs)
        extent_min = tuple(int(component) for component in outputs["EXTENT_MIN"].ravel())
        extent_max = tuple(int(component) for component in outputs["EXTENT_MAX"].ravel())
        dimensions = tuple(extent_max[i] - extent_min[i] + 1 for i in range(3))

        # Group by result dataset so each dataset receives one atomic revision.
        grouped: dict[str, tuple[Usd.Prim, dict[str, np.ndarray]]] = {}

        for output_name in requested_outputs:
            np_array = outputs.get(output_name)
            if np_array is None:
                continue
            if not output_name.startswith(_NANOVDB_OUTPUT_PREFIX):
                raise ValueError(
                    f"RTWT result output '{output_name}' is not a NanoVDB wire output "
                    f"(expected prefix '{_NANOVDB_OUTPUT_PREFIX}')"
                )

            dataset = usd_utils.get_target_prim(
                prim, f"omni:rtwt:result_field_selection:{output_name}:target", quiet=True
            )
            field_name = usd_utils.get_attribute(
                prim, f"omni:rtwt:result_field_selection:{output_name}:fieldName", quiet=True
            )
            if not dataset or not field_name:
                continue

            dataset_key = str(dataset.GetPath())
            _, dataset_fields = grouped.setdefault(dataset_key, (dataset, {}))
            field_name = str(field_name)
            if field_name in dataset_fields:
                raise ValueError(
                    f"Multiple inference outputs map to field '{field_name}' on {dataset.GetPath()}"
                )
            dataset_fields[field_name] = np_array

        for dataset, dataset_fields in grouped.values():
            publish_results(
                dataset,
                dataset_fields,
                origin=extent_min,
                dimensions=dimensions,
            )

    def _create_inputs(self, usd_string: str, prim_path: str) -> list[InferInput]:
        inputs = []

        inputs.append(InferInput("USD_LAYER", [1], "BYTES"))
        inputs[-1].set_data_from_numpy(np.array([usd_string], dtype=np.object_))

        inputs.append(InferInput("PRIM_PATH", [1], "BYTES"))
        inputs[-1].set_data_from_numpy(np.array([prim_path], dtype=np.object_))

        inputs.append(InferInput("BATCH_SIZE", [1], np_to_triton_dtype(np.int32)))
        inputs[-1].set_data_from_numpy(np.array([self._triton_batch_size], dtype=np.int32))

        inputs.append(InferInput("STENCIL_SIZE", [1], np_to_triton_dtype(np.int32)))
        inputs[-1].set_data_from_numpy(np.array([self._triton_stencil_size], dtype=np.int32))

        return inputs

    def _create_outputs(self, requested_outputs: list[str]) -> list[InferRequestedOutput]:
        return [InferRequestedOutput(name) for name in requested_outputs] + [
            InferRequestedOutput("EXTENT_MIN"),
            InferRequestedOutput("EXTENT_MAX"),
            InferRequestedOutput("ERROR_MESSAGE"),
        ]


def scan_offline_cache_options() -> dict | None:
    """Report which AppState option values are actually present in the disk cache.

    Returns one of:
        {"enforced": False}
            offline_mode=false, or generate_if_missing=true — the runtime can
            satisfy any requested combination, so the UI need not restrict.
        {"enforced": True, "options": {short_key: [values, ...], ...}}
            offline_mode=true and generate_if_missing=false — cache misses are
            fatal, so the UI should only surface combinations for which a cache
            entry exists. Values are aggregated from each entry's JSON sidecar
            (see InferenceOperator._sidecar_payload).
        None
            offline_cache_dir is unset or unreadable; caller should treat as
            unrestricted.
    """
    settings = get_settings()
    if not (settings.get_as_bool("/exts/omni.rtwt.inference/offline_mode")
            and not settings.get_as_bool("/exts/omni.rtwt.inference/generate_if_missing")):
        return {"enforced": False}

    raw_dir = settings.get_as_string("/exts/omni.rtwt.inference/offline_cache_dir") or ""
    if not raw_dir:
        return None
    cache_dir = Path(os.path.normpath(carb.tokens.get_tokens_interface().resolve(raw_dir)))
    if not cache_dir.is_dir():
        logger.warning("scan_offline_cache_options: cache dir %s not found", cache_dir)
        return None

    per_attr: dict[str, set[str]] = {}
    for sidecar in cache_dir.glob("*.json"):
        try:
            entry = json.loads(sidecar.read_text())
        except (OSError, ValueError) as e:
            logger.warning("scan_offline_cache_options: skipping %s (%s)", sidecar, e)
            continue
        app_state = entry.get("app_state") or {}
        for full_name, raw in app_state.items():
            short = full_name.rsplit(":", 1)[-1]
            per_attr.setdefault(short, set()).add(str(raw))

    options: dict[str, list] = {}
    for short, raw_values in per_attr.items():
        try:
            options[short] = sorted(float(v) for v in raw_values)
        except ValueError:
            options[short] = sorted(raw_values)

    return {"enforced": True, "options": options}
