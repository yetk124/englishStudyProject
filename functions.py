import subprocess
import os
from glob import glob
from pydub import AudioSegment
import math
from tqdm import tqdm
import openai
from langchain.schema.output_parser import BaseOutputParser
from datetime import timedelta


def get_video_id(url: str) -> str:
    return url.lstrip("https://www.youtube.com/watch?v=")


def get_video_dir(video_id: str) -> str:
    return f"files/{video_id}"


def download_youtube_video(url: str) -> None:
    video_id = get_video_id(url)
    if not os.path.exists(get_video_dir(video_id)):
        command = ["yt-dlp", "-o", f"files/{video_id}/video.%(ext)s", url]
        subprocess.run(command)


def get_video_path(video_dir: str) -> str:
    extensions = ["mp4", "avi", "webm"]
    files = glob(f"{video_dir}/*.*")
    return next((file for file in files if file.split(".")[-1] in extensions), None)


def get_audio_path(video_dir: str) -> str:
    return f"{video_dir}/audio.mp3"


def get_audio_chunk_dir(video_dir: str) -> str:
    return f"{video_dir}/chunks"


def get_transcript_path(video_dir: str) -> str:
    return f"{video_dir}/transcript.txt"


def extract_audio_from_video(video_id: str) -> None:
    video_dir = get_video_dir(video_id)
    video_path = get_video_path(video_dir)
    audio_path = get_audio_path(video_dir)
    if not os.path.exists(audio_path):
        command = ["ffmpeg", "-i", video_path, "-vn", audio_path]
        subprocess.run(command)


def cut_audio_in_chunks(video_id: str, chunk_size: int = 10) -> None:
    video_dir = get_video_dir(video_id)
    audio_path = get_audio_path(video_dir)
    chunks_dir = get_audio_chunk_dir(video_dir)
    os.makedirs(chunks_dir, exist_ok=True)
    track = AudioSegment.from_mp3(audio_path)
    chunk_len = chunk_size * 60 * 1000
    chunks = math.ceil(len(track) / chunk_len)

    for i in tqdm(range(chunks), "Split audio file into chunks"):
        start_time = i * chunk_len
        end_time = (i + 1) * chunk_len
        chunk = track[start_time:end_time]
        chunk.export(f"{chunks_dir}/chunk_{i}.mp3", format="mp3")


def transcribe_chunks(video_dir: str):
    chunks_dir = get_audio_chunk_dir(video_dir)
    transcript_path = get_transcript_path(video_dir)
    if not os.path.exists(transcript_path):
        files = glob(f"{chunks_dir}/*")
        for file in tqdm(files, "Transcribing audio chunks"):
            with open(file, "rb") as audio_file, open(
                transcript_path, "a"
            ) as text_file:
                transcript = openai.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="vtt",
                    language="en",
                )
                text_file.write(transcript)


def parse_timestamp(ts: str) -> timedelta:
    hours, minutes, rest = ts.split(":")
    seconds, milliseconds = rest.split(".")
    return timedelta(
        hours=int(hours),
        minutes=int(minutes),
        seconds=int(seconds),
        milliseconds=int(milliseconds),
    )


class VttTimestampOutputParser(BaseOutputParser):
    def parse(self, text: str) -> list[dict]:
        lines = text.strip().splitlines()
        result = []
        offset = timedelta(minutes=0)
        for i, line in enumerate(lines):
            if "-->" in line:
                start, end = line.split(" --> ")
                caption = lines[i + 1] if i + 1 < len(lines) else ""
                result.append(
                    {
                        "start": parse_timestamp(start.strip()) + offset,
                        "end": parse_timestamp(end.strip()) + offset,
                        "text": caption.strip(),
                    }
                )
            elif "WEBVTT" in line:
                offset = parse_timestamp(end.strip()) + offset
        return result


class VttOutputParser(BaseOutputParser):
    def parse(self, text: str) -> list[dict]:
        lines = text.strip().splitlines()
        result = []
        for i, line in enumerate(lines):
            if "-->" in line:
                caption = lines[i + 1] if i + 1 < len(lines) else ""
                result.append(caption)
        return " ".join(result)
