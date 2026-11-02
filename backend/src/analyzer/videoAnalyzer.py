from __future__ import annotations

import math
import subprocess
import struct
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO, Callable

import numpy as np


@dataclass(slots=True)
class _Atom:
    atom_type: str
    size: int
    header_size: int
    data_offset: int

    @property
    def end_offset(self) -> int:
        return self.data_offset + max(self.size - self.header_size, 0)


class VideoAnalyzer:
    """Extract MOV metadata and render SOG overlays into a copied video."""

    _PLAY_RES_X = 1920
    _PLAY_RES_Y = 1080
    _QUICKTIME_EPOCH = datetime(1904, 1, 1, tzinfo=UTC)
    _DEFAULT_OUTPUT_SUFFIX = ".mp4"
    _MAX_SOG_ALIGNMENT_DELTA_SECONDS = 5.0
    _ASS_EVENT_STEP_SECONDS = 1

    def analyze(self, file_path: str, sog_channel: str | None = None) -> dict[str, object]:
        normalized_path = self._normalize_video_path(file_path)
        return self._extract_metadata(normalized_path, sog_channel)

    def render_sog_overlay(
        self,
        *,
        file_path: str,
        overlay_layout: dict[str, list[dict[str, Any]]],
        output_dir: str | Path,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> dict[str, object]:
        normalized_path = self._normalize_video_path(file_path)
        metadata = self.analyze(str(normalized_path), sog_channel=None)
        creation_time = self._parse_creation_time(metadata)

        output_directory = Path(output_dir).expanduser()
        output_directory.mkdir(parents=True, exist_ok=True)
        output_suffix = normalized_path.suffix or self._DEFAULT_OUTPUT_SUFFIX
        output_path = output_directory / f"{normalized_path.stem}_overlay{output_suffix}"

        prepared_channels = self._prepare_overlay_channels(
            creation_time=creation_time,
            channels=(
                [
                    {
                        "position": position,
                        **channel,
                    }
                    for position, channels in overlay_layout.items()
                    for channel in channels
                ]
            ),
        )
        self._render_overlay_video(
            input_path=normalized_path,
            output_path=output_path,
            overlay_layout=self._group_prepared_channels_by_position(prepared_channels),
            duration_seconds=(
                metadata.get("movie", {}).get("duration_seconds")
                if isinstance(metadata.get("movie"), dict)
                else None
            ),
            progress_callback=progress_callback,
        )

        return {
            "file_path": str(normalized_path),
            "output_file_path": str(output_path),
            "creation_time": creation_time.isoformat(),
            "channel_count": len(prepared_channels),
        }

    def _normalize_video_path(self, file_path: str) -> Path:
        normalized_path = Path(file_path).expanduser().resolve()
        if not normalized_path.exists():
            raise FileNotFoundError(f"Video file does not exist: {normalized_path}")
        if not normalized_path.is_file():
            raise ValueError(f"Video path is not a file: {normalized_path}")
        return normalized_path

    def _extract_metadata(
        self, file_path: Path, sog_channel: str | None
    ) -> dict[str, object]:
        metadata: dict[str, object] = {
            "file_path": str(file_path),
            "file_name": file_path.name,
            "file_extension": file_path.suffix.lower(),
            "file_size_bytes": file_path.stat().st_size,
            "sog_channel": sog_channel,
            "container": {},
            "movie": {},
            "tracks": [],
        }

        with file_path.open("rb") as handle:
            file_size = metadata["file_size_bytes"]
            top_level_atoms = self._read_atoms(handle, start=0, end=file_size)
            for atom in top_level_atoms:
                if atom.atom_type == "ftyp":
                    metadata["container"] = self._parse_ftyp(handle, atom)
                elif atom.atom_type == "moov":
                    movie_metadata, tracks = self._parse_moov(handle, atom)
                    metadata["movie"] = movie_metadata
                    metadata["tracks"] = tracks

        return metadata

    def _parse_creation_time(self, metadata: dict[str, object]) -> datetime:
        movie_metadata = metadata.get("movie")
        if not isinstance(movie_metadata, dict):
            raise ValueError("Video file does not include movie metadata.")

        creation_time_raw = movie_metadata.get("creation_time")
        if not isinstance(creation_time_raw, str) or not creation_time_raw:
            raise ValueError("Video file does not include a readable creation time.")

        creation_time = datetime.fromisoformat(creation_time_raw)
        if creation_time.tzinfo is None:
            creation_time = creation_time.replace(tzinfo=UTC)
        return creation_time.astimezone(UTC)

    def _prepare_overlay_channels(
        self,
        *,
        creation_time: datetime,
        channels: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        prepared_channels: list[dict[str, Any]] = []

        for channel in channels:
            if channel.get("data_type") == "virtual_utc_time":
                prepared_channels.append(
                    {
                        "position": channel.get("position", "bottom"),
                        "name": channel["name"],
                        "unit": None,
                        "data_type": "virtual_utc_time",
                        "creation_time": creation_time,
                        "sample_seconds": np.array([], dtype=float),
                        "sample_values": [],
                    }
                )
                continue

            normalized_samples: list[tuple[float, Any]] = []
            for timestamp, value in channel["samples"]:
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
                seconds = (timestamp.astimezone(UTC) - creation_time).total_seconds()
                normalized_samples.append((seconds, value))

            if not normalized_samples:
                raise ValueError(
                    f"Selected channel '{channel['name']}' does not contain any usable samples."
                )

            normalized_samples.sort(key=lambda item: item[0])
            prepared_channels.append(
                {
                    "position": channel.get("position", "bottom"),
                    "name": channel["name"],
                    "unit": channel.get("unit"),
                    "data_type": channel.get("data_type"),
                    "creation_time": creation_time,
                    "sample_seconds": np.array(
                        [item[0] for item in normalized_samples], dtype=float
                    ),
                    "sample_values": [item[1] for item in normalized_samples],
                }
            )

        if not prepared_channels:
            raise ValueError("Select at least one channel for the video overlay.")

        return prepared_channels

    def _render_overlay_video(
        self,
        *,
        input_path: Path,
        output_path: Path,
        overlay_layout: dict[str, list[dict[str, Any]]],
        duration_seconds: float | None,
        progress_callback: Callable[[float, str], None] | None,
    ) -> None:
        try:
            import imageio_ffmpeg
        except ModuleNotFoundError as exc:  # pragma: no cover - environment-specific
            raise RuntimeError(
                "Video rendering requires imageio-ffmpeg. Install it with "
                "`pip install imageio-ffmpeg`."
            ) from exc

        if duration_seconds is None or duration_seconds <= 0:
            raise ValueError("Video file does not include a usable duration.")

        subtitle_file_path = self._write_ass_overlay_file(
            output_dir=output_path.parent,
            overlay_layout=overlay_layout,
            duration_seconds=duration_seconds,
        )
        try:
            ffmpeg_process = subprocess.Popen(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(),
                    "-y",
                    "-i",
                    str(input_path),
                    "-progress",
                    "pipe:1",
                    "-nostats",
                    "-vf",
                    f"subtitles={subtitle_file_path.name}",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    str(output_path),
                ],
                cwd=str(output_path.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if progress_callback is not None:
                progress_callback(2.0, "Starting ffmpeg render...")

            stdout_lines: list[str] = []
            assert ffmpeg_process.stdout is not None
            for raw_line in ffmpeg_process.stdout:
                line = raw_line.strip()
                stdout_lines.append(line)
                if progress_callback is not None:
                    self._handle_ffmpeg_progress_line(
                        line,
                        duration_seconds=duration_seconds,
                        progress_callback=progress_callback,
                    )

            stderr_text = ""
            if ffmpeg_process.stderr is not None:
                stderr_text = ffmpeg_process.stderr.read()

            return_code = ffmpeg_process.wait()
            if return_code != 0:
                raise subprocess.CalledProcessError(
                    return_code,
                    ffmpeg_process.args,
                    output="\n".join(stdout_lines),
                    stderr=stderr_text,
                )

            if progress_callback is not None:
                progress_callback(99.0, "Finalizing video...")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "ffmpeg could not render the annotated video.\n"
                f"stdout:\n{exc.stdout}\n\nstderr:\n{exc.stderr}"
            ) from exc
        finally:
            subtitle_file_path.unlink(missing_ok=True)

    def _handle_ffmpeg_progress_line(
        self,
        line: str,
        *,
        duration_seconds: float,
        progress_callback: Callable[[float, str], None],
    ) -> None:
        if not line or "=" not in line:
            return

        key, raw_value = line.split("=", 1)
        value = raw_value.strip()

        if key == "out_time_ms":
            try:
                out_time_ms = int(value)
            except ValueError:
                return
            processed_seconds = out_time_ms / 1_000_000
            if duration_seconds > 0:
                progress_percent = min(max((processed_seconds / duration_seconds) * 100, 0), 99)
                progress_callback(progress_percent, f"Rendering video... {progress_percent:.0f}%")
        elif key == "progress" and value == "end":
            progress_callback(100.0, "Video render completed.")

    def _write_ass_overlay_file(
        self,
        *,
        output_dir: Path,
        overlay_layout: dict[str, list[dict[str, Any]]],
        duration_seconds: float,
    ) -> Path:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".ass",
            prefix="sog_overlay_",
            dir=output_dir,
            delete=False,
        ) as subtitle_file:
            subtitle_file.write(self._build_ass_header())
            subtitle_file.write(
                "\n"
                f"{self._build_ass_style()}\n"
                "\n[Events]\n"
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            )

            whole_seconds = max(1, int(math.ceil(duration_seconds)))
            for second in range(whole_seconds):
                start_time = float(second)
                end_time = min(float(second + self._ASS_EVENT_STEP_SECONDS), duration_seconds)
                for position in ("top", "bottom", "left", "right"):
                    channels = overlay_layout.get(position, [])
                    field_positions = self._compute_field_positions(
                        field_count=len(channels),
                        overlay_position=position,
                    )
                    for channel, (x_pos, y_pos) in zip(channels, field_positions, strict=True):
                        label = self._build_channel_field_text(
                            time_seconds=start_time,
                            channel=channel,
                        )
                        subtitle_file.write(
                            "Dialogue: 0,"
                            f"{self._format_ass_timestamp(start_time)},"
                            f"{self._format_ass_timestamp(end_time)},Overlay,,0,0,0,,"
                            f"{{\\an5\\pos({x_pos},{y_pos})}}{label}\n"
                        )

        return Path(subtitle_file.name)

    def _group_prepared_channels_by_position(
        self,
        channels: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        channels_by_position: dict[str, list[dict[str, Any]]] = {}
        for channel in channels:
            position = str(channel.get("position") or "bottom")
            channels_by_position.setdefault(position, []).append(channel)
        return channels_by_position

    def _build_ass_header(self) -> str:
        return """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
"""

    def _build_ass_style(self) -> str:
        return (
            "Style: Overlay,Arial,30,&H00FFFFFF,&H000000FF,&H80121F2A,&H80121F2A,"
            "0,0,0,0,100,100,0,0,3,1,0,5,28,28,28,1"
        )

    def _format_ass_timestamp(self, seconds: float) -> str:
        total_centiseconds = max(0, int(round(seconds * 100)))
        hours, remainder = divmod(total_centiseconds, 360000)
        minutes, remainder = divmod(remainder, 6000)
        secs, centiseconds = divmod(remainder, 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

    def _escape_ass_text(self, text: str) -> str:
        escaped = text.replace("\\", r"\\")
        return escaped.replace("{", r"\{").replace("}", r"\}")

    def _build_channel_field_text(
        self,
        *,
        time_seconds: float,
        channel: dict[str, Any],
    ) -> str:
        channel_value = self._resolve_channel_value(
            time_seconds=time_seconds,
            channel=channel,
            sample_seconds=channel["sample_seconds"],
            sample_values=channel["sample_values"],
        )
        channel_name = self._format_display_name(str(channel["name"]))
        if channel_value is None:
            return (
                "{\\fs18\\b1}"
                f"{self._escape_ass_text(channel_name)}"
                "{\\r}"
                "\\N"
                "{\\fs34\\b0}n/a"
            )

        formatted_value = self._format_channel_value(
            channel_value=channel_value,
            unit=channel.get("unit"),
            data_type=channel.get("data_type"),
        )
        return (
            "{\\fs18\\b1}"
            f"{self._escape_ass_text(channel_name)}"
            "{\\r}"
            "\\N"
            "{\\fs34\\b0}"
            f"{self._escape_ass_text(formatted_value)}"
        )

    def _format_display_name(self, raw_name: str) -> str:
        normalized = raw_name.strip().upper()
        if normalized in {"TIME_UTC", "UTC_TIME"}:
            return "UTC"
        for suffix in (
            "_COGANALYZER_DEG",
            "_DEG",
            "_ANALYZER",
            "_M",
            "_S",
            "_KN",
        ):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break

        parts = [part for part in normalized.split("_") if part]
        filtered_parts = [
            part
            for part in parts
            if part not in {"ANALYZER", "DEG", "KN", "M", "S", "REL"}
        ]
        if filtered_parts:
            return " ".join(filtered_parts)
        if parts:
            return parts[0]
        return normalized

    def _compute_field_positions(
        self,
        *,
        field_count: int,
        overlay_position: str,
    ) -> list[tuple[int, int]]:
        if field_count <= 0:
            return []

        positions: list[tuple[int, int]] = []
        if overlay_position in {"top", "bottom"}:
            step_x = self._PLAY_RES_X / (field_count + 1)
            y_pos = 110 if overlay_position == "top" else self._PLAY_RES_Y - 110
            for index in range(field_count):
                positions.append((int(round(step_x * (index + 1))), y_pos))
            return positions

        step_y = self._PLAY_RES_Y / (field_count + 1)
        x_pos = 180 if overlay_position == "left" else self._PLAY_RES_X - 180
        for index in range(field_count):
            positions.append((x_pos, int(round(step_y * (index + 1)))))
        return positions

    def _format_channel_value(
        self,
        *,
        channel_value: Any,
        unit: str | None,
        data_type: str | None,
    ) -> str:
        if data_type == "boolean":
            return "yes" if bool(channel_value) else "no"

        if data_type == "string":
            return str(channel_value)

        if isinstance(channel_value, (int, float, np.integer, np.floating)):
            suffix = f" {unit}" if unit else ""
            return f"{float(channel_value):.1f}{suffix}"

        return str(channel_value)

    def _resolve_channel_value(
        self,
        *,
        time_seconds: float,
        channel: dict[str, Any] | None = None,
        sample_seconds: np.ndarray,
        sample_values: list[Any],
    ) -> Any | None:
        if channel and channel.get("data_type") == "virtual_utc_time":
            creation_time = channel.get("creation_time")
            if isinstance(creation_time, datetime):
                return (creation_time + timedelta(seconds=time_seconds)).strftime("%H:%M:%S")
            return None

        if sample_seconds.size == 0:
            return None

        index = int(np.searchsorted(sample_seconds, time_seconds))
        if index <= 0:
            closest_index = 0
        elif index >= sample_seconds.size:
            closest_index = sample_seconds.size - 1
        else:
            previous_index = index - 1
            next_index = index
            if abs(sample_seconds[previous_index] - time_seconds) <= abs(
                sample_seconds[next_index] - time_seconds
            ):
                closest_index = previous_index
            else:
                closest_index = next_index

        time_delta = abs(float(sample_seconds[closest_index]) - time_seconds)
        if time_delta > self._MAX_SOG_ALIGNMENT_DELTA_SECONDS:
            return None
        return sample_values[closest_index]

    def _parse_moov(
        self, handle: BinaryIO, moov_atom: _Atom
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        movie_metadata: dict[str, object] = {}
        tracks: list[dict[str, object]] = []

        for atom in self._read_child_atoms(handle, moov_atom):
            if atom.atom_type == "mvhd":
                movie_metadata = self._parse_mvhd(handle, atom)
            elif atom.atom_type == "trak":
                tracks.append(self._parse_trak(handle, atom))

        return movie_metadata, tracks

    def _parse_trak(self, handle: BinaryIO, trak_atom: _Atom) -> dict[str, object]:
        track_metadata: dict[str, object] = {}

        for atom in self._read_child_atoms(handle, trak_atom):
            if atom.atom_type == "tkhd":
                track_metadata.update(self._parse_tkhd(handle, atom))
            elif atom.atom_type == "mdia":
                track_metadata.update(self._parse_mdia(handle, atom))

        return track_metadata

    def _parse_mdia(self, handle: BinaryIO, mdia_atom: _Atom) -> dict[str, object]:
        media_metadata: dict[str, object] = {}

        for atom in self._read_child_atoms(handle, mdia_atom):
            if atom.atom_type == "mdhd":
                media_metadata.update(self._parse_mdhd(handle, atom))
            elif atom.atom_type == "hdlr":
                media_metadata.update(self._parse_hdlr(handle, atom))

        return media_metadata

    def _parse_ftyp(self, handle: BinaryIO, atom: _Atom) -> dict[str, object]:
        payload = self._read_payload(handle, atom)
        if len(payload) < 8:
            return {}

        compatible_brands = [
            payload[index : index + 4].decode("latin-1", errors="replace")
            for index in range(8, len(payload), 4)
            if len(payload[index : index + 4]) == 4
        ]
        return {
            "major_brand": payload[0:4].decode("latin-1", errors="replace"),
            "minor_version": struct.unpack(">I", payload[4:8])[0],
            "compatible_brands": compatible_brands,
        }

    def _parse_mvhd(self, handle: BinaryIO, atom: _Atom) -> dict[str, object]:
        payload = self._read_payload(handle, atom)
        if len(payload) < 24:
            return {}

        version = payload[0]
        if version == 1 and len(payload) >= 112:
            creation_time, modification_time, timescale, duration = struct.unpack(
                ">QQIQ", payload[4:32]
            )
            next_track_id = struct.unpack(">I", payload[108:112])[0]
        elif len(payload) >= 100:
            creation_time, modification_time, timescale, duration = struct.unpack(
                ">IIII", payload[4:20]
            )
            next_track_id = struct.unpack(">I", payload[96:100])[0]
        else:
            return {}

        return {
            "timescale": timescale,
            "duration_seconds": self._duration_seconds(duration, timescale),
            "creation_time": self._quicktime_timestamp_to_iso(creation_time),
            "modification_time": self._quicktime_timestamp_to_iso(modification_time),
            "next_track_id": next_track_id,
        }

    def _parse_tkhd(self, handle: BinaryIO, atom: _Atom) -> dict[str, object]:
        payload = self._read_payload(handle, atom)
        if len(payload) < 84:
            return {}

        version = payload[0]
        if version == 1 and len(payload) >= 104:
            track_id = struct.unpack(">I", payload[20:24])[0]
            duration = struct.unpack(">Q", payload[28:36])[0]
            volume_fixed = struct.unpack(">H", payload[72:74])[0]
            width_fixed = struct.unpack(">I", payload[96:100])[0]
            height_fixed = struct.unpack(">I", payload[100:104])[0]
        else:
            track_id = struct.unpack(">I", payload[12:16])[0]
            duration = struct.unpack(">I", payload[20:24])[0]
            volume_fixed = struct.unpack(">H", payload[60:62])[0]
            width_fixed = struct.unpack(">I", payload[76:80])[0]
            height_fixed = struct.unpack(">I", payload[80:84])[0]

        return {
            "track_id": track_id,
            "track_duration": duration,
            "volume": round(volume_fixed / 256.0, 3),
            "width_px": round(width_fixed / 65536.0, 3),
            "height_px": round(height_fixed / 65536.0, 3),
        }

    def _parse_mdhd(self, handle: BinaryIO, atom: _Atom) -> dict[str, object]:
        payload = self._read_payload(handle, atom)
        if len(payload) < 24:
            return {}

        version = payload[0]
        if version == 1 and len(payload) >= 32:
            timescale = struct.unpack(">I", payload[20:24])[0]
            duration = struct.unpack(">Q", payload[24:32])[0]
        else:
            timescale = struct.unpack(">I", payload[12:16])[0]
            duration = struct.unpack(">I", payload[16:20])[0]

        return {
            "media_timescale": timescale,
            "media_duration_seconds": self._duration_seconds(duration, timescale),
        }

    def _parse_hdlr(self, handle: BinaryIO, atom: _Atom) -> dict[str, object]:
        payload = self._read_payload(handle, atom)
        if len(payload) < 24:
            return {}

        handler_type = payload[8:12].decode("latin-1", errors="replace")
        name_bytes = payload[24:]
        name = name_bytes.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()
        return {
            "handler_type": handler_type,
            "handler_name": name or None,
        }

    def _read_child_atoms(self, handle: BinaryIO, parent_atom: _Atom) -> list[_Atom]:
        child_start = parent_atom.data_offset
        if parent_atom.atom_type == "meta":
            child_start += 4
        return self._read_atoms(handle, start=child_start, end=parent_atom.end_offset)

    def _read_atoms(self, handle: BinaryIO, start: int, end: int) -> list[_Atom]:
        atoms: list[_Atom] = []
        offset = start

        while offset + 8 <= end:
            handle.seek(offset)
            header = handle.read(8)
            if len(header) < 8:
                break

            size, atom_type_bytes = struct.unpack(">I4s", header)
            atom_type = atom_type_bytes.decode("latin-1", errors="replace")
            header_size = 8

            if size == 1:
                extended_size_data = handle.read(8)
                if len(extended_size_data) < 8:
                    break
                size = struct.unpack(">Q", extended_size_data)[0]
                header_size = 16
            elif size == 0:
                size = end - offset

            if size < header_size:
                break

            atoms.append(
                _Atom(
                    atom_type=atom_type,
                    size=size,
                    header_size=header_size,
                    data_offset=offset + header_size,
                )
            )
            offset += size

        return atoms

    def _read_payload(self, handle: BinaryIO, atom: _Atom) -> bytes:
        payload_size = max(atom.size - atom.header_size, 0)
        handle.seek(atom.data_offset)
        return handle.read(payload_size)

    def _duration_seconds(self, duration: int, timescale: int) -> float | None:
        if timescale <= 0:
            return None
        return round(duration / timescale, 3)

    def _quicktime_timestamp_to_iso(self, timestamp: int) -> str | None:
        if timestamp <= 0:
            return None
        return (self._QUICKTIME_EPOCH + timedelta(seconds=timestamp)).isoformat()
