import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import aiofiles
import pdfplumber
from pydantic import BaseModel, model_validator, ConfigDict, Field, field_validator
from pypdf import PdfReader, PdfWriter

from init import DATA_DIR
from provider.merger import MergeItem
from provider.merger import Parser, Merge, MergeStrategy


@dataclass
class CallLog(MergeItem):
    datetime: str
    number: str
    duration_seconds: int

    def get_unique_key(self) -> str:
        # Assuming someone is dialing to at max 1 person at a given time
        return f"{self.datetime}_{self.number}"

    def __str__(self):
        return f"Called {self.number} for {self.duration_seconds} seconds at {self.datetime}"

    def merge(self, other: 'CallLog') -> 'CallLog':
        # Implement the logic to merge two CallLog objects across generations
        self.duration_seconds = other.duration_seconds
        return self

    def duration_repr(self):
        if self.duration_seconds < 60:
            return f'{self.duration_seconds} sec'
        elif self.duration_seconds < 3600:
            return f'{self.duration_seconds // 60} min'
        else:
            return f'{self.duration_seconds // 3600} hr'


class AirtelParser(Parser):
    DATA_PATH = os.path.join(DATA_DIR, 'airtel')

    def __init__(self, path: str = None):
        if not path:
            path = self.DATA_PATH
        super().__init__(path)

    @staticmethod
    def _decrypt_pdf(input_path, output_path, password):
        reader = PdfReader(input_path)

        if reader.is_encrypted:
            if not reader.decrypt(password):
                raise ValueError(f"Incorrect PDF {password=} for {input_path=}")

        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        with open(output_path, "wb") as f:
            writer.write(f)

    @staticmethod
    def _parse_airtel_pdf(pdf_path):
        VOICE_HEADER = "S.No. Date Time Number Duration(sec) Amount(Rs)"
        SMS_HEADER = "S.No. Date Time Number Amount(Rs)"
        voice_calls = []
        # sms = []
        # recharges = []

        section = None
        file_time = None

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text(
                    x_tolerance=2,
                    y_tolerance=3,
                )

                if not text:
                    continue

                for line in text.splitlines():
                    line = line.strip()

                    # -------------------------
                    # Section detection
                    # -------------------------

                    if line == "Your Details":
                        section = "details"
                        continue

                    if line == "RECHARGE":
                        section = "recharge"
                        continue

                    elif line == "VOICE Roaming":
                        section = "voice"
                        continue

                    elif line == "SMS Roaming":
                        section = "sms"
                        continue

                    # Headers / section titles
                    if line in {
                        "Your Itemized Statement",
                        VOICE_HEADER,
                        SMS_HEADER,
                        "S.No. Date Time Amount(Rs) Channel",
                    }:
                        continue

                    if section == "details":
                        if line.startswith("Month"):
                            file_time = line[5:].strip()
                            print("Parsing for month:", file_time)
                    # -------------------------
                    # Voice calls
                    # -------------------------

                    elif section == "voice":
                        match = re.match(
                            r"^(\d+)\s+"
                            r"(\d{2}-\d{2}-\d{4})\s+"
                            r"(\d{2}:\d{2}:\d{2})\s+"
                            r"(\S+)\s+"
                            r"(\d+)\s+"
                            r"([\d.]+)$",
                            line,
                        )

                        if match:
                            (
                                serial,
                                date,
                                time,
                                number,
                                duration,
                                amount,
                            ) = match.groups()

                            voice_calls.append({
                                "serial": int(serial),
                                "datetime": datetime.strptime(
                                    f"{date} {time}",
                                    "%d-%m-%Y %H:%M:%S",
                                ),
                                "number": number,
                                "duration_seconds": int(duration),
                                # "amount": float(amount),
                            })

                            continue

                    # -------------------------
                    # SMS
                    # -------------------------

                    elif section == "sms":
                        # TODO: WIP. May be later
                        pass
                        # match = re.match(
                        #     r"^(\d+)\s+"
                        #     r"(\d{2}-\d{2}-\d{4})\s+"
                        #     r"(\d{2}:\d{2}:\d{2})\s+"
                        #     r"(\S+)\s+"
                        #     r"([\d.]+)$",
                        #     line,
                        # )
                        # 
                        # if match:
                        #     (
                        #         serial,
                        #         date,
                        #         time,
                        #         number,
                        #         amount,
                        #     ) = match.groups()
                        # 
                        #     sms.append({
                        #         "serial": int(serial),
                        #         "datetime": datetime.strptime(
                        #             f"{date} {time}",
                        #             "%d-%m-%Y %H:%M:%S",
                        #         ),
                        #         "number": number,
                        #         "amount": float(amount),
                        #     })
                        # 
                        #     continue

                    # -------------------------
                    # Recharge
                    # -------------------------

                    elif section == "recharge":
                        # TODO: WIP. May be later
                        pass
                        # match = re.match(
                        #     r"^(\d+)\s+"
                        #     r"(\d{2}-\d{2}-\d{4})\s+"
                        #     r"(\d{2}:\d{2})\s+"
                        #     r"([\d.]+)\s+"
                        #     r"(.+)$",
                        #     line,
                        # )
                        #
                        # if match:
                        #     (
                        #         serial,
                        #         date,
                        #         time,
                        #         amount,
                        #         channel,
                        #     ) = match.groups()
                        #
                        #     recharges.append({
                        #         "serial": int(serial),
                        #         "datetime": datetime.strptime(
                        #             f"{date} {time}",
                        #             "%d-%m-%Y %H:%M",
                        #         ),
                        #         "amount": float(amount),
                        #         "channel": channel.strip(),
                        #     })
                        #
                        #     continue

        return file_time, {
            "voice_calls": voice_calls,
            # "sms": sms,
            # "recharges": recharges,
        }

    async def load_incoming_data(self):
        data = {}
        password = os.getenv("AIRTEL_PASSWORD")

        if not password:
            raise ValueError("AIRTEL_PASSWORD environment variable is not set")

        try:
            filenames = os.listdir(self.path)
        except FileNotFoundError:
            print(f"Directory {self.path} not found. Creating")
            os.makedirs(self.path)
            return data
        for filename in filenames:
            if filename.endswith("_decrypted.pdf") or not filename.endswith(".pdf"):
                continue

            print(f"Processing {filename}...")

            clean_filename = filename[:-4]  # Remove .pdf extension
            encrypted = Path(f"{self.path}/{filename}")
            decrypted = Path(f"{self.path}/{clean_filename}_decrypted.pdf")

            self._decrypt_pdf(encrypted, decrypted, password=password)

            file_time, records = self._parse_airtel_pdf(decrypted)
            data[file_time] = records
        return data

    async def load_old_data(self):
        try:
            async with aiofiles.open(f'{self.path}/logs.json', 'r') as f:
                return json.loads(await f.read())
        except FileNotFoundError:
            print("Error reading matches file.")
            return []

    def validate_old_data(self, old_data):
        # TODO
        pass

    def validate_incoming_data(self, raw_data):
        if not isinstance(raw_data, dict):
            raise ValueError("Raw data must be a dict of file times with their call data.")

        if len(raw_data) == 0:
            raise ValueError("Raw data is empty.")

        for _, call_logs in raw_data.items():
            AirtelDumpModel.model_validate(call_logs)

    def parse_incoming_data(self, raw_data) -> List[CallLog]:
        call_logs: List[CallLog] = []
        last_call_log: Optional[CallLog] = None
        for _, raw_info in raw_data.items():
            for raw_call_log in raw_info['voice_calls']:
                call_log = CallLog(
                    number=raw_call_log['number'],
                    datetime=raw_call_log['datetime'],
                    duration_seconds=int(raw_call_log['duration_seconds']),
                )
                if not last_call_log or last_call_log.get_unique_key() != call_log.get_unique_key():
                    call_logs.append(call_log)
                    last_call_log = call_log
                else:
                    last_call_log.duration_seconds += int(raw_call_log['duration_seconds'])

        return call_logs

    def parse_old_data(self, raw_data) -> List[MergeItem]:
        call_logs: List[CallLog] = []
        for raw_call_log in raw_data:
            call_log = CallLog(
                number=raw_call_log['number'],
                datetime=raw_call_log['datetime'],
                duration_seconds=int(raw_call_log['duration_seconds']),
            )
            call_logs.append(call_log)
        return call_logs


class AirtelMerge(Merge):
    merge_strategy = MergeStrategy.MERGE
    parser = AirtelParser

    def __init__(self, new_path: str):
        super().__init__(new_path)

    async def dump(self, data: List[CallLog], dry_run=True) -> bool:
        file_name = f"{self.parser.DATA_PATH}/logs{'_dry_run' if dry_run else ''}.json"
        try:
            # Convert objects to dictionaries if data elements are custom objects (e.g. dataclasses or Pydantic models)
            # If 'data' is already a list of dicts/primitives, `default=str` or custom serializer can be used.
            async with aiofiles.open(file_name, "w") as f:
                await f.write(
                    json.dumps(
                        data,
                        default=lambda o: (
                            o.__dict__ if hasattr(o, "__dict__") else str(o)
                        ),
                        indent=4,
                    )
                )
            return True
        except Exception as e:
            print(f"Error writing to matches file: {e}")
            return False


class CallModel(BaseModel):
    # This class is to validate our own customized dump of Airtel backup
    model_config = ConfigDict(extra='forbid')
    serial: int = Field(gt=0)
    datetime: datetime
    number: str
    duration_seconds: int = Field(gt=0)

    @field_validator("number")
    @classmethod
    def validate_number(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("Number must contain only digits")

        if len(value) != 10:
            raise ValueError("Number must be a 10-digit number")

        if value[0] not in "6789":
            raise ValueError("Invalid Indian mobile number")
        return value


class AirtelDumpModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_calls: list[CallModel]

    @model_validator(mode="after")
    def validate_voice_call_serials(self):
        serials = [call.serial for call in self.voice_calls]

        if serials != list(range(1, len(serials) + 1)):
            raise ValueError(
                "Voice call serial numbers must be continuous from 1 to n"
            )

        return self
