"""
Audio MCP Server

This module provides MCP (Model-Controller-Processor) server functionality for audio processing.
It includes tools for audio transcription and encoding audio files to base64 format.
The server handles both local audio files and remote audio URLs with proper validation
and supports various audio formats.

Main functions:
- encode_audio: Encodes audio files to base64 format
- mcptranscribe: Transcribes audio content using LLM models
"""

import base64
import json
import os
import traceback
from typing import List

from openai import OpenAI
from pydantic import BaseModel, Field

from aworld.logs.util import logger
from aworld.mcp_servers.abc.base import MCPServerBase, mcp
from aworld.mcp_servers.utils import get_file_from_source


class AudioTranscriptionResult(BaseModel):
    """Model representing the result of an audio transcription"""

    audio_url: str
    transcription: str
    success: bool
    error: str = None


class AudioServer(MCPServerBase):
    """
    Audio Server class for processing audio files.

    This class provides methods for encoding audio to base64 format and
    transcribing audio content using LLM models.
    """

    _instance = None
    _llm = None

    def __new__(cls):
        """Implement singleton pattern"""
        if cls._instance is None:
            cls._instance = super(AudioServer, cls).__new__(cls)
            cls._instance._init_server()
        return cls._instance

    def _init_server(self):
        """Initialize the audio server"""
        self._llm = OpenAI(
            base_url=os.getenv("LLM_BASE_URL_ZZZ", ""),
            api_key=os.getenv("LLM_API_KEY_ZZZ", ""),
        )
        logger.info("AudioServer initialized")

    @classmethod
    def get_instance(cls):
        """Get the singleton instance of AudioServer"""
        if cls._instance is None:
            return cls()
        return cls._instance

    @staticmethod
    def encode_audio(audio_source: str, with_header: bool = True) -> str:
        """
        Encode audio to base64 format with robust file handling

        Args:
            audio_source: URL or local file path of the audio
            with_header: Whether to include MIME type header

        Returns:
            str: Base64 encoded audio string, with MIME type prefix if with_header is True

        Raises:
            ValueError: When audio source is invalid or audio format is not supported
            IOError: When audio file cannot be read
        """
        if not audio_source:
            raise ValueError("Audio source cannot be empty")

        try:
            # Get file with validation (only audio files allowed)
            file_path, mime_type, content = get_file_from_source(
                audio_source,
                allowed_mime_prefixes=["audio/"],
                max_size_mb=25.0,  # 25MB limit for audio files
            )

            # Encode to base64
            audio_base64 = base64.b64encode(content).decode()

            # Format with header if requested
            final_audio = (
                f"data:{mime_type};base64,{audio_base64}"
                if with_header
                else audio_base64
            )

            # Clean up temporary file if it was created for a URL
            if file_path != os.path.abspath(audio_source) and os.path.exists(file_path):
                os.unlink(file_path)

            return final_audio

        except Exception as e:
            logger.error(
                f"Error encoding audio from {audio_source}: {traceback.format_exc()}"
            )
            raise

    @mcp
    @classmethod
    def transcribe_audio(
        cls,
        audio_urls: List[str] = Field(
            description="The input audio in given a list of filepaths or urls."
        ),
    ) -> str:
        """
        Transcribe the given audio in a list of filepaths or urls.

        Args:
            audio_urls: List of audio file paths or URLs

        Returns:
            str: JSON string containing transcriptions
        """
        # Handle Field objects if they're passed directly
        if hasattr(audio_urls, "default") and not isinstance(audio_urls, list):
            audio_urls = audio_urls.default

        # Get the singleton instance and ensure server is initialized
        instance = cls.get_instance()

        results = []
        for audio_url in audio_urls:
            try:
                # Get file with validation (only audio files allowed)
                file_path, _, _ = get_file_from_source(
                    audio_url, allowed_mime_prefixes=["audio/"], max_size_mb=25.0
                )

                # Use the file for transcription
                with open(file_path, "rb") as audio_file:
                    transcription = instance._llm.audio.transcriptions.create(
                        file=audio_file,
                        model="gpt-4o-transcribe",
                        response_format="text",
                    )

                result = AudioTranscriptionResult(
                    audio_url=audio_url, transcription=transcription, success=True
                )
                results.append(result)

                # Clean up temporary file if it was created for a URL
                if file_path != os.path.abspath(audio_url) and os.path.exists(
                    file_path
                ):
                    os.unlink(file_path)

            except Exception as e:
                error_msg = str(e)
                logger.error(
                    f"Error transcribing {audio_url}: {traceback.format_exc()}"
                )
                result = AudioTranscriptionResult(
                    audio_url=audio_url,
                    transcription="",
                    success=False,
                    error=error_msg,
                )
                results.append(result)

        logger.info(f"Transcription results: {len(results)} files processed")
        return json.dumps(
            {
                "total": len(audio_urls),
                "success_count": sum(1 for r in results if r.success),
                "failed_count": sum(1 for r in results if not r.success),
                "results": [r.model_dump() for r in results],
            },
            ensure_ascii=False,
        )


if __name__ == "__main__":
    audio_server = AudioServer.get_instance()
    result = audio_server.transcribe_audio(
        audio_urls=[
            "/Users/arac/Desktop/gaia-benchmark/GAIA/2023/validation/2b3ef98c-cc05-450b-a719-711aee40ac65.mp3"
        ]
    )
    logger.success(result)
