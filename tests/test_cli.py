import gzip

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from asc_cli.auth import create_token
from asc_cli.client import encode_rows, parse_tab_report
from asc_cli.cli import _validate_date, _validate_month, render


def test_parse_tab_report_reads_apple_gzip_payload():
    payload = gzip.compress(b"Provider\tSKU\tUnits\nAPPLE\tfasttempo\t3\n")
    assert parse_tab_report(gzip.decompress(payload)) == [
        {"Provider": "APPLE", "SKU": "fasttempo", "Units": "3"}
    ]


def test_encode_rows_supports_csv_and_json():
    rows = [{"SKU": "fasttempo", "Units": "3"}]
    assert "SKU,Units" in encode_rows(rows, "csv")
    assert '"SKU": "fasttempo"' in encode_rows(rows, "json")


def test_report_date_validation():
    _validate_date("2026-08-01")
    _validate_month("2026-08")
    for validator, value in ((_validate_date, "2026-99-99"), (_validate_month, "2026-99")):
        try:
            validator(value)
        except ValueError:
            pass
        else:
            raise AssertionError("expected invalid date to fail")


def test_jwt_has_expected_claims(tmp_path):
    key = tmp_path / "AuthKey_test.p8"
    private_key = ec.generate_private_key(ec.SECP256R1())
    key.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key.chmod(0o600)
    token = create_token(
        {"issuer_id": "issuer", "key_id": "key", "private_key": str(key)},
        now=1_700_000_000,
    )
    assert jwt.decode(token, options={"verify_signature": False}) == {
        "iss": "issuer",
        "iat": 1_700_000_000,
        "exp": 1_700_001_200,
        "aud": "appstoreconnect-v1",
    }
    assert jwt.get_unverified_header(token)["kid"] == "key"


def test_apps_table_is_compact():
    output = render(
        [{"id": "123", "attributes": {"name": "FastTempo", "bundleId": "app.fasttempo", "sku": "FT"}}],
        output_format="table",
        command="apps",
    )
    assert "id\tname\tbundleId\tsku" in output
    assert "123\tFastTempo\tapp.fasttempo\tFT" in output
