"""EDF biosignal harmonization: rename, resample to target rate, write schema channels only."""

from __future__ import annotations

import os
import shutil
import tempfile
from math import gcd
from typing import Any, Mapping

import numpy as np
import pyedflib
from scipy import signal

from .biosignal_schema import resolve_signals_for_file

_DIG_MIN = -32768
_DIG_MAX = 32767
_SLOW_TREND_LABELS = frozenset({"hr", "pulse", "spo2", "sao2"})
_STEP_LABELS = frozenset({"position", "oxstat"})


def channel_transform_record(
    original_label: str,
    original_rate_hz: int,
    harmonized_name: str,
    target_rate_hz: int,
    *,
    mapped: bool = True,
) -> dict[str, Any]:
    return {
        "original_label": original_label,
        "original_sample_rate_hz": original_rate_hz,
        "harmonized_name": harmonized_name,
        "harmonization_target_rate_hz": target_rate_hz,
        "mapped": mapped,
    }


def _sanitize_edf_header_bytes(header: bytearray) -> bytearray:
    header = bytearray(header)
    ns = int(header[252:256].decode().strip())

    def clean_slice(start: int, length: int) -> None:
        for i in range(start, start + length):
            if header[i] == 0:
                continue
            if header[i] < 32 or header[i] > 126:
                header[i] = ord(" ")

    clean_slice(8, 80)
    clean_slice(88, 80)
    base = 256
    for i in range(ns):
        clean_slice(base + i * 16, 16)
    off = base + ns * 16
    for i in range(ns):
        clean_slice(off + i * 80, 80)
    off += ns * 80
    for i in range(ns):
        clean_slice(off + i * 8, 8)
    off += ns * 8 * 5
    for i in range(ns):
        clean_slice(off + i * 80, 80)
    off = base + ns * 256 - ns * 32
    for i in range(ns):
        clean_slice(off + i * 32, 32)

    dim_off = base + ns * 16 + ns * 80
    for i in range(ns):
        chunk = header[dim_off + i * 8 : dim_off + (i + 1) * 8]
        if all(b in (0, ord(" ")) for b in chunk):
            header[dim_off + i * 8 : dim_off + (i + 1) * 8] = b"n/a     "
    return header


def _repair_edf_header_copy(orig_path: str) -> str:
    with open(orig_path, "rb") as src:
        main = bytearray(src.read(256))
        hdr_size = int(main[184:192].decode().strip())
        header = main + bytearray(src.read(hdr_size - 256))
        fixed = _sanitize_edf_header_bytes(header)
        fd, tmp = tempfile.mkstemp(suffix=".edf")
        os.close(fd)
        with open(tmp, "wb") as dst:
            dst.write(fixed)
            shutil.copyfileobj(src, dst)
    return tmp


def _ensure_readable_edf(orig_path: str) -> tuple[str, str | None]:
    try:
        with pyedflib.EdfReader(orig_path) as reader:
            _ = reader.signals_in_file
        return orig_path, None
    except OSError as exc:
        if "compliant" not in str(exc).lower():
            raise
    tmp = _repair_edf_header_copy(orig_path)
    return tmp, tmp


def _check_duration(reader: pyedflib.EdfReader, max_duration_h: float | None) -> bool:
    if max_duration_h is None:
        return True
    return reader.file_duration / 3600.0 <= max_duration_h


def _resample(sig: np.ndarray, old_rate: int, new_rate: int) -> np.ndarray:
    if new_rate == old_rate:
        return sig.copy()
    g = gcd(new_rate, old_rate)
    return signal.resample_poly(sig, new_rate // g, old_rate // g)


def _block_representative_downsample(
    sig: np.ndarray,
    old_rate: int,
    new_rate: int,
    *,
    step_like: bool = False,
) -> np.ndarray:
    if new_rate >= old_rate:
        return _resample(sig, old_rate, new_rate)
    n_out = max(1, int(round(len(sig) * (new_rate / old_rate))))
    edges = np.linspace(0, len(sig), n_out + 1).astype(int)
    out = np.empty(n_out, dtype=float)
    for i in range(n_out):
        i0, i1 = edges[i], edges[i + 1]
        if i1 <= i0:
            i1 = min(i0 + 1, len(sig))
        blk = sig[i0:i1]
        if blk.size == 0:
            out[i] = float(sig[min(i0, len(sig) - 1)])
            continue
        if step_like:
            rounded = np.round(blk).astype(int)
            vals, cnts = np.unique(rounded, return_counts=True)
            out[i] = float(vals[int(np.argmax(cnts))])
        else:
            out[i] = float(np.median(blk))
    return out


def _phys_range_from_header(p0: float, p1: float) -> tuple[float, float] | None:
    if p0 > p1:
        p0, p1 = p1, p0
    if p0 == p1:
        return None
    return p0, p1


def _clip_and_header(
    sig: np.ndarray,
    label: str,
    new_rate: int,
    orig_dimension: str,
    *,
    clip_range: tuple[float, float] | None = None,
) -> tuple[np.ndarray, dict]:
    dim = str(orig_dimension) if orig_dimension is not None else ""
    if clip_range is not None:
        p0, p1 = clip_range
        sig = np.clip(sig, p0, p1)
    else:
        p0 = float(np.min(sig))
        p1 = float(np.max(sig))
        if p0 == p1:
            p1 += 1e-6

    header = {
        "label": label,
        "dimension": dim,
        "sample_frequency": new_rate,
        "physical_min": p0,
        "physical_max": p1,
        "digital_min": _DIG_MIN,
        "digital_max": _DIG_MAX,
        "transducer": "",
        "prefilter": "",
    }
    return sig, header


def _channel_output_plan(
    ch_name: str,
    old_rate: int,
    signal_header: dict,
    signals: Mapping[str, Mapping[str, object]],
    emitted_names: set[str],
) -> tuple[int, str, tuple[float, float] | None] | None:
    if ch_name not in signals:
        return None
    new_name = str(signals[ch_name]["new_name"])
    if new_name in emitted_names:
        return None
    new_rate = int(signals[ch_name]["new_rate"])
    clip_range = _phys_range_from_header(
        signal_header["physical_min"], signal_header["physical_max"]
    )
    return new_rate, new_name, clip_range


def harmonize_edf(
    input_edf: str | os.PathLike,
    output_edf: str | os.PathLike,
    signals_to_modify: Mapping[str, Mapping[str, object]],
    *,
    max_duration_h: float | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
    """
    Read an EDF, keep schema-mapped channels only, rename and resample, write output EDF.

    Returns (success, per-channel transform log).
    """
    orig_path = str(input_edf)
    out_path = str(output_edf)
    read_path, cleanup = _ensure_readable_edf(orig_path)
    try:
        rows: list[tuple[np.ndarray, dict]] = []
        transform_log: list[dict[str, Any]] = []
        emitted_names: set[str] = set()

        with pyedflib.EdfReader(read_path) as reader:
            if not _check_duration(reader, max_duration_h):
                return False, []
            labels = [label.strip() for label in reader.getSignalLabels()]
            signals = resolve_signals_for_file(labels, signals_to_modify)

            for i in range(reader.signals_in_file):
                ch_name = labels[i]
                old_rate = int(reader.getSampleFrequency(i))
                header = reader.getSignalHeaders()[i]
                plan = _channel_output_plan(
                    ch_name, old_rate, header, signals, emitted_names
                )
                if plan is None:
                    continue

                new_rate, new_name, clip_range = plan
                sig = reader.readSignal(i)
                orig_dimension = reader.getPhysicalDimension(i)

                transform_log.append(
                    channel_transform_record(
                        ch_name,
                        old_rate,
                        new_name,
                        new_rate,
                        mapped=True,
                    )
                )
                emitted_names.add(new_name)

                lb = new_name.strip().lower()
                if new_rate == 1 and old_rate > 1 and lb in (_SLOW_TREND_LABELS | _STEP_LABELS):
                    sig = _block_representative_downsample(
                        sig,
                        old_rate,
                        new_rate,
                        step_like=(lb in _STEP_LABELS),
                    )
                else:
                    sig = _resample(sig, old_rate, new_rate)
                sig, out_header = _clip_and_header(
                    sig, new_name, new_rate, orig_dimension, clip_range=clip_range
                )
                rows.append((sig, out_header))

        if not rows:
            return False, transform_log

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with pyedflib.EdfWriter(
            out_path, n_channels=len(rows), file_type=pyedflib.FILETYPE_EDFPLUS
        ) as writer:
            writer.setSignalHeaders([row[1] for row in rows])
            writer.writeSamples([row[0] for row in rows])
        return True, transform_log
    finally:
        if cleanup:
            os.remove(cleanup)
