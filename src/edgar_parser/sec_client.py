from __future__ import annotations

from dataclasses import dataclass
import gzip
import json
import time
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import zlib

from edgar_parser.config import IdentityConfig


DEFAULT_RATE_LIMIT_PER_SECOND = 5.0
SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


class SecRequestError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SecResponse:
    url: str
    status_code: int
    headers: dict[str, str]
    body: bytes


class SecClient:
    def __init__(
        self,
        identity: IdentityConfig,
        rate_limit_per_second: float = DEFAULT_RATE_LIMIT_PER_SECOND,
        opener: Callable[[Request], Any] | None = None,
        sleep: Callable[[float], None] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.identity = identity
        self.rate_limit_per_second = rate_limit_per_second
        self._opener = opener or urlopen
        self._sleep = sleep or time.sleep
        self._monotonic = monotonic or time.monotonic
        self._last_request_at = 0.0

    def get_json(self, url: str) -> dict[str, Any]:
        response = self.get(url)
        return json.loads(response.body.decode("utf-8"))

    def get_text(self, url: str) -> str:
        response = self.get(url)
        return response.body.decode("utf-8", errors="replace")

    def get(self, url: str) -> SecResponse:
        self._enforce_rate_limit()
        request = Request(
            url=url,
            headers={
                "User-Agent": self.identity.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Host": urlparse(url).netloc,
            },
        )

        with self._opener(request) as handle:
            status_code = getattr(handle, "status", handle.getcode())
            body = handle.read()
            headers = {key: value for key, value in handle.headers.items()}

        if status_code >= 400:
            raise SecRequestError(f"SEC request failed for {url} with status {status_code}")

        return SecResponse(
            url=url,
            status_code=status_code,
            headers=headers,
            body=_decode_body(body, headers.get("Content-Encoding")),
        )

    def fetch_company_tickers(self) -> dict[str, Any]:
        return self.get_json(SEC_COMPANY_TICKERS_URL)

    def fetch_submissions(self, cik: str) -> dict[str, Any]:
        return self.get_json(self.submissions_url(cik))

    def fetch_submissions_file(self, name: str) -> dict[str, Any]:
        return self.get_json(f"https://data.sec.gov/submissions/{name}")

    def fetch_filing_index_json(self, cik: str, accession_number: str) -> dict[str, Any]:
        return self.get_json(self.filing_index_json_url(cik, accession_number))

    @staticmethod
    def submissions_url(cik: str) -> str:
        padded = "".join(character for character in str(cik) if character.isdigit()).zfill(10)
        return f"https://data.sec.gov/submissions/CIK{padded}.json"

    @staticmethod
    def filing_text_url(cik_without_zeroes: str, accession_number: str) -> str:
        return f"https://www.sec.gov/Archives/edgar/data/{cik_without_zeroes}/{accession_number}.txt"

    @staticmethod
    def filing_directory_url(cik_without_zeroes: str, accession_number_nodashes: str, document_name: str) -> str:
        return f"https://www.sec.gov/Archives/edgar/data/{cik_without_zeroes}/{accession_number_nodashes}/{document_name}"

    @staticmethod
    def filing_index_json_url(cik: str, accession_number: str) -> str:
        cik_without_zeroes = str(int(str(cik)))
        accession_number_nodashes = accession_number.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{cik_without_zeroes}/{accession_number_nodashes}/index.json"

    def _enforce_rate_limit(self) -> None:
        interval = 1.0 / self.rate_limit_per_second
        elapsed = self._monotonic() - self._last_request_at
        if elapsed < interval:
            self._sleep(interval - elapsed)
        self._last_request_at = self._monotonic()


def _decode_body(body: bytes, content_encoding: str | None) -> bytes:
    if not content_encoding:
        return body

    encoding = content_encoding.lower()
    if encoding == "gzip":
        return gzip.decompress(body)
    if encoding == "deflate":
        return zlib.decompress(body)
    return body
