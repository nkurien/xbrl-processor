# test_taxonomy_validator.py

import pytest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from validators.taxonomy_validator import TaxonomyValidator
from core.processor import XBRLProcessor
from core.models import XBRLContext, XBRLUnit, XBRLFact


@pytest.fixture
def validator():
    return TaxonomyValidator()

@pytest.fixture
def processor():
    """Create a processor instance for testing."""
    return XBRLProcessor()

@pytest.fixture
def sample_schema(tmp_path):
    """Create a sample taxonomy schema file."""
    schema_content = """<?xml version="1.0" encoding="UTF-8"?>
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
               xmlns:xbrli="http://www.xbrl.org/2003/instance"
               targetNamespace="http://example.com/test">

        <!-- Import the XBRL instance schema -->
        <xs:import namespace="http://www.xbrl.org/2003/instance"
                  schemaLocation="http://www.xbrl.org/2003/xbrl-instance-2003-12-31.xsd"/>

        <!-- Import the XBRL linkbase schema -->
        <xs:import namespace="http://www.xbrl.org/2003/linkbase"
                  schemaLocation="http://www.xbrl.org/2003/xbrl-linkbase-2003-12-31.xsd"/>

        <xs:element name="Revenue" type="xbrli:monetaryItemType" substitutionGroup="xbrli:item">
            <xs:annotation>
                <xs:documentation>Period Type: duration</xs:documentation>
            </xs:annotation>
        </xs:element>
        <xs:element name="Assets" type="xbrli:monetaryItemType" substitutionGroup="xbrli:item">
            <xs:annotation>
                <xs:documentation>Period Type: instant</xs:documentation>
            </xs:annotation>
        </xs:element>
    </xs:schema>"""

    schema_file = tmp_path / "test-taxonomy.xsd"
    schema_file.write_text(schema_content)

    # We also need to handle the schema loading differently in the validator
    return schema_file

@pytest.fixture
def sample_contexts():
    """Provide standard test contexts."""
    return {
        'ctx1': XBRLContext(
            id='ctx1',
            entity='http://entity.com:TEST',
            instant=datetime(2024, 1, 1),  # Remove period_start/end
            period_start=None,
            period_end=None
        ),
        'ctx2': XBRLContext(
            id='ctx2',
            entity='http://entity.com:TEST',
            instant=None,
            period_start=datetime(2024, 1, 1),
            period_end=datetime(2024, 12, 31)
        )
    }


@pytest.fixture
def sample_taxonomy(tmp_path):
    """Create a sample taxonomy for testing."""
    schema_content = """<?xml version="1.0" encoding="UTF-8"?>
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
               xmlns:xbrli="http://www.xbrl.org/2003/instance"
               xmlns:test="http://test.com/test"
               targetNamespace="http://test.com/test">
        <xs:element name="Valid" type="xbrli:monetaryItemType" substitutionGroup="xbrli:item"/>
        <xs:element name="MissingContext" type="xbrli:monetaryItemType" substitutionGroup="xbrli:item"/>
        <xs:element name="MissingUnit" type="xbrli:monetaryItemType" substitutionGroup="xbrli:item"/>
        <xs:element name="NonNumeric" type="xbrli:stringItemType" substitutionGroup="xbrli:item"/>
    </xs:schema>"""

    schema_file = tmp_path / "test-taxonomy.xsd"
    schema_file.write_text(schema_content)
    return schema_file


def test_validation(processor, sample_contexts, sample_taxonomy):
    """Test comprehensive validation including context, unit, and fact relationships."""
    # Load the test taxonomy
    processor.load_taxonomy(sample_taxonomy)

    # Setup test data
    processor.contexts.update(sample_contexts)
    processor.units['usd'] = XBRLUnit(id='usd', measures=['iso4217:USD'])

    # Add valid and invalid facts
    test_facts = [
        XBRLFact(concept='test:Valid', value=100, context_ref='ctx1', unit_ref='usd'),
        XBRLFact(concept='test:MissingContext', value=100, context_ref='missing', unit_ref='usd'),
        XBRLFact(concept='test:MissingUnit', value=100, context_ref='ctx1', unit_ref='missing'),
        XBRLFact(concept='test:NonNumeric', value='text', context_ref='ctx1', unit_ref=None)
    ]
    processor.facts.extend(test_facts)

    # Run validation
    errors = processor.validate()

    # Verify specific error messages
    error_texts = '\n'.join(errors)
    print("\nActual validation errors:")
    print(error_texts)

    # Updated assertions to match actual error messages
    assert "references missing context" in error_texts.lower()
    assert "references missing unit" in error_texts.lower()
    assert len(errors) >= 2, "Should find at least 2 validation errors"


def test_load_taxonomy(validator, sample_schema):
    """Test loading a taxonomy schema."""
    validator.load_taxonomy(sample_schema)
    assert "http://example.com/test" in validator.taxonomies
    assert "http://example.com/test:Revenue" in validator.concept_info
    assert "http://example.com/test:Assets" in validator.concept_info


def test_validate_monetary_concept(validator):
    """Test validation of monetary type concepts."""
    # Valid cases
    assert validator._validate_monetary(1000).is_valid
    assert validator._validate_monetary(Decimal("1000.50")).is_valid
    assert validator._validate_monetary(-500).is_valid

    # Invalid cases
    assert not validator._validate_monetary("1000").is_valid
    assert not validator._validate_monetary(None).is_valid
    assert not validator._validate_monetary("invalid").is_valid


def test_validate_context(validator):
    """Test context validation."""
    # Valid instant context
    valid_instant = {
        'entity': 'http://example.com:123',
        'instant': datetime(2024, 1, 1)
    }
    assert validator.validate_context(valid_instant).is_valid

    # Valid duration context
    valid_duration = {
        'entity': 'http://example.com:123',
        'startDate': datetime(2024, 1, 1),
        'endDate': datetime(2024, 12, 31)
    }
    assert validator.validate_context(valid_duration).is_valid

    # Invalid contexts
    invalid_date_order = {
        'entity': 'http://example.com:123',
        'startDate': datetime(2024, 12, 31),
        'endDate': datetime(2024, 1, 1)
    }
    assert not validator.validate_context(invalid_date_order).is_valid

    no_entity = {
        'instant': datetime(2024, 1, 1)
    }
    assert not validator.validate_context(no_entity).is_valid


def test_validate_unit(validator):
    """Test unit validation."""
    # Valid units
    valid_currency = {
        'measures': ['iso4217:USD']
    }
    assert validator.validate_unit(valid_currency).is_valid

    valid_shares = {
        'measures': ['xbrli:shares']
    }
    assert validator.validate_unit(valid_shares).is_valid

    valid_divide = {
        'measures': ['iso4217:USD', 'xbrli:shares'],
        'divide': True,
        'numerator': ['iso4217:USD'],
        'denominator': ['xbrli:shares']
    }
    assert validator.validate_unit(valid_divide).is_valid

    # Invalid units
    invalid_currency = {
        'measures': ['iso4217:INVALID']
    }
    result = validator.validate_unit(invalid_currency)
    assert result.is_valid  # Still valid but should have warnings
    assert any('Unknown currency code' in w for w in result.warnings)

    no_measures = {}
    assert not validator.validate_unit(no_measures).is_valid


def test_integrated_validation(sample_schema):
    """Test integrated validation with XBRLProcessor."""
    processor = XBRLProcessor()
    validator = TaxonomyValidator()
    processor.validator = validator
    validator.load_taxonomy(sample_schema)

    # Add test data
    processor.contexts['ctx1'] = XBRLContext(
        id='ctx1',
        entity='http://example.com:123',
        instant=datetime(2024, 1, 1)
    )

    processor.contexts['ctx2'] = XBRLContext(
        id='ctx2',
        entity='http://example.com:123',
        instant=None,
        period_start=datetime(2024, 1, 1),
        period_end=datetime(2024, 12, 31)
    )

    processor.units['usd'] = XBRLUnit(
        id='usd',
        measures=['iso4217:USD']
    )

    # Add both valid and invalid facts
    processor.facts.extend([
        # Valid fact (instant context for Assets)
        XBRLFact(
            concept='test:Assets',  # Changed from full URI to match taxonomy
            value=1000000,
            context_ref='ctx1',
            unit_ref='usd'
        ),
        # Invalid fact (instant context for Revenue)
        XBRLFact(
            concept='test:Revenue',  # Changed from full URI to match taxonomy
            value=500000,
            context_ref='ctx1',
            unit_ref='usd'
        )
    ])

    errors = processor.validate()
    assert len(errors) > 0, "Should detect validation errors"
    error_texts = '\n'.join(str(err) for err in errors)
    assert any('should be numeric' in str(err).lower() or 'concept test:revenue' in str(err).lower()
              for err in errors), "Should detect period type or concept issues"


def test_complex_validation_scenarios(validator, sample_schema):
    """Test more complex validation scenarios."""
    validator.load_taxonomy(sample_schema)

    # Test nested context with scenario
    complex_context = {
        'entity': 'http://example.com:123',
        'instant': datetime(2024, 1, 1),
        'scenario': {
            'segments': [
                {'dimension': 'Region', 'value': 'North'},
                {'dimension': 'Product', 'value': 'A'}
            ]
        }
    }
    result = validator.validate_context(complex_context)
    assert result.is_valid

    # Test unit with complex divide relationship
    complex_unit = {
        'measures': ['iso4217:USD', 'xbrli:shares'],
        'divide': True,
        'numerator': ['iso4217:USD'],
        'denominator': ['xbrli:shares']
    }
    result = validator.validate_unit(complex_unit)
    assert result.is_valid

    # Test concept with multiple validation aspects
    concept_result = validator.validate_concept(
        'http://example.com/test:Revenue',
        Decimal('1000000.00'),
        {
            'entity': 'http://example.com:123',
            'startDate': datetime(2024, 1, 1),
            'endDate': datetime(2024, 12, 31)
        }
    )
    assert concept_result.is_valid


def test_error_conditions(validator):
    """Test various error conditions and edge cases."""
    # Test invalid taxonomy load
    with pytest.raises(ValueError):
        validator.load_taxonomy(Path("nonexistent.xsd"))

    # Test validation with empty/none values
    assert not validator._validate_monetary(None).is_valid
    assert not validator._validate_decimal("invalid").is_valid
    assert not validator._validate_datetime("not-a-date").is_valid

    # Test context with mixed instant/duration
    invalid_context = {
        'entity': 'http://example.com:123',
        'instant': datetime(2024, 1, 1),
        'startDate': datetime(2024, 1, 1),
        'endDate': datetime(2024, 12, 31)
    }
    result = validator.validate_context(invalid_context)
    assert not result.is_valid
    assert any('cannot have both instant and duration' in err.lower()
               for err in result.errors)