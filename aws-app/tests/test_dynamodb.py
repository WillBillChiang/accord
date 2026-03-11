"""Tests for DynamoDB data access layer."""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock boto3
mock_boto3 = MagicMock()
sys.modules['boto3'] = mock_boto3
sys.modules['botocore'] = MagicMock()
sys.modules['botocore.exceptions'] = MagicMock()

# Need to set up ClientError before importing
from unittest.mock import MagicMock as MockClass
ClientError = type('ClientError', (Exception,), {})
sys.modules['botocore.exceptions'] = MagicMock(ClientError=ClientError)

from models.dynamodb import _convert_floats, _convert_decimals, DynamoDBClient


class TestFloatConversion:
    """Test float <-> Decimal conversion for DynamoDB."""

    def test_convert_float_to_decimal(self):
        """Float should convert to Decimal."""
        result = _convert_floats(3.14)
        assert isinstance(result, Decimal)

    def test_convert_dict_floats(self):
        """Floats in dicts should convert."""
        result = _convert_floats({"price": 100.50, "name": "test"})
        assert isinstance(result["price"], Decimal)
        assert isinstance(result["name"], str)

    def test_convert_list_floats(self):
        """Floats in lists should convert."""
        result = _convert_floats([1.0, 2.0, "text"])
        assert isinstance(result[0], Decimal)
        assert isinstance(result[2], str)

    def test_convert_nested(self):
        """Nested structures should convert recursively."""
        result = _convert_floats({"data": {"price": 99.99, "items": [1.5]}})
        assert isinstance(result["data"]["price"], Decimal)
        assert isinstance(result["data"]["items"][0], Decimal)


class TestDecimalConversion:
    """Test Decimal -> float conversion."""

    def test_convert_decimal_to_float(self):
        """Decimal should convert to float."""
        result = _convert_decimals(Decimal("3.14"))
        assert isinstance(result, float)
        assert abs(result - 3.14) < 0.001

    def test_convert_dict_decimals(self):
        """Decimals in dicts should convert."""
        result = _convert_decimals({"price": Decimal("100.50")})
        assert isinstance(result["price"], float)

    def test_convert_list_decimals(self):
        """Decimals in lists should convert."""
        result = _convert_decimals([Decimal("1.0"), Decimal("2.0")])
        assert all(isinstance(x, float) for x in result)

    def test_non_decimal_passthrough(self):
        """Non-Decimal values should pass through unchanged."""
        result = _convert_decimals({"name": "test", "count": 5})
        assert result["name"] == "test"
        assert result["count"] == 5


class TestDynamoDBClient:
    """Test DynamoDB client operations."""

    def test_client_creation(self):
        """DynamoDBClient should instantiate."""
        client = DynamoDBClient()
        assert client is not None

    def test_put_session(self):
        """put_session should call DynamoDB put_item."""
        client = DynamoDBClient()
        mock_resource = MagicMock()
        mock_table = MagicMock()
        mock_resource.Table.return_value = mock_table
        client._dynamodb = mock_resource

        client.put_session({
            "sessionId": "test-001",
            "status": "active",
            "createdAt": 1234567890.0,
        })

        mock_table.put_item.assert_called_once()

    def test_get_session_found(self):
        """get_session should return session when found."""
        client = DynamoDBClient()
        mock_resource = MagicMock()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"sessionId": "test-001", "status": "active"}
        }
        mock_resource.Table.return_value = mock_table
        client._dynamodb = mock_resource

        result = client.get_session("test-001")
        assert result is not None
        assert result["sessionId"] == "test-001"

    def test_get_session_not_found(self):
        """get_session should return None when not found."""
        client = DynamoDBClient()
        mock_resource = MagicMock()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_resource.Table.return_value = mock_table
        client._dynamodb = mock_resource

        result = client.get_session("nonexistent")
        assert result is None
